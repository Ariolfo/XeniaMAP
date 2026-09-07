"""Casos de uso Agro: crop centro + enqueue de recortes S1/S2."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Sequence

import rasterio

from app.core.storage_paths import _tenant_storage
from app.domain.agro.repositories import LayerRepository
from app.core.celery_task_registry import register_celery_task
from app.services.preprocess_pipeline_variant import normalize_pipeline_variant


class CropRasterCenter:
    """Recorte centrado por ratio (endpoint legacy ``/preprocess/crop``)."""

    def execute(self, *, src_path: Path | str, out_path: Path | str, crop_ratio: float) -> str:
        src_path = Path(src_path)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        ratio = max(0.2, min(1.0, float(crop_ratio)))
        with rasterio.open(src_path) as src:
            h = int(src.height * ratio)
            w = int(src.width * ratio)
            r0 = (src.height - h) // 2
            c0 = (src.width - w) // 2
            window = rasterio.windows.Window(c0, r0, w, h)
            data = src.read(window=window)
            profile = src.profile.copy()
            profile.update(height=h, width=w, transform=src.window_transform(window))
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(data)
        return str(out_path)


def crop_output_path(tenant_id: int, project_id: int) -> Path:
    return _tenant_storage(tenant_id, project_id, "preprocess") / f"crop_{uuid.uuid4().hex}.tif"


def _require_project_layer(
    layers: LayerRepository,
    *,
    tenant_id: int,
    project_id: int,
    layer_id: int | None,
) -> None:
    if layer_id is None:
        return
    found = layers.get_by_id_for_project(
        layer_id, project_id=project_id, tenant_id=tenant_id
    )
    if not found:
        raise LookupError(f"No existe la capa vectorial {layer_id} en este proyecto.")


class EnqueueS1GrdRecortes:
    """Encola ``tasks.s1_grd_recortes_pipeline``."""

    def execute(
        self,
        *,
        layers: LayerRepository,
        tenant_id: int,
        project_id: int,
        project_name: str,
        layer_id: int | None,
        product_paths: Sequence[str] | None,
        source_subpath: str | None,
        database_url: str,
    ) -> dict[str, Any]:
        from app.tasks.jobs import s1_grd_recortes_pipeline

        _require_project_layer(
            layers, tenant_id=tenant_id, project_id=project_id, layer_id=layer_id
        )

        paths = [str(x).strip().replace("\\", "/") for x in (product_paths or []) if str(x).strip()]
        if not paths:
            raise ValueError("Indica al menos un producto (ruta bajo la carpeta origen).")

        try:
            async_result = s1_grd_recortes_pipeline.delay(
                tenant_id,
                project_id,
                project_name,
                layer_id,
                database_url,
                paths,
                source_subpath,
            )
        except Exception as exc:
            raise RuntimeError(
                "No se pudo encolar el recorte Sentinel-1. Comprueba Redis y el worker Celery. "
                f"Detalle: {exc!s}"
            ) from exc
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="s1_grd_recortes_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id}


class EnqueueS2L2aRecortes:
    """Encola ``tasks.s2_l2a_recortes_pipeline`` (WKT ya resuelto en el controller)."""

    def execute(
        self,
        *,
        layers: LayerRepository,
        tenant_id: int,
        project_id: int,
        project_name: str,
        layer_id: int | None,
        wkt: str | None,
        product_names: Sequence[str] | None,
        source_subpath: str | None,
        pipeline_variant: str,
        database_url: str,
    ) -> dict[str, Any]:
        from app.tasks.jobs import s2_l2a_recortes_pipeline

        _require_project_layer(
            layers, tenant_id=tenant_id, project_id=project_id, layer_id=layer_id
        )

        if not wkt:
            if layer_id is not None:
                raise ValueError(
                    f"No se pudo leer geometría para la capa {layer_id} "
                    "(archivo ausente o formato no soportado). Comprueba el lote o elige «Todos los lotes»."
                )
            raise ValueError("No hay polígono vectorial en el proyecto. Carga un lote antes.")

        try:
            async_result = s2_l2a_recortes_pipeline.delay(
                tenant_id,
                project_id,
                project_name,
                layer_id,
                database_url,
                list(product_names) if product_names is not None else None,
                source_subpath,
                normalize_pipeline_variant(pipeline_variant),
            )
        except Exception as exc:
            raise RuntimeError(
                "No se pudo encolar la tarea de recorte. Comprueba que Redis esté en marcha "
                f"y el worker Celery activo. Detalle: {exc!s}"
            ) from exc
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="s2_l2a_recortes_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id}
