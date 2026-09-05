"""Assert fire Celery tasks are registered after importing job modules."""
from __future__ import annotations

from app.tasks.celery_app import celery_app
import app.tasks.jobs  # noqa: F401
import app.tasks.fire_jobs  # noqa: F401


def test_fire_celery_tasks_registered() -> None:
    for name in (
        "tasks.fire_download_s2",
        "tasks.fire_process_dnbr",
        "tasks.fire_validate_firms",
    ):
        assert name in celery_app.tasks
