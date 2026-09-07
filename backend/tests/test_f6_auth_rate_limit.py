"""F6: rate limit auth fail-closed + bucket bajo."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("APP_ENV", "dev")

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.rate_limit import is_auth_rate_limited_path


def test_is_auth_rate_limited_path():
    assert is_auth_rate_limited_path("/api/v1/auth/login", api_prefix="/api/v1")
    assert is_auth_rate_limited_path("/api/v1/auth/request-otp", api_prefix="/api/v1")
    assert is_auth_rate_limited_path("/api/v1/auth/check-email", api_prefix="/api/v1")
    assert not is_auth_rate_limited_path("/api/v1/auth/me", api_prefix="/api/v1")
    assert not is_auth_rate_limited_path("/api/v1/projects", api_prefix="/api/v1")
    assert not is_auth_rate_limited_path("/health", api_prefix="/api/v1")


def test_auth_rate_limit_fail_closed_without_redis(monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_get_redis", lambda: None)
    client = TestClient(main_mod.app)
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "x" * 12},
    )
    assert res.status_code == 503
    assert "Rate limiter" in (res.json().get("detail") or "")


def test_auth_rate_limit_exceeded_returns_429(monkeypatch):
    import app.main as main_mod
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "auth_rate_limit_max_requests", 3)
    monkeypatch.setattr(cfg.settings, "auth_rate_limit_window_seconds", 60)

    store: dict[str, int] = {}

    class FakeRedis:
        def incr(self, key: str) -> int:
            store[key] = store.get(key, 0) + 1
            return store[key]

        def expire(self, key: str, window: int) -> bool:
            return True

    monkeypatch.setattr(main_mod, "_get_redis", lambda: FakeRedis())
    # Sin DB en este test: el endpoint puede 500; importa el middleware 429.
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    payload = {"email": "brute@example.com", "password": "x" * 12}
    codes = [
        client.post("/api/v1/auth/login", json=payload).status_code for _ in range(5)
    ]
    assert codes[0] != 429
    assert codes[1] != 429
    assert codes[2] != 429
    assert codes[3] == 429
    assert codes[4] == 429
    assert any(k.startswith("ratelimit:auth:") for k in store)


def test_non_auth_path_fail_open_without_redis(monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_get_redis", lambda: None)
    client = TestClient(main_mod.app)
    res = client.get("/health")
    assert res.status_code == 200


def test_auth_rate_limit_redis_error_is_503(monkeypatch):
    import app.main as main_mod

    bad = MagicMock()
    bad.incr.side_effect = ConnectionError("redis down")
    monkeypatch.setattr(main_mod, "_get_redis", lambda: bad)
    client = TestClient(main_mod.app)
    res = client.post(
        "/api/v1/auth/check-email",
        json={"email": "a@example.com"},
    )
    assert res.status_code == 503
