"""Casos de uso: listado / stats / paths / preview de resultados Fire."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd

from app.application.fire.catalog import FIRE_RESULT_CATALOG, allowed_result_filenames, catalog_entry
from app.core.config import settings
from app.domain.shared.ports import TileRenderPort

logger = logging.getLogger(__name__)


def fire_storage_root(order_id: int) -> Path:
    root = Path(settings.storage_path) / "fire" / f"order_{order_id}" / "s2"
    root.mkdir(parents=True, exist_ok=True)
    return root


def fire_results_root(order_id: int, *, create: bool = True) -> Path:
    root = Path(settings.storage_path) / "fire" / f"order_{order_id}" / "results"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def safe_result_path(order_id: int, filename: str) -> Path:
    """Resuelve un archivo de catálogo bajo results/. Raises LookupError / ValueError."""
    name = Path(str(filename or "")).name
    if name not in allowed_result_filenames():
        raise LookupError("Capa Fire no permitida")
    root = fire_results_root(order_id, create=False)
    path = (root / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise LookupError("Ruta inválida") from exc
    if not path.is_file():
        raise LookupError("Archivo de resultado no encontrado")
    return path


class ListFireResultLayers:
    def execute(self, *, order_id: int, request_name: str) -> dict[str, Any]:
        from app.services.raster_geo import BURN_SEVERITY_CLASS_LABELS, BURN_SEVERITY_CLASS_RGB

        root = fire_results_root(order_id, create=False)
        layers: list[dict[str, Any]] = []
        for item in FIRE_RESULT_CATALOG:
            if item.get("ui_nested_only"):
                continue
            path = root / item["filename"]
            entry: dict[str, Any] = {
                "filename": item["filename"],
                "label": item["label"],
                "kind": item["kind"],
                "default_on": bool(item.get("default_on")),
                "available": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
                "severity_class_group": bool(item.get("severity_class_group")),
                "map_symbol": item.get("map_symbol"),
            }
            if item.get("severity_class_group"):
                sev_path = root / "Fire_burn_severity.tif"
                entry["severity_classes"] = [
                    {
                        "class_id": cid,
                        "label": BURN_SEVERITY_CLASS_LABELS[cid],
                        "color": "#{:02x}{:02x}{:02x}".format(*BURN_SEVERITY_CLASS_RGB[cid]),
                        "default_on": cid >= 4,
                        "available": sev_path.is_file(),
                        "source_filename": "Fire_burn_severity.tif",
                    }
                    for cid in range(1, 8)
                ]
            layers.append(entry)
        return {
            "order_id": order_id,
            "request_name": request_name,
            "results_root": str(root) if root.exists() else None,
            "layers": layers,
        }


class FireResultStats:
    def execute(self, *, order_id: int, request_name: str) -> dict[str, Any]:
        root = fire_results_root(order_id, create=False)
        rows: list[dict[str, Any]] = []
        for item in FIRE_RESULT_CATALOG:
            if not item.get("stats"):
                continue
            path = root / item["filename"]
            entry: dict[str, Any] = {
                "filename": item["filename"],
                "label": item["label"],
                "available": path.is_file(),
                "feature_count": None,
                "area_ha": None,
                "area_km2": None,
            }
            if path.is_file():
                try:
                    gdf = gpd.read_file(path)
                    entry["feature_count"] = int(len(gdf))
                    is_points = bool(item.get("stats_kind") == "points") or (
                        len(gdf) > 0
                        and gdf.geometry.geom_type.isin(["Point", "MultiPoint"]).all()
                    )
                    if is_points:
                        entry["area_ha"] = None
                        entry["area_km2"] = None
                    elif "area_ha" in gdf.columns:
                        ha = float(gdf["area_ha"].fillna(0).sum())
                        entry["area_ha"] = round(ha, 2)
                        entry["area_km2"] = round(ha / 100.0, 4)
                    else:
                        projected = gdf
                        if projected.crs is None:
                            projected = projected.set_crs(4326)
                        try:
                            projected = projected.to_crs(9377)
                        except Exception:
                            projected = projected.to_crs(3857)
                        ha = float(projected.geometry.area.sum()) / 10000.0
                        entry["area_ha"] = round(ha, 2)
                        entry["area_km2"] = round(ha / 100.0, 4)
                except Exception as exc:
                    logger.warning("fire stats %s: %s", path, exc)
                    entry["available"] = False
            rows.append(entry)
        return {
            "order_id": order_id,
            "request_name": request_name,
            "layers": rows,
        }


class FireResultGeojson:
    def execute(self, *, order_id: int, filename: str) -> dict[str, Any]:
        path = safe_result_path(order_id, filename)
        if path.suffix.lower() != ".gpkg":
            raise ValueError("Solo GPKG como GeoJSON")
        gdf = gpd.read_file(path)
        if gdf.crs is not None:
            gdf = gdf.to_crs(4326)
        return json.loads(gdf.to_json())


class FireResultPreview:
    """PNG / bounds para raster Fire (format=json|meta|png)."""

    def execute(
        self,
        *,
        order_id: int,
        filename: str,
        severity_class: int | None = None,
        format: str = "json",
        include_png: bool = False,
    ) -> tuple[str, Any]:
        """Returns ``(kind, payload)`` where kind is ``png`` or ``json``."""
        from app.services.raster_geo import (
            bounds_wgs84_from_path,
            render_burn_severity_discrete_png,
            render_display_ready_rgb_preview_png,
            render_raster_preview_png,
        )

        path = safe_result_path(order_id, filename)
        if path.suffix.lower() not in {".tif", ".tiff"}:
            raise ValueError("Solo GeoTIFF como preview")
        catalog = catalog_entry(path.name)
        meta = dict(catalog.get("preview_meta") or {}) if catalog else {}
        index_palette = bool(catalog.get("index_palette")) if catalog else False
        display_ready = bool(catalog.get("display_ready_uint8")) if catalog else False
        discrete_sev = bool(catalog.get("discrete_severity")) if catalog else False
        if severity_class is not None and (severity_class < 1 or severity_class > 7):
            raise ValueError("severity_class debe estar entre 1 y 7")
        fmt = str(format or "json").strip().lower()
        if fmt not in {"json", "meta", "png"}:
            raise ValueError("format debe ser json, meta o png")

        bounds = bounds_wgs84_from_path(path)
        need_png = fmt == "png" or (fmt == "json" and include_png)
        png = None
        if need_png:
            if discrete_sev or severity_class is not None:
                if path.name != "Fire_burn_severity.tif":
                    raise ValueError("severity_class solo aplica a Fire_burn_severity.tif")
                png = render_burn_severity_discrete_png(
                    path, max_dim=1536, only_class=severity_class
                )
            elif display_ready:
                png = render_display_ready_rgb_preview_png(path, max_dim=1536, nodata=0)
            else:
                png = render_raster_preview_png(
                    path,
                    max_dim=1536,
                    layer_metadata=meta,
                    index_palette_request=index_palette,
                )
        if not bounds:
            raise ValueError("Raster sin bounds WGS84")
        w, s, e, n = [float(x) for x in bounds]
        bounds_list = [w, s, e, n]
        if fmt == "png":
            assert png is not None
            return (
                "png",
                {
                    "content": png,
                    "bounds": bounds_list,
                    "filename": path.name,
                },
            )
        body: dict[str, Any] = {
            "filename": path.name,
            "bounds": bounds_list,
            "severity_class": severity_class,
            "content_type": "image/png",
        }
        if fmt == "json" and include_png and png is not None:
            body["png_base64"] = base64.b64encode(png).decode("ascii")
        return ("json", body)


class FireResultXyzTile:
    def __init__(self, tiles: TileRenderPort | None = None) -> None:
        from app.infrastructure.composition import default_tile_render

        self._tiles = tiles or default_tile_render()

    def execute(
        self,
        *,
        order_id: int,
        filename: str,
        z: int,
        x: int,
        y: int,
        severity_class: int | None = None,
    ) -> bytes:
        if z < 0 or z > 22 or x < 0 or y < 0:
            raise ValueError("tile z/x/y inválido")
        path = safe_result_path(order_id, filename)
        if path.suffix.lower() not in {".tif", ".tiff"}:
            raise ValueError("Solo GeoTIFF como tiles")
        # F6: órdenes antiguas sin COG — optimizar bajo demanda (una vez).
        try:
            from app.infrastructure.raster.cog import ensure_fire_analysis_cogs

            ensure_fire_analysis_cogs(path)
        except Exception:
            pass
        catalog = catalog_entry(path.name)
        if severity_class is not None and (severity_class < 1 or severity_class > 7):
            raise ValueError("severity_class debe estar entre 1 y 7")

        discrete_sev = bool(catalog.get("discrete_severity")) if catalog else False
        index_palette = bool(catalog.get("index_palette")) if catalog else False
        if discrete_sev or severity_class is not None:
            mode = "severity"
        elif index_palette:
            mode = "index"
        else:
            mode = "rgb"
        cmap = "RdYlBu_r"
        if catalog and isinstance(catalog.get("preview_meta"), dict):
            cmap = str(catalog["preview_meta"].get("index_preview_cmap") or cmap)

        return self._tiles.render_fire_xyz_tile_png(
            path,
            z,
            x,
            y,
            mode=mode,
            severity_class=severity_class,
            index_cmap=cmap,
        )
