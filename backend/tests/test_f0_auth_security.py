"""F0/F2: bootstrap admins por env + OTP simulate sin filtrar OTP en JSON."""

from __future__ import annotations

import os

# CI / local sin .env completo: fijar antes de importar settings.
os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("OTP_SIMULATE", "1")
os.environ.setdefault("APP_ENV", "dev")


def test_bootstrap_admin_emails_from_env(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "Admin@Example.com, other@x.test")
    from app.core.config import Settings

    s = Settings(
        secret_key="ci-xeniamap-test-secret-key-do-not-use-in-prod",
        admin_emails="Admin@Example.com, other@x.test",
        app_env="dev",
        otp_simulate=False,
    )
    assert s.is_bootstrap_admin("admin@example.com")
    assert s.is_bootstrap_admin("other@x.test")
    assert not s.is_bootstrap_admin("nobody@x.test")


def test_otp_simulate_forbidden_in_production_settings():
    from app.core.config import Settings
    import pytest

    with pytest.raises(ValueError, match="OTP_SIMULATE"):
        Settings(
            secret_key="ci-xeniamap-test-secret-key-do-not-use-in-prod",
            app_env="production",
            otp_simulate=True,
        )


def test_request_otp_simulate_never_returns_debug_otp(monkeypatch):
    """F2: OTP_SIMULATE no debe incluir el código en la respuesta HTTP."""
    monkeypatch.setenv("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
    monkeypatch.setenv("OTP_SIMULATE", "1")
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.delenv("LOG_OTP", raising=False)
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    # Recargar settings con env actual
    from app.core import config as cfg

    monkeypatch.setattr(
        cfg,
        "settings",
        cfg.Settings(
            secret_key="ci-xeniamap-test-secret-key-do-not-use-in-prod",
            otp_simulate=True,
            app_env="dev",
        ),
    )
    from app.api.v1 import auth as auth_mod

    monkeypatch.setattr(auth_mod, "settings", cfg.settings)

    from app.main import app

    client = TestClient(app)
    try:
        res = client.post("/api/v1/auth/request-otp", json={"email": "cliente-otp@example.com"})
    except OperationalError:
        pytest.skip("Postgres no disponible (solo CI / stack local)")
    if res.status_code == 200:
        body = res.json()
        assert body.get("debug_otp") is None
        assert "no se expone" in (body.get("message") or "").lower() or "LOG_OTP" in (
            body.get("message") or ""
        )
