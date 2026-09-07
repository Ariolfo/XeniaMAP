"""B1: routing Celery agro / fire sin renombrar tasks.fire_*."""
from __future__ import annotations

from app.tasks.queue_routing import (
    AGRO_TASK_NAMES,
    FIRE_TASK_NAMES,
    QUEUE_AGRO,
    QUEUE_FIRE,
    celery_task_routes,
    queue_for_task,
    routes_mapping,
)


def test_fire_task_names_unchanged_contract():
    assert FIRE_TASK_NAMES == (
        "tasks.fire_download_s2",
        "tasks.fire_process_dnbr",
        "tasks.fire_validate_firms",
    )


def test_queue_for_task_splits_contexts():
    for name in FIRE_TASK_NAMES:
        assert queue_for_task(name) == QUEUE_FIRE
    for name in AGRO_TASK_NAMES:
        assert queue_for_task(name) == QUEUE_AGRO
    assert queue_for_task("tasks.unknown_future") == QUEUE_AGRO


def test_celery_app_routes_and_default_queue():
    from app.tasks.celery_app import celery_app

    assert celery_app.conf.task_default_queue == QUEUE_AGRO
    routes = celery_app.conf.task_routes
    assert routes == celery_task_routes()
    for name in FIRE_TASK_NAMES:
        assert routes[name]["queue"] == QUEUE_FIRE


def test_routes_mapping_covers_known_tasks():
    mapping = routes_mapping()
    assert set(FIRE_TASK_NAMES).issubset(mapping)
    assert set(AGRO_TASK_NAMES).issubset(mapping)
    assert all(mapping[n] == QUEUE_FIRE for n in FIRE_TASK_NAMES)
    assert all(mapping[n] == QUEUE_AGRO for n in AGRO_TASK_NAMES)
