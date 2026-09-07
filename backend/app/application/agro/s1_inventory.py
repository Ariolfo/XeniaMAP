"""Casos de uso Agro: inventarios / previews S1 (preproceso + s1indices)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import rasterio

from app.core.celery_task_registry import register_celery_task
from app.core.storage_paths import _tenant_storage, project_s1_preproceso_dir
from app.services.raster_geo import render_raster_preview_png


def _safe_relative_under(root: Path, p: Path) -> str | None:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


_S1_IW_GRDH_SCENE_DATE = re.compile(r"S1[A-Z]_IW_GRDH_1SDV_(\d{8})T", re.IGNORECASE)

S1_PREP_VV_PREVIEW_PALETTES: dict[str, str] = {
    "spectral": "Spectral",
    "jet": "jet",
    "turbo": "turbo",
}

S1_PREP_SIGMA0_IMG: dict[str, str] = {
    "vv": "Sigma0_VV_db.img",
    "vh": "Sigma0_VH_db.img",
}

S1_SAR_INDEX_DIR_KEYS = frozenset({"RVI", "RFDI", "VV_VH", "VH_VV", "NRPB"})


def s1_preproceso_sort_key_from_path(path: Path) -> str:
    """Clave YYYY-MM-DD; prioriza fecha GRD en la ruta."""
    text = "/".join(path.parts)
    m = _S1_IW_GRDH_SCENE_DATE.search(text)
    if m:
        ymd = m.group(1)
        return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    except OSError:
        return "1900-01-01"


def canonical_s1_sar_index_dir_name(raw: str) -> str | None:
    u = raw.strip().upper().replace("/", "_")
    return u if u in S1_SAR_INDEX_DIR_KEYS else None


class ListS1PrepSigma0Inventory:
    """Lista ``Sigma0_*_db.img`` bajo ``s1preproceso/``."""

    def execute(self, *, tenant_id: int, project_id: int, pol: str = "vv") -> dict[str, Any]:
        p = str(pol or "vv").strip().lower()
        if p not in S1_PREP_SIGMA0_IMG:
            raise ValueError("pol debe ser vv o vh")
        basename = S1_PREP_SIGMA0_IMG[p]

        root = project_s1_preproceso_dir(tenant_id, project_id)
        if not root.is_dir():
            return {"items": [], "root_exists": False, "pol": p}

        items: list[dict] = []
        for path in sorted(root.rglob(basename)):
            if not path.is_file() or path.name != basename:
                continue
            rel = _safe_relative_under(root, path)
            if rel is None:
                continue
            items.append(
                {
                    "basename": path.name,
                    "relative_path": rel,
                    "sort_key": s1_preproceso_sort_key_from_path(path),
                }
            )
        items.sort(key=lambda x: (x["sort_key"], x["relative_path"]))
        return {"items": items, "root_exists": True, "pol": p}


class PreviewS1PrepSigma0Png:
    """PNG de sigma0 VV/VH en dB desde ENVI en ``s1preproceso/``."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        img_relpath: str | None,
        pol: str = "vv",
        palette: str = "spectral",
    ) -> bytes:
        p = str(pol or "vv").strip().lower()
        if p not in S1_PREP_SIGMA0_IMG:
            raise ValueError("pol debe ser vv o vh")
        expected_name = S1_PREP_SIGMA0_IMG[p]

        if img_relpath is None or not str(img_relpath).strip():
            raise ValueError("Indica path")

        root = project_s1_preproceso_dir(tenant_id, project_id).resolve()
        rel = Path(str(img_relpath).strip().replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Ruta relativa no válida")
        img_path = (root / rel).resolve()
        if not img_path.is_file() or not img_path.is_relative_to(root):
            raise LookupError(f"{expected_name} no encontrado")
        if img_path.name != expected_name:
            raise ValueError(f"El archivo debe ser {expected_name} para pol={p}")

        cmap_key = S1_PREP_VV_PREVIEW_PALETTES.get(str(palette or "spectral").strip().lower())
        if cmap_key is None:
            allowed = ", ".join(sorted(S1_PREP_VV_PREVIEW_PALETTES))
            raise ValueError(f"palette inválida; use: {allowed}")

        meta = {"preview_rgb_bands": [1, 1, 1], "index_preview_cmap": cmap_key}
        try:
            return render_raster_preview_png(
                img_path,
                layer_metadata=meta,
                index_palette_request=True,
            )
        except Exception as exc:
            raise ValueError(f"No se pudo generar la vista previa: {exc}") from exc


class ListS1PrepSarScenes:
    def execute(self, *, tenant_id: int, project_id: int) -> dict[str, Any]:
        from app.services.s1_sar_indices import discover_s1_prep_sar_scenes

        root = project_s1_preproceso_dir(tenant_id, project_id)
        items = discover_s1_prep_sar_scenes(tenant_id, project_id)
        return {"items": items, "root_exists": root.is_dir()}


class EnqueueS1SarIndexStacks:
    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        indices: Sequence[str],
        scene_vv_relpaths: Sequence[str],
        database_url: str,
    ) -> dict[str, Any]:
        from app.tasks.jobs import s1_sar_index_stacks_pipeline

        paths = [str(p).strip().replace("\\", "/") for p in scene_vv_relpaths if str(p).strip()]
        paths = list(dict.fromkeys(paths))
        if not paths:
            raise ValueError("Indica al menos una escena (ruta a Sigma0_VV_db.img)")

        try:
            async_result = s1_sar_index_stacks_pipeline.delay(
                tenant_id,
                project_id,
                list(indices),
                paths,
                database_url,
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar la tarea de índices SAR. ¿Redis y worker activos? {exc!s}"
            ) from exc
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="s1_sar_index_stacks_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id}


class ListS1SarIndexStacksInventory:
    def execute(self, *, tenant_id: int, project_id: int) -> dict[str, Any]:
        from app.services.s1_sar_indices import S1_SAR_STACKS_ROOT_NAME

        root = _tenant_storage(tenant_id, project_id, S1_SAR_STACKS_ROOT_NAME)
        if not root.is_dir():
            return {"items": []}

        items: list[dict] = []
        seen_rel: set[str] = set()
        for p in sorted(root.rglob("*.tif")):
            if "_cog" in p.name.lower() or not p.is_file():
                continue
            rel = _safe_relative_under(root, p)
            if rel is None or rel in seen_rel:
                continue
            parts = Path(rel).parts
            if len(parts) < 2:
                continue
            key = canonical_s1_sar_index_dir_name(parts[0])
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
        return {"items": items}


class PreviewS1SarIndexStackPng:
    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        stack_relpath: str | None,
        band: int | None = None,
        index_palette: int = 0,
    ) -> bytes:
        from app.services.s1_sar_indices import S1_SAR_STACKS_ROOT_NAME

        if stack_relpath is None or not str(stack_relpath).strip():
            raise ValueError("Indica path")

        root = _tenant_storage(tenant_id, project_id, S1_SAR_STACKS_ROOT_NAME).resolve()
        rel = Path(str(stack_relpath).strip().replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Ruta relativa no válida")
        tif_path = (root / rel).resolve()
        if not tif_path.is_file() or not tif_path.is_relative_to(root):
            raise LookupError("Stack SAR no encontrado")
        if "_cog" in tif_path.name.lower():
            raise ValueError("Usa el GeoTIFF fuente del stack")

        first_seg = rel.parts[0] if rel.parts else ""
        index_key = canonical_s1_sar_index_dir_name(first_seg) or first_seg
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
