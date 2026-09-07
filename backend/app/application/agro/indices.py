"""Casos de uso Agro: índices de vegetación (simple + stacks S2)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import rasterio

from app.core.celery_task_registry import register_celery_task
from app.core.storage_paths import _tenant_storage
from app.services.preprocess_pipeline_variant import normalize_pipeline_variant

SUPPORTED_SIMPLE_INDICES = frozenset({"NDVI", "EVI", "NDWI"})


class ComputeSimpleVegetationIndex:
    """
    Índice monocapa a partir de un raster de proyecto (endpoint legacy ``/preprocess/indices``).
    """

    def execute(self, *, src_path: Path | str, out_path: Path | str, index_type: str) -> str:
        key = str(index_type or "").upper()
        if key not in SUPPORTED_SIMPLE_INDICES:
            raise ValueError("Unsupported index type")

        src_path = Path(src_path)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(src_path) as src:
            band = src.read(1).astype("float32")
            nir = band
            red = np.clip(band * 0.7, 1, 255)
            green = np.clip(band * 0.5, 1, 255)
            if key == "NDVI":
                idx = (nir - red) / (nir + red + 1e-6)
            elif key == "EVI":
                idx = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * green + 1)
            else:  # NDWI
                idx = (green - nir) / (green + nir + 1e-6)
            profile = src.profile.copy()
            profile.update(dtype="float32", count=1)
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(idx.astype("float32"), 1)
        return key


class EnqueueS2IndexStacks:
    """Encola ``tasks.s2_index_stacks_pipeline`` tras validar la lista de índices."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        indices: Sequence[str],
        database_url: str,
        raster_layer_ids: list[int] | None = None,
        recorte_filenames: list[str] | None = None,
        pipeline_variant: str = "s2",
    ) -> dict[str, Any]:
        from app.services.s2_vegetation_indices import normalize_requested_indices
        from app.tasks.jobs import s2_index_stacks_pipeline

        variant = normalize_pipeline_variant(pipeline_variant)
        pairs = normalize_requested_indices(indices, pipeline_variant=variant)
        if not pairs:
            raise ValueError("Selecciona al menos un índice (o TODOS).")

        rids = raster_layer_ids
        if rids is not None and len(rids) == 0:
            rids = None
        fnames = recorte_filenames
        if fnames is not None and len(fnames) == 0:
            fnames = None
        rids_eff = None if fnames else rids

        try:
            async_result = s2_index_stacks_pipeline.delay(
                tenant_id,
                project_id,
                list(indices),
                database_url,
                rids_eff,
                fnames,
                variant,
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar la tarea de índices. ¿Redis y worker activos? {exc!s}"
            ) from exc

        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="s2_index_stacks_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id}


def simple_index_output_path(tenant_id: int, project_id: int, index_type: str) -> Path:
    return (
        _tenant_storage(tenant_id, project_id, "preprocess")
        / f"{str(index_type).lower()}_{uuid.uuid4().hex}.tif"
    )
