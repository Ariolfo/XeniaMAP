from celery import Celery

from app.core.config import settings

celery_app = Celery("xeniamap", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_track_started = True

# Import task modules so the worker registers all @celery_app.task definitions.
# Without this, `celery -A app.tasks.celery_app.celery_app worker` only loads this file
# and tasks in jobs.py never get registered (KeyError: 'tasks.download_sentinel2').
from app.tasks import jobs  # noqa: E402, F401
