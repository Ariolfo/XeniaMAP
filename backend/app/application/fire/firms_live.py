"""Caso de uso: hotspots FIRMS VIIRS en vivo (24h / 48h) para un AOI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping

from app.domain.fire.ports import FirmsHotspotPort
from app.modules.fire.validate_firms import (
    AOI_QUERY_BUFFER_M,
    choose_utm_crs,
    normalize_acq_datetime,
    query_bbox_from_aoi,
)


def _gdf_from_geometry_geojson(geometry_geojson: dict) -> gpd.GeoDataFrame:
    raw = geometry_geojson or {}
    t = raw.get("type")
    if t == "FeatureCollection":
        gdf = gpd.GeoDataFrame.from_features(raw.get("features") or [], crs="EPSG:4326")
    elif t == "Feature":
        gdf = gpd.GeoDataFrame.from_features([raw], crs="EPSG:4326")
    elif t in ("Polygon", "MultiPolygon"):
        gdf = gpd.GeoDataFrame.from_features(
            [{"type": "Feature", "properties": {}, "geometry": raw}],
            crs="EPSG:4326",
        )
    else:
        raise ValueError(f"GeoJSON no soportado: {t}")
    if gdf.empty:
        raise ValueError("AOI vacío")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)
    gdf = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty)].copy()
    if gdf.empty:
        raise ValueError("AOI sin geometrías válidas")
    return gdf


def _parse_acq_utc(row: pd.Series) -> datetime | None:
    iso = normalize_acq_datetime(row)
    if not iso:
        return None
    try:
        if iso.endswith("Z"):
            return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        return datetime.strptime(iso[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _empty_fc() -> dict:
    return {"type": "FeatureCollection", "features": []}


def split_hotspots_by_age(
    records,
    aoi_projected: gpd.GeoDataFrame,
    *,
    as_of: datetime,
    hours: int,
) -> tuple[dict, dict, int, int]:
    """Separa detecciones en buckets 24h y 24–48h.

    ``records``: ``Sequence[Mapping]`` (DTO de puerto) o DataFrame legado.
    """
    fc_24 = _empty_fc()
    fc_48 = _empty_fc()
    if records is None:
        return fc_24, fc_48, 0, 0
    if isinstance(records, pd.DataFrame):
        df = records
    else:
        rows = list(records)
        if not rows:
            return fc_24, fc_48, 0, 0
        df = pd.DataFrame(rows)
    if df.empty:
        return fc_24, fc_48, 0, 0

    geometry = gpd.points_from_xy(df["longitude"], df["latitude"])
    gdf = gpd.GeoDataFrame(df.copy(), geometry=geometry, crs="EPSG:4326").to_crs(aoi_projected.crs)
    query_zone = aoi_projected.geometry.unary_union.buffer(AOI_QUERY_BUFFER_M)
    gdf = gdf[gdf.geometry.intersects(query_zone)].copy()
    if gdf.empty:
        return fc_24, fc_48, 0, 0

    cutoff_24 = as_of - timedelta(hours=24)
    cutoff_48 = as_of - timedelta(hours=min(hours, 48))
    window_start = as_of - timedelta(hours=hours)

    feats_24: list[dict] = []
    feats_48: list[dict] = []

    gdf_wgs = gdf.to_crs(4326)
    for _, row in gdf_wgs.iterrows():
        acq = _parse_acq_utc(row)
        if acq is None or acq < window_start or acq > as_of:
            continue
        props = {
            k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
            for k, v in row.drop(labels=["geometry"], errors="ignore").items()
            if k != "geometry"
        }
        props["acq_datetime_utc"] = acq.strftime("%Y-%m-%dT%H:%MZ")
        age_h = (as_of - acq).total_seconds() / 3600.0
        props["age_hours"] = round(age_h, 2)
        feat = {
            "type": "Feature",
            "geometry": mapping(row.geometry),
            "properties": props,
        }
        if acq >= cutoff_24:
            props["age_bucket"] = "24h"
            feats_24.append(feat)
        elif hours >= 48 and acq >= cutoff_48:
            props["age_bucket"] = "48h"
            feats_48.append(feat)

    return (
        {"type": "FeatureCollection", "features": feats_24},
        {"type": "FeatureCollection", "features": feats_48},
        len(feats_24),
        len(feats_48),
    )


class GetFirmsLiveHotspots:
    """Caso de uso: consulta FIRMS en vivo independiente de dNBR."""

    def __init__(self, firms: FirmsHotspotPort) -> None:
        self._firms = firms

    def execute(
        self,
        *,
        geometry_geojson: dict,
        map_key: str,
        hours: int = 48,
    ) -> dict[str, Any]:
        if hours not in (24, 48):
            raise ValueError("hours debe ser 24 o 48")
        key = (map_key or "").strip()
        if not key:
            raise RuntimeError(
                "FIRMS_MAP_KEY no configurada. "
                "https://firms.modaps.eosdis.nasa.gov/api/map_key/"
            )

        as_of = datetime.now(timezone.utc)
        aoi = _gdf_from_geometry_geojson(geometry_geojson)
        target_crs = choose_utm_crs(aoi)
        aoi_projected = aoi.to_crs(target_crs)
        bbox = query_bbox_from_aoi(aoi_projected)

        start_date = (as_of - timedelta(hours=hours)).date()
        end_date = as_of.date()

        raw = self._firms.download(
            map_key=key,
            bbox=bbox,
            start_date=start_date,
            end_date=end_date,
        )
        fc_24, fc_48, n24, n48 = split_hotspots_by_age(
            raw, aoi_projected, as_of=as_of, hours=hours
        )

        return {
            "as_of": as_of.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hours": hours,
            "bbox_wsen": [round(v, 6) for v in bbox],
            "fire_start": start_date.isoformat(),
            "fire_end": end_date.isoformat(),
            "counts": {"hotspots_24h": n24, "hotspots_48h": n48},
            "layers": {
                "hotspots_24h": fc_24,
                "hotspots_48h": fc_48 if hours >= 48 else _empty_fc(),
            },
        }
