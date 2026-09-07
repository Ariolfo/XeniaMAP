"""Métricas producto: FIRMS cache + Celery enqueue."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("OTP_SIMULATE", "1")

from fastapi.testclient import TestClient

from app.core import metrics as m
from app.core.celery_task_registry import register_celery_task
from app.infrastructure.firms import live_cache as lc
from app.main import app

client = TestClient(app)


def test_firms_cache_hit_miss_metrics(monkeypatch):
    monkeypatch.setattr(lc, "_redis", lambda: None)
    lc._mem.clear()
    monkeypatch.setattr(
        "app.core.config.settings.firms_live_cache_ttl_sec",
        300,
        raising=False,
    )

    before_miss = m.FIRMS_LIVE_CACHE_TOTAL.labels(result="miss")._value.get()
    assert lc.get_firms_live_cached(1, 24) is None
    after_miss = m.FIRMS_LIVE_CACHE_TOTAL.labels(result="miss")._value.get()
    assert after_miss == before_miss + 1

    lc.set_firms_live_cached(1, 24, {"hotspots": []})
    before_hit = m.FIRMS_LIVE_CACHE_TOTAL.labels(result="hit")._value.get()
    got = lc.get_firms_live_cached(1, 24)
    assert got is not None
    after_hit = m.FIRMS_LIVE_CACHE_TOTAL.labels(result="hit")._value.get()
    assert after_hit == before_hit + 1


def test_celery_enqueue_metric_and_exposed():
    before = m.CELERY_TASKS_ENQUEUED_TOTAL.labels(task="download_sentinel2")._value.get()
    register_celery_task(
        "metric-test-task-id",
        tenant_id=1,
        project_id=2,
        task_name="download_sentinel2",
    )
    after = m.CELERY_TASKS_ENQUEUED_TOTAL.labels(task="download_sentinel2")._value.get()
    assert after == before + 1

    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "xeniamap_firms_live_cache_total" in body
    assert "xeniamap_celery_tasks_enqueued_total" in body


def test_observe_celery_finished_histogram():
    before = m.CELERY_TASKS_TOTAL.labels(task="fire_download_s2", state="SUCCESS")._value.get()
    m.observe_celery_finished("tasks.fire_download_s2", "SUCCESS", 1.25)
    after = m.CELERY_TASKS_TOTAL.labels(task="fire_download_s2", state="SUCCESS")._value.get()
    assert after == before + 1
    body = client.get("/metrics").text
    assert "xeniamap_celery_task_duration_seconds" in body
