"""Casos de uso Agro: inventarios / previews de stacks ópticos (indices/ / indecesPS/)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import rasterio

from app.core.storage_paths import _tenant_storage
from app.services.preprocess_pipeline_variant import indices_dir_name, normalize_pipeline_variant
from app.services.raster_geo import render_raster_preview_png

# Carpetas bajo indices/ (S2) o indecesPS/ (Planet); debe coincidir con normalize_requested_indices.
PS_INDEX_DIR_NAMES = frozenset({"MSAVI2", "MTVI2", "VARI", "TGI", "KNDVI", "GIYI"})


def _safe_relative_under(root: Path, p: Path) -> str | None:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def canonical_index_dir_name(raw: str) -> str | None:
    """Carpeta bajo indices/ o indecesPS/ → clave estable (mismo criterio que el pipeline)."""
    u = raw.strip().upper()
    if u == "NDVI":
        return "NDVI"
    if u == "EVI":
        return "EVI"
    if u == "NDWI":
        return "NDWI"
    if u == "CIRE":
        return "CIre"
    if u == "MCARI":
        return "MCARI"
    if u == "NDRE":
        return "NDRE"
    if u == "RSTRUCTURE":
        return "RSTRUCTURE"
    if u in PS_INDEX_DIR_NAMES:
        return u
    return None


class ListIndexStacksInventory:
    """Lista GeoTIFF multibanda en ``indices/`` o ``indecesPS/`` (sin capas en BD)."""

    def execute(
        self, *, tenant_id: int, project_id: int, pipeline_variant: str = "s2"
    ) -> dict[str, Any]:
        pv = normalize_pipeline_variant(pipeline_variant)
        idx_kind = indices_dir_name(pv)
        indices_root = _tenant_storage(tenant_id, project_id, idx_kind)
        if not indices_root.is_dir():
            return {"items": [], "indices_dir": idx_kind, "pipeline_variant": pv}

        items: list[dict] = []
        seen_rel: set[str] = set()
        for p in sorted(indices_root.rglob("*.tif")):
            if "_cog" in p.name.lower() or not p.is_file():
                continue
            rel = _safe_relative_under(indices_root, p)
            if rel is None or rel in seen_rel:
                continue
            parts = Path(rel).parts
            if len(parts) < 2:
                continue
            key = canonical_index_dir_name(parts[0])
            if key is None:
                continue
            seen_rel.add(rel)
            try:
                with rasterio.open(p) as src:
                    bands = int(src.count)
                    tags = src.tags()
            except Exception:
                continue
            dates: list[str] = []
            jd = tags.get("BAND_DATES_JSON")
            if isinstance(jd, str) and jd.strip():
                try:
                    parsed = json.loads(jd)
                    if isinstance(parsed, list):
                        dates = [str(x) for x in parsed]
                except json.JSONDecodeError:
                    dates = []
            items.append(
                {
                    "index_key": key,
                    "relative_path": rel,
                    "bands": bands,
                    "band_dates": dates,
                }
            )
        items.sort(key=lambda x: (x["index_key"], x["relative_path"]))
        return {"items": items, "indices_dir": idx_kind, "pipeline_variant": pv}


class PreviewIndexStackPng:
    """PNG de una banda de un stack óptico en disco (no requiere RasterLayer)."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        stack_relpath: str | None,
        band: int | None = None,
        index_palette: int = 0,
        pipeline_variant: str = "s2",
    ) -> bytes:
        if stack_relpath is None or not str(stack_relpath).strip():
            raise ValueError("Indica path")

        root = _tenant_storage(
            tenant_id, project_id, indices_dir_name(pipeline_variant)
        ).resolve()
        rel = Path(str(stack_relpath).strip().replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Ruta relativa no válida")
        tif_path = (root / rel).resolve()
        if not tif_path.is_file() or not tif_path.is_relative_to(root):
            raise LookupError("Stack no encontrado")
        if "_cog" in tif_path.name.lower():
            raise ValueError("Usa el GeoTIFF fuente del stack")

        first_seg = rel.parts[0] if rel.parts else ""
        index_key = canonical_index_dir_name(first_seg) or first_seg
        meta = {
            "s2_index_stack": True,
            "vegetation_index_key": index_key,
            "preview_rgb_bands": [1, 1, 1],
            "index_preview_cmap": "RdYlGn",
        }
        rgb_override = (band, band, band) if band is not None else None
        try:
            return render_raster_preview_png(
                tif_path,
                layer_metadata=meta,
                rgb_bands_1based=rgb_override,
                index_palette_request=index_palette == 1,
            )
        except Exception as exc:
            raise ValueError(f"No se pudo generar la vista previa: {exc}") from exc
