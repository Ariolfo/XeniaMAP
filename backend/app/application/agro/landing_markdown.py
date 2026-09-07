"""Casos de uso Agro: Markdown de landing (generación / listado / path de descarga)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.storage_paths import _tenant_storage

LANDING_MARKDOWN_NAMES: dict[str, str] = {
    "PS": "landing_narrativa_PS.md",
    "S1": "landing_narrativa_S1.md",
    "S2": "landing_narrativa_S2.md",
}

MAX_MD_MB = 4.9


class EnqueueLandingMarkdown:
    """Encola ``landing_markdown_pipeline`` y registra task_id→tenant."""

    def execute(self, *, tenant_id: int, project_id: int) -> dict[str, Any]:
        from app.core.celery_task_registry import register_celery_task
        from app.tasks.jobs import landing_markdown_pipeline

        try:
            async_result = landing_markdown_pipeline.delay(project_id)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar la generación de Markdown (Redis/worker): {exc!s}"
            ) from exc
        register_celery_task(
            async_result.id,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name="landing_markdown_pipeline",
        )
        return {"status": "queued", "task_id": async_result.id}


class ListLandingMarkdownFiles:
    """Lista Markdown generados bajo ``markdown/``."""

    def execute(self, *, tenant_id: int, project_id: int) -> dict[str, Any]:
        md_dir = _tenant_storage(tenant_id, project_id, "markdown")
        files: list[dict[str, Any]] = []
        for sensor, name in LANDING_MARKDOWN_NAMES.items():
            p = md_dir / name
            if not p.is_file():
                continue
            st = p.stat()
            files.append(
                {
                    "sensor": sensor,
                    "name": name,
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return {
            "project_id": project_id,
            "files": files,
            "max_md_mb": MAX_MD_MB,
        }


class ResolveLandingMarkdownPath:
    """Resuelve path absoluto de un Markdown por sensor (PS|S1|S2)."""

    def execute(self, *, tenant_id: int, project_id: int, sensor: str) -> Path:
        key = str(sensor or "").strip().upper()
        name = LANDING_MARKDOWN_NAMES.get(key)
        if not name:
            raise ValueError("sensor debe ser PS, S1 o S2")
        p = _tenant_storage(tenant_id, project_id, "markdown") / name
        if not p.is_file():
            raise FileNotFoundError(f"No existe {name}; genera los Markdown primero.")
        return p
