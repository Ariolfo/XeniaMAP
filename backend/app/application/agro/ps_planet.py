"""Casos de uso Agro: flujo PlanetScope (ZIP extract, inventario, recorte, ST cluster)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import rasterio
from sqlalchemy.orm import Session

from app.core.celery_task_registry import register_celery_task
from app.core.storage_paths import _tenant_storage, resolve_source_subpath
from app.models.models import Layer
from app.services.preprocess_pipeline_variant import indices_dir_name
from app.services.ps_spatiotemporal_cluster import (
    cluster_map_to_png,
    get_preset,
    load_meta,
    run_ps_spatiotemporal_cluster,
)

logger = logging.getLogger(__name__)


class EnqueuePsPlanetZipExtract:
    """Encola ``tasks.ps_planet_zip_extract_pipeline``."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        source_subpath: str | None,
    ) -> dict[str, Any]:
        from app.tasks.jobs import ps_planet_zip_extract_pipeline

        try:
            async_result = ps_planet_zip_extract_pipeline.delay(
                tenant_id,
                project_id,
                source_subpath,
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar la extracción PS. ¿Redis y worker Celery? {exc!s}"
            ) from exc
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="ps_planet_zip_extract_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id}


class ListPsTifInventory:
    """Lista GeoTIFF en ``rasterPS/`` o ``recortesPS/`` (o ruta ``source_subpath``)."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        source: str = "rasterPS",
        source_subpath: str | None = None,
    ) -> dict[str, Any]:
        from app.services.ps_recorte_clip import (
            list_ps_clip_tifs,
            normalize_ps_clip_source,
            ps_clip_source_dir_name,
        )

        kind = normalize_ps_clip_source(source)
        dir_label = ps_clip_source_dir_name(kind)

        if source_subpath is None:
            root = _tenant_storage(tenant_id, project_id, dir_label)
        else:
            root = resolve_source_subpath(tenant_id, project_id, source_subpath)
            if root is None:
                raise ValueError("Ruta de origen inválida o fuera del alcance permitido")

        exists = root.is_dir()
        items: list[dict[str, Any]] = []
        if exists:
            for p in list_ps_clip_tifs(root, kind):
                bands = None
                try:
                    with rasterio.open(p) as src:
                        bands = int(src.count)
                except Exception:
                    bands = None
                items.append(
                    {
                        "basename": p.name,
                        "name": p.name,
                        "bands": bands,
                        "size_bytes": p.stat().st_size if p.is_file() else None,
                    }
                )
        return {
            "items": items,
            "source": kind,
            "dir": dir_label,
            "exists": exists,
            "path": str(root),
        }


def parse_filenames_json(filenames_json: str | None) -> list[str] | None:
    """Parsea JSON array de basenames; None si vacío. ValueError si inválido."""
    if filenames_json is None or not str(filenames_json).strip():
        return None
    try:
        parsed = json.loads(filenames_json)
    except json.JSONDecodeError as exc:
        raise ValueError("filenames_json no es JSON válido") from exc
    if not isinstance(parsed, list):
        raise ValueError("filenames_json debe ser un array")
    filenames = [str(x).strip() for x in parsed if str(x).strip()]
    if not filenames:
        raise ValueError("Selecciona al menos un TIF")
    return filenames


class EnqueuePsRecorteClip:
    """Encola ``tasks.ps_recorte_clip_pipeline`` (WKT ya resuelto en el controller)."""

    def execute(
        self,
        *,
        db: Session,
        tenant_id: int,
        project_id: int,
        wkt: str | None,
        source: str,
        filenames: list[str] | None,
        source_subpath: str | None,
        layer_id: int | None = None,
        require_layer_exists: bool = True,
    ) -> dict[str, Any]:
        from app.services.ps_recorte_clip import normalize_ps_clip_source
        from app.tasks.jobs import ps_recorte_clip_pipeline

        kind = normalize_ps_clip_source(source)

        if require_layer_exists and layer_id is not None:
            found = (
                db.query(Layer)
                .filter(
                    Layer.id == layer_id,
                    Layer.project_id == project_id,
                    Layer.tenant_id == tenant_id,
                )
                .first()
            )
            if not found:
                raise LookupError(f"No existe la capa vectorial {layer_id} en este proyecto.")

        if not wkt:
            if layer_id is not None:
                raise ValueError(
                    f"No se pudo leer geometría para la capa {layer_id} "
                    "(archivo ausente o formato no soportado)."
                )
            raise ValueError(
                "No hay polígono vectorial en el proyecto. Carga un lote o sube un AOI "
                "(GeoJSON / ZIP shapefile)."
            )

        try:
            async_result = ps_recorte_clip_pipeline.delay(
                tenant_id,
                project_id,
                wkt,
                kind,
                filenames,
                source_subpath,
            )
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar el recorte PS. ¿Redis y worker Celery? {exc!s}"
            ) from exc
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="ps_recorte_clip_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id, "source": kind}


def _resolve_st_cluster_out_dir(tenant_id: int, project_id: int, preset: str) -> tuple[Any, Path]:
    pr = get_preset(preset)
    out_dir = _tenant_storage(tenant_id, project_id, pr.output_subdir)
    if not out_dir.is_dir():
        for legacy_subdir in pr.legacy_output_subdirs:
            legacy_dir = _tenant_storage(tenant_id, project_id, legacy_subdir)
            if legacy_dir.is_dir():
                out_dir = legacy_dir
                break
    return pr, out_dir


class RunPsSpatiotemporalCluster:
    """Ejecuta pipeline KMeans espacial-temporal PlanetScope (sync)."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        preset: str = "smart1",
        n_clusters: int = 4,
        random_state: int = 42,
    ) -> dict[str, Any]:
        pr = get_preset(preset)
        index_root = _tenant_storage(tenant_id, project_id, indices_dir_name("ps"))
        out_dir = _tenant_storage(tenant_id, project_id, pr.output_subdir)
        try:
            meta = run_ps_spatiotemporal_cluster(
                index_root,
                out_dir,
                preset_id=pr.id,
                n_clusters=n_clusters,
                random_state=random_state,
            )
        except ValueError:
            raise
        except Exception as exc:
            logger.exception("ps_spatiotemporal_cluster failed")
            raise RuntimeError(f"Error en pipeline: {exc!s}") from exc
        return {"status": "ok", "meta": meta}


