from __future__ import annotations

import logging
import os
import time

from celery import Celery
from celery.signals import task_postrun, task_prerun, worker_ready

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery("xeniamap", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True

# Import task modules so the worker registers all @celery_app.task definitions.
# Without this, `celery -A app.tasks.celery_app.celery_app worker` only loads this file
# and tasks in jobs.py never get registered (KeyError: 'tasks.download_sentinel2').
from app.tasks import jobs  # noqa: E402, F401
from app.tasks import fire_jobs  # noqa: E402, F401

_task_started_at: dict[str, float] = {}


@worker_ready.connect
def _celery_metrics_http_server(**_kwargs) -> None:
    """Expone métricas del worker para scrape Prometheus (proceso distinto al API)."""
    try:
        from prometheus_client import start_http_server

        port = int(os.environ.get("CELERY_METRICS_PORT", "9101"))
        start_http_server(port)
        logger.info("Celery Prometheus metrics on :%s", port)
    except OSError as exc:
        # Puerto ya en uso (reload watchfiles) — no tumbar el worker.
        logger.warning("Celery metrics HTTP server not started: %s", exc)
    except Exception as exc:
        logger.warning("Celery metrics HTTP server failed: %s", exc)


@task_prerun.connect
def _celery_task_prerun(task_id=None, task=None, **_kwargs) -> None:
    if task_id:
        _task_started_at[str(task_id)] = time.perf_counter()


@task_postrun.connect
def _celery_task_postrun(task_id=None, task=None, state=None, **_kwargs) -> None:
    from app.core.metrics import observe_celery_finished

    started = _task_started_at.pop(str(task_id), None) if task_id else None
    duration = (time.perf_counter() - started) if started is not None else None
    name = getattr(task, "name", None) if task is not None else None
    observe_celery_finished(name, state, duration)
