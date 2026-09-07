"""Adapter: JobQueuePort → Celery + registro task_id→tenant."""

from __future__ import annotations

from typing import Any

from app.core.celery_task_registry import register_celery_task


class CeleryJobQueue:
    def enqueue(
        self,
        task: Any,
        *args: Any,
        tenant_id: int,
        project_id: int | None = None,
        task_name: str | None = None,
        **kwargs: Any,
    ) -> str:
        name = task_name or getattr(task, "name", None) or getattr(task, "__name__", None)
        try:
            async_result = task.delay(*args, **kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"No se pudo encolar la tarea ({name}): ¿Redis/worker activos? {exc!s}"
            ) from exc
        tid = str(async_result.id)
        register_celery_task(
            tid,
            tenant_id=tenant_id,
            project_id=project_id,
            task_name=str(name) if name else None,
        )
        return tid
