"""Colas Celery por bounded context (B1) — sin renombrar ``tasks.fire_*``."""

from __future__ import annotations

from typing import Mapping

# Nombres de cola Redis/Celery (estables para extracción futura).
QUEUE_AGRO = "agro"
QUEUE_FIRE = "fire"

# Nombres Celery canónicos Fire — NO renombrar (contrato ops / clientes).
FIRE_TASK_NAMES: tuple[str, ...] = (
    "tasks.fire_download_s2",
    "tasks.fire_process_dnbr",
    "tasks.fire_validate_firms",
)

# Tareas Agro/shared en ``tasks/jobs.py`` (cola default agro).
AGRO_TASK_NAMES: tuple[str, ...] = (
    "tasks.process_raster",
    "tasks.process_s2_zip_layers",
    "tasks.mock_inference",
    "tasks.download_sentinel2",
    "tasks.download_sentinel1",
    "tasks.s2_l2a_recortes_pipeline",
    "tasks.s1_grd_recortes_pipeline",
    "tasks.s2_index_stacks_pipeline",
    "tasks.s1_sar_index_stacks_pipeline",
    "tasks.ps_planet_zip_extract_pipeline",
    "tasks.ps_recorte_clip_pipeline",
    "tasks.landing_markdown_pipeline",
    "tasks.soilplus_execute_save",
)


def celery_task_routes() -> dict[str, dict[str, str]]:
    """Rutas explícitas Fire → ``fire``; el resto cae en ``task_default_queue=agro``."""
    return {name: {"queue": QUEUE_FIRE} for name in FIRE_TASK_NAMES}


def queue_for_task(task_name: str) -> str:
    """Resuelve cola de una tarea registrada (útil en tests / docs)."""
    if task_name in FIRE_TASK_NAMES:
        return QUEUE_FIRE
    return QUEUE_AGRO


def routes_mapping() -> Mapping[str, str]:
    """Nombre de tarea → cola (incluye Agro explícito para documentación/tests)."""
    out: dict[str, str] = {n: QUEUE_AGRO for n in AGRO_TASK_NAMES}
    out.update({n: QUEUE_FIRE for n in FIRE_TASK_NAMES})
    return out
