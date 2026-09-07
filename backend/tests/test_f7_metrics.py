"""F7: health + Prometheus /metrics."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("OTP_SIMULATE", "1")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_metrics_prometheus_exposed():
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Instrumentator exports process/http metrics
    assert "http_" in body or "python_" in body or "process_" in body
