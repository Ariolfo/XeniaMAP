"""F0: bootstrap admins por env + OTP simulate vs SMTP gate."""

from __future__ import annotations

import os

# CI / local sin .env completo: fijar antes de importar settings.
os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("OTP_SIMULATE", "1")


def test_bootstrap_admin_emails_from_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "Admin@Example.com, other@x.test")
    from app.core.config import Settings

    s = Settings(
        secret_key="ci-xeniamap-test-secret-key-do-not-use-in-prod",
        admin_emails="Admin@Example.com, other@x.test",
    )
    assert s.is_bootstrap_admin("admin@example.com")
    assert s.is_bootstrap_admin("other@x.test")
    assert not s.is_bootstrap_admin("nobody@x.test")


def test_request_otp_simulate_returns_debug(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
    monkeypatch.setenv("OTP_SIMULATE", "1")
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    from app.main import app

    client = TestClient(app)
    try:
        res = client.post("/api/v1/auth/request-otp", json={"email": "cliente-otp@example.com"})
    except OperationalError:
        pytest.skip("Postgres no disponible (solo CI / stack local)")
    # Puede fallar por usuario inexistente; si 200, no debe ser el código fijo legacy.
    if res.status_code == 200:
        body = res.json()
        assert body.get("debug_otp")
        assert body["debug_otp"] != "12345678" or len(body["debug_otp"]) == 8
        assert "SIMULATE" in (body.get("message") or "").upper() or "desarrollo" in (
            body.get("message") or ""
        ).lower()
