"""Adapter: TileRenderPort → raster_geo / xyz_tiles / PostGIS MVT."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import text


class CompositeTileRenderAdapter:
    def render_raster_preview_png(
        self,
        path: Path,
        *,
        max_dim: int = 2048,
        layer_metadata: dict | None = None,
        index_palette_request: bool = False,
        rgb_bands_1based: tuple[int, int, int] | None = None,
    ) -> bytes:
        from app.services.raster_geo import render_raster_preview_png

        return render_raster_preview_png(
            path,
            max_dim=max_dim,
            layer_metadata=layer_metadata,
            index_palette_request=index_palette_request,
            rgb_bands_1based=rgb_bands_1based,
        )

    def render_fire_xyz_tile_png(
        self,
        path: Path,
        z: int,
        x: int,
        y: int,
        *,
        mode: str = "rgb",
        severity_class: int | None = None,
        index_cmap: str = "RdYlBu_r",
    ) -> bytes:
        from app.infrastructure.raster.xyz_tiles import render_fire_xyz_tile_png

        return render_fire_xyz_tile_png(
            path,
            z,
            x,
            y,
            mode=mode,
            severity_class=severity_class,
            index_cmap=index_cmap,
        )

    def render_layer_mvt_tile(
        self,
        db: Any,
        *,
        layer_id: int,
        tenant_id: int,
        project_id: int,
        z: int,
        x: int,
        y: int,
        source_layer: str = "published",
        extent: int = 4096,
        buffer: int = 64,
    ) -> bytes:
        row = db.execute(
            text(
                """
                SELECT ST_AsMVT(tile, :layer_name, :extent, 'geom') AS mvt
                FROM (
                  SELECT ST_AsMVTGeom(
                    ST_Transform(l.geom, 3857),
                    ST_TileEnvelope(:z, :x, :y),
                    :extent,
                    :buffer,
                    true
                  ) AS geom
                  FROM layers l
                  WHERE l.id = :id
                    AND l.tenant_id = :tid
                    AND l.project_id = :pid
                    AND l.geom IS NOT NULL
                    AND ST_Intersects(
                      l.geom,
                      ST_Transform(ST_TileEnvelope(:z, :x, :y), 4326)
                    )
                ) AS tile
                WHERE tile.geom IS NOT NULL
                """
            ),
            {
                "layer_name": source_layer,
                "extent": extent,
                "buffer": buffer,
                "z": z,
                "x": x,
                "y": y,
                "id": layer_id,
                "tid": tenant_id,
                "pid": project_id,
            },
        ).first()
        if not row or row[0] is None:
            return b""
        return bytes(row[0])