class GetPsSpatiotemporalClusterStatus:
    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        preset: str = "smart1",
    ) -> dict[str, Any]:
        pr, out_dir = _resolve_st_cluster_out_dir(tenant_id, project_id, preset)
        map_path = out_dir / "final_cluster_map.tif"
        return {
            "ready": map_path.is_file(),
            "preset": pr.id,
            "meta": load_meta(out_dir),
        }


class GetPsSpatiotemporalClusterPreviewPng:
    """Devuelve bytes PNG del mapa de clusters."""

    def execute(
        self,
        *,
        tenant_id: int,
        project_id: int,
        preset: str = "smart1",
    ) -> bytes:
        pr, out_dir = _resolve_st_cluster_out_dir(tenant_id, project_id, preset)
        map_path = out_dir / "final_cluster_map.tif"
        if not map_path.is_file():
            for legacy_subdir in pr.legacy_output_subdirs:
                legacy_map_path = (
                    _tenant_storage(tenant_id, project_id, legacy_subdir) / "final_cluster_map.tif"
                )
                if legacy_map_path.is_file():
                    map_path = legacy_map_path
                    break
        if not map_path.is_file():
            raise LookupError("Aún no hay mapa de cluster. Ejecuta POST ps-spatiotemporal-cluster.")
        try:
            return cluster_map_to_png(map_path.resolve())
        except Exception as exc:
            raise ValueError(f"No se pudo generar la vista previa: {exc!s}") from exc
