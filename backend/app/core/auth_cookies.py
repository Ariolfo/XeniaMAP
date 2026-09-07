"""Cookies HttpOnly para access/refresh (F5)."""

from __future__ import annotations

import os

from fastapi import Response

from app.core.config import settings

ACCESS_COOKIE = "xeniamap_access"
REFRESH_COOKIE = "xeniamap_refresh"


def _cookie_secure() -> bool:
    if settings.is_production():
        return True
    return os.environ.get("COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}


def _common_cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": "lax",
        "path": "/",
    }


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    kw = _common_cookie_kwargs()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=max(60, int(settings.access_token_expire_minutes) * 60),
        **kw,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max(60, int(settings.refresh_token_expire_minutes) * 60),
        **kw,
    )


def clear_auth_cookies(response: Response) -> None:
    kw = _common_cookie_kwargs()
    response.delete_cookie(ACCESS_COOKIE, path=kw["path"])
    response.delete_cookie(REFRESH_COOKIE, path=kw["path"])
