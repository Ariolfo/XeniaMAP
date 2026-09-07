"""Casos de uso Agro: inventarios / previews de recortes/ y recortesPS/."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import rasterio

from app.core.storage_paths import _tenant_storage
from app.domain.agro.repositories import RasterLayerRepository
from app.models.models import RasterLayer
from app.services.preprocess_pipeline_variant import (
    is_planetscope_ps_recorte_filename,
    normalize_pipeline_variant,
    recortes_dir_name,
)
from app.services.raster_geo import render_raster_preview_png
from app.services.s2_vegetation_indices import sort_key_from_path_or_meta


def _safe_relative_under(root: Path, p: Path) -> str | None:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


class ListRecortesInventory:
    """
    Lista GeoTIFF bajo ``recortes/`` o ``recortesPS/`` con ≥6 bandas.
    Enlaza ``raster_layer_id`` por path resuelto, basename o ``metadata.source_name``.
    """

    def execute(
        self,
        raster_layers: RasterLayerRepository,
        *,
        tenant_id: int,
        project_id: int,
        pipeline_variant: str = "s2",
    ) -> dict[str, Any]:
        pv = normalize_pipeline_variant(pipeline_variant)
        rec_kind = recortes_dir_name(pv)
        recortes_root = _tenant_storage(tenant_id, project_id, rec_kind)
        if not recortes_root.is_dir():
            return {"items": [], "recortes_dir": rec_kind, "pipeline_variant": pv}

        resolved_to_rid: dict[Path, int] = {}
        name_to_rid: dict[str, int] = {}
        source_basename_to_rid: dict[str, int] = {}
        for r in raster_layers.list_for_project(project_id=project_id, tenant_id=tenant_id):
            om = r.raster_metadata or {}
            sn = (om.get("source_name") or "").strip()
            if sn:
                sb = Path(sn).name
                if sb.lower().endswith(".tif") and "_cog" not in sb.lower():
                    source_basename_to_rid.setdefault(sb, r.id)
            nm = (r.name or "").strip()
            if nm and is_planetscope_ps_recorte_filename(nm):
                source_basename_to_rid.setdefault(Path(nm).name, r.id)
            for attr in (r.file_path, r.cog_path):
                if not attr:
                    continue
                fp = Path(attr)
                bn = fp.name
                if "_cog" in bn.lower() or not bn.lower().endswith(".tif"):
                    continue
                if fp.is_file():
                    try:
                        resolved_to_rid[fp.resolve()] = r.id
                    except OSError:
                        pass
                if bn not in name_to_rid:
                    name_to_rid[bn] = r.id

        items: list[dict] = []
        for p in sorted(recortes_root.rglob("*.tif")):
            if "_cog" in p.name.lower() or not p.is_file():
                continue
            if pv == "ps" and not is_planetscope_ps_recorte_filename(p.name):
                continue
            rel = _safe_relative_under(recortes_root, p)
            if rel is None:
                continue
            try:
                with rasterio.open(p) as src:
                    bands = int(src.count)
            except Exception:
                continue
            if bands < 6:
                continue
            sk = sort_key_from_path_or_meta(p, None)
            if not sk:
                try:
                    sk = datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()
                except OSError:
                    sk = "1900-01-01"
            rid = resolved_to_rid.get(p.resolve())
            if rid is None:
                rid = name_to_rid.get(p.name)
            if rid is None:
                rid = source_basename_to_rid.get(p.name)
            items.append(
                {
                    "basename": p.name,
                    "relative_path": rel,
                    "bands": bands,
                    "sort_key": sk,
                    "raster_layer_id": rid,
                }
            )
        items.sort(key=lambda x: (x["sort_key"], x["relative_path"]))
        return {"items": items, "recortes_dir": rec_kind, "pipeline_variant": pv}


class PreviewRecortePng:
    """Vista RGB desde GeoTIFF en ``recortes/`` o ``recortesPS/``."""

    def execute(
        self,
        raster_layers: RasterLayerRepository,
        *,
        tenant_id: int,
        project_id: int,
        recorte_relpath: str | None = None,
        name: str | None = None,
        pipeline_variant: str = "s2",
    ) -> bytes:
        root = _tenant_storage(
            tenant_id, project_id, recortes_dir_name(pipeline_variant)
        ).resolve()
        pv = normalize_pipeline_variant(pipeline_variant)

        if recorte_relpath is not None and str(recorte_relpath).strip():
            rel = Path(str(recorte_relpath).strip().replace("\\", "/"))
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("Ruta relativa no válida")
            full_path = (root / rel).resolve()
            if not full_path.is_file() or not full_path.is_relative_to(root):
                raise LookupError("GeoTIFF no encontrado en la carpeta de recortes del variant")
            tif_path = full_path
            basename = tif_path.name
        elif name is not None and str(name).strip():
            raw = str(name).strip()
            if not raw or ".." in raw or "/" in raw or "\\" in raw:
                raise ValueError("Nombre de archivo no válido")
            basename = Path(raw).name
            if basename != raw:
                raise ValueError("Usa solo el nombre del archivo")
            tif_path = (root / basename).resolve()
            if not tif_path.is_file() or tif_path.parent != root:
                raise LookupError("GeoTIFF no encontrado en la carpeta de recortes del variant")
        else:
            raise ValueError("Indica path o name")

        if "_cog" in basename.lower():
            raise ValueError("Usa el GeoTIFF fuente, no el COG")

        if pv == "ps" and not is_planetscope_ps_recorte_filename(basename):
            raise ValueError(
                "Solo se admiten GeoTIFF con nombre PS_dd-mm-yy.tif (p. ej. PS_23-03-26.tif)."
            )

        meta: dict | None = None
        layer_match: RasterLayer | None = None
        layers_q = raster_layers.list_for_project(project_id=project_id, tenant_id=tenant_id)
        try:
            tif_r = tif_path.resolve()
        except OSError:
            tif_r = tif_path
        for r in layers_q:
            for attr in (r.file_path, r.cog_path):
                if not attr:
                    continue
                ap = Path(attr)
                try:
                    if ap.is_file() and ap.resolve() == tif_r:
                        layer_match = r
                        break
                except OSError:
                    continue
            if layer_match is not None:
                break
        if layer_match is None:
            for r in layers_q:
                for attr in (r.file_path, r.cog_path):
                    if attr and Path(attr).name == basename:
                        layer_match = r
                        break
                if layer_match is not None:
                    break
        if layer_match is None:
            for r in layers_q:
                om = r.raster_metadata or {}
                sn = (om.get("source_name") or "").strip()
                if sn and Path(sn).name == basename:
                    layer_match = r
                    break
        if layer_match is None:
            for r in layers_q:
                nm = (r.name or "").strip()
                if nm and Path(nm).name == basename and is_planetscope_ps_recorte_filename(nm):
                    layer_match = r
                    break

        if layer_match is not None:
            meta = layer_match.raster_metadata or {}
        else:
            meta = {"preview_rgb_bands": [3, 2, 1], "s2_l2a_recorte": True}

        render_path = tif_path
        if pv == "ps":
            try:
                with rasterio.open(render_path) as _chk:
                    n_ps = int(_chk.count)
            except Exception:
                n_ps = 0
            if n_ps >= 6:
                meta = {
                    "preview_rgb_bands": [6, 4, 2],
                    "planetscope_composite": True,
                    "source_name": basename,
                }

        try:
            return render_raster_preview_png(render_path, layer_metadata=meta)
        except Exception as exc:
            raise ValueError(f"No se pudo generar la vista previa: {exc}") from exc
