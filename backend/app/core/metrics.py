"""Métricas Prometheus de producto (FIRMS cache, Celery).

Se exponen en el proceso API vía ``GET /metrics`` (Instrumentator) y, en el
worker Celery, en un HTTP server dedicado (``CELERY_METRICS_PORT``, default 9101).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# FIRMS live cache (proceso API)
FIRMS_LIVE_CACHE_TOTAL = Counter(
    "xeniamap_firms_live_cache_total",
    "Consultas al cache FIRMS live por resultado",
    ["result"],  # hit | miss | stale_hit | stale_miss | disabled
)

# Celery — encolado desde API
CELERY_TASKS_ENQUEUED_TOTAL = Counter(
    "xeniamap_celery_tasks_enqueued_total",
    "Tareas Celery encoladas desde la API",
    ["task"],
)

# Celery — ejecución en worker (o en tests si se disparan signals)
CELERY_TASKS_TOTAL = Counter(
    "xeniamap_celery_tasks_total",
    "Tareas Celery finalizadas en el worker",
    ["task", "state"],
)

CELERY_TASK_DURATION_SECONDS = Histogram(
    "xeniamap_celery_task_duration_seconds",
    "Duración de tareas Celery en el worker",
    ["task"],
    buckets=(0.5, 1, 2, 5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)


def observe_firms_cache(result: str) -> None:
    label = str(result or "unknown").strip().lower() or "unknown"
    FIRMS_LIVE_CACHE_TOTAL.labels(result=label).inc()


def observe_celery_enqueued(task_name: str | None) -> None:
    name = str(task_name or "unknown").strip() or "unknown"
    # acortar nombres tipo tasks.download_sentinel2
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    CELERY_TASKS_ENQUEUED_TOTAL.labels(task=name).inc()


def observe_celery_finished(task_name: str | None, state: str | None, duration_sec: float | None) -> None:
    name = str(task_name or "unknown").strip() or "unknown"
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    st = str(state or "UNKNOWN").strip().upper() or "UNKNOWN"
    CELERY_TASKS_TOTAL.labels(task=name, state=st).inc()
    if duration_sec is not None and duration_sec >= 0:
        CELERY_TASK_DURATION_SECONDS.labels(task=name).observe(float(duration_sec))
