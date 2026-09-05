"""Helpers to materialize a FireOrder AOI for scripts 02/03."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd


def write_order_aoi_gpkg(
    *,
    geometry_geojson: dict,
    request_name: str,
    department: str | None,
    output_path: str | Path,
) -> Path:
    """
    Write order geometry as GeoPackage with MpNombre/Depto fields expected by
    the Tolima dNBR / FIRMS scripts.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

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
        # Fallback: try parsing as FeatureCollection string-ish payload
        gdf = gpd.GeoDataFrame.from_features(
            json.loads(json.dumps(raw)).get("features") or [],
            crs="EPSG:4326",
        )

    if gdf.empty:
        raise ValueError("AOI geometry is empty")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    gdf = gdf[gdf.geometry.notna() & (~gdf.geometry.is_empty)].copy()
    if gdf.empty:
        raise ValueError("AOI has no valid geometries")

    # Dissolve to one feature per municipality name for script compatibility.
    gdf["MpNombre"] = str(request_name or "AOI")
    gdf["Depto"] = str(department or "")
    gdf = gdf.dissolve(by=["Depto", "MpNombre"], as_index=False)

    if out.exists():
        out.unlink()
    gdf.to_file(out, layer="aoi", driver="GPKG")
    return out


def order_paths(storage_path: str | Path, order_id: int) -> dict[str, Path]:
    root = Path(storage_path) / "fire" / f"order_{order_id}"
    s2 = root / "s2"
    results = root / "results"
    aoi = root / "aoi.gpkg"
    return {
        "root": root,
        "s2": s2,
        "results": results,
        "aoi": aoi,
    }
