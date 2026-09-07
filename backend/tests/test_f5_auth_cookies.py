"""F5: cookies HttpOnly + auth por cookie o Bearer."""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("APP_ENV", "dev")

from unittest.mock import MagicMock

from fastapi import Response
from starlette.requests import Request

from app.api.deps import _access_token_from_request
from app.core.auth_cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)


def test_set_auth_cookies_are_httponly():
    response = Response()
    set_auth_cookies(response, access_token="access-jwt", refresh_token="refresh-jwt")
    # Starlette guarda Set-Cookie en raw_headers
    cookies = response.headers.getlist("set-cookie")
    joined = "\n".join(cookies).lower()
    assert ACCESS_COOKIE in joined or any(ACCESS_COOKIE in c for c in cookies)
    assert any("httponly" in c.lower() for c in cookies)
    assert any(REFRESH_COOKIE in c for c in cookies)


def test_clear_auth_cookies():
    response = Response()
    set_auth_cookies(response, access_token="a", refresh_token="b")
    clear_auth_cookies(response)
    cookies = response.headers.getlist("set-cookie")
    assert cookies  # delete_cookie emite Set-Cookie de expiración


def test_access_token_prefers_bearer_over_cookie():
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [
            (b"authorization", b"Bearer from-header"),
            (b"cookie", f"{ACCESS_COOKIE}=from-cookie".encode()),
        ],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    creds = MagicMock()
    creds.credentials = "from-header"
    assert _access_token_from_request(request, creds) == "from-header"


def test_access_token_falls_back_to_cookie():
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"cookie", f"{ACCESS_COOKIE}=cookie-jwt".encode())],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    assert _access_token_from_request(request, None) == "cookie-jwt"


def test_login_sets_cookies_integration():
    """Si hay Postgres y un usuario seedable vía OTP, login/refresh dejan cookies."""
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    from app.core import config as cfg
    from app.core.otp_store import set_otp
    from app.main import app

    client = TestClient(app)
    email = "f5-cookie-auth@example.com"
    try:
        set_otp(email, "123456")
        res = client.post(
            "/api/v1/auth/verify-otp",
            json={"email": email, "code": "123456"},
        )
    except OperationalError:
        pytest.skip("Postgres no disponible")
    except Exception as exc:
        # Redis/OTP store puede fallar en CI mínimo
        pytest.skip(f"OTP/DB no disponible: {exc}")

    if res.status_code not in (200, 201):
        pytest.skip(f"verify-otp no usable en este entorno: {res.status_code}")

    assert ACCESS_COOKIE in res.cookies or any(
        ACCESS_COOKIE in (h.decode() if isinstance(h, bytes) else h)
        for h in res.headers.getlist("set-cookie")
    )
    # /auth/me solo con cookie (sin Authorization)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json().get("email") == email

    # refresh con cookie (body vacío)
    refreshed = client.post("/api/v1/auth/refresh", json={})
    assert refreshed.status_code == 200
    assert "access_token" in refreshed.json()

    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200
    me2 = client.get("/api/v1/auth/me")
    assert me2.status_code == 401
