"""Casos de uso Agro: publicar vectores en PostGIS y servir MVT (ADR-001)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.models.models import Layer
from app.domain.shared.ports import TileRenderPort
from app.infrastructure.composition import default_tile_render
from app.services.project_geometry import (
    _geometries_wgs84_from_geojson,
    layer_to_geojson,
)

logger = logging.getLogger(__name__)

# Nombre de source-layer en el protobuf MVT (MapLibre ``source-layer``).
MVT_SOURCE_LAYER = "published"
MVT_EXTENT = 4096
MVT_BUFFER = 64


def geometry_geojson_for_postgis(geojson_data: dict) -> str | None:
    """Una geometría GeoJSON (WGS84) a persistir en ``layers.geom``."""
    from shapely.geometry import GeometryCollection, mapping

    geoms = _geometries_wgs84_from_geojson(geojson_data)
    if not geoms:
        return None
    g = geoms[0] if len(geoms) == 1 else GeometryCollection(geoms)
    if not g.is_valid:
        g = g.buffer(0)
    if g.is_empty:
        return None
    return json.dumps(mapping(g))


def layer_geom_meta(db: Session, *, layer_ids: list[int]) -> dict[int, dict[str, Any]]:
    """``mvt_ready`` + bbox WGS84 ``[w,s,e,n]`` por layer id."""
    if not layer_ids:
        return {}
    stmt = text(
        """
        SELECT id,
               (geom IS NOT NULL) AS mvt_ready,
               CASE
                 WHEN geom IS NULL THEN NULL
                 ELSE ARRAY[
                   ST_XMin(geom)::float8,
                   ST_YMin(geom)::float8,
                   ST_XMax(geom)::float8,
                   ST_YMax(geom)::float8
                 ]
               END AS bbox
        FROM layers
        WHERE id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    rows = db.execute(stmt, {"ids": layer_ids}).mappings()
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        bbox = row["bbox"]
        if bbox is not None:
            bbox = [float(x) for x in bbox]
        out[int(row["id"])] = {
            "mvt_ready": bool(row["mvt_ready"]),
            "bbox": bbox,
        }
    return out


class SyncLayerGeom:
    """Lee el archivo de la capa y escribe ``layers.geom`` (EPSG:4326)."""

    def execute(self, db: Session, *, layer: Layer) -> dict[str, Any]:
        geo = layer_to_geojson(layer)
        if not geo:
            # Shapefile / ZIP shapefile vía geopandas
            from pathlib import Path

            from app.services.aoi_vector import geojson_from_vector_path

            fp = Path(layer.file_path)
            ext = fp.suffix.lower()
            if ext in {".shp", ".zip"} and fp.exists():
                try:
                    geo = geojson_from_vector_path(fp)
                except Exception as exc:
                    logger.info("SyncLayerGeom: no se pudo leer vector %s: %s", fp, exc)
                    geo = None
        if not geo:
            return {"ok": False, "mvt_ready": False, "bbox": None, "detail": "no_geojson"}

        geom_json = geometry_geojson_for_postgis(geo)
        if not geom_json:
            return {"ok": False, "mvt_ready": False, "bbox": None, "detail": "empty_geom"}

        db.execute(
            text(
                """
                UPDATE layers
                SET geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:gj)), 4326)
                WHERE id = :id
                  AND tenant_id = :tid
                  AND project_id = :pid
                """
            ),
            {
                "gj": geom_json,
                "id": layer.id,
                "tid": layer.tenant_id,
                "pid": layer.project_id,
            },
        )
        db.commit()
        meta = layer_geom_meta(db, layer_ids=[layer.id]).get(layer.id) or {
            "mvt_ready": False,
            "bbox": None,
        }
        return {
            "ok": bool(meta.get("mvt_ready")),
            "mvt_ready": bool(meta.get("mvt_ready")),
            "bbox": meta.get("bbox"),
            "detail": "synced" if meta.get("mvt_ready") else "update_failed",
        }


class RenderLayerMvtTile:
    """``ST_AsMVT`` para una capa publicada (lazy-sync si ``geom`` vacío) vía ``TileRenderPort``."""

    def __init__(self, tiles: TileRenderPort | None = None) -> None:
        self._tiles = tiles or default_tile_render()

    def execute(
        self,
        db: Session,
        *,
        layer: Layer,
        z: int,
        x: int,
        y: int,
        sync_if_missing: bool = True,
    ) -> bytes:
        if z < 0 or z > 22:
            raise ValueError("z fuera de rango")
        max_xy = 1 << z
        if x < 0 or y < 0 or x >= max_xy or y >= max_xy:
            raise ValueError("x/y fuera de rango para z")

        ready = layer_geom_meta(db, layer_ids=[layer.id]).get(layer.id, {}).get("mvt_ready")
        if not ready and sync_if_missing:
            SyncLayerGeom().execute(db, layer=layer)
            ready = layer_geom_meta(db, layer_ids=[layer.id]).get(layer.id, {}).get("mvt_ready")
        if not ready:
            raise LookupError("layer_geom_missing")

        return self._tiles.render_layer_mvt_tile(
            db,
            layer_id=int(layer.id),
            tenant_id=int(layer.tenant_id),
            project_id=int(layer.project_id),
            z=z,
            x=x,
            y=y,
            source_layer=MVT_SOURCE_LAYER,
            extent=MVT_EXTENT,
            buffer=MVT_BUFFER,
        )
