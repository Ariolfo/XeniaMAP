"""F7: errores genéricos al cliente (sin rutas/traceback)."""

from __future__ import annotations

from fastapi import HTTPException

from app.core.http_errors import (
    CLIENT_INTERNAL,
    CLIENT_TASK_FAILED,
    client_safe_message,
    http_from_app_exc,
    log_celery_failure,
)


def test_client_safe_message_strips_paths():
    assert "home" not in client_safe_message(
        FileNotFoundError("/home/deep/secret.tif not found"),
        fallback="Not found",
    )
    assert client_safe_message("Proyecto no encontrado", fallback="x") == "Proyecto no encontrado"


def test_http_from_app_exc_500_is_generic():
    exc = RuntimeError("sqlalchemy OperationalError at /data/storage/x")
    http = http_from_app_exc(exc)
    assert isinstance(http, HTTPException)
    assert http.status_code == 500
    assert http.detail == CLIENT_INTERNAL


def test_http_from_app_exc_value_error():
    http = http_from_app_exc(ValueError("start_date required"))
    assert http.status_code == 400
    assert "start_date" in str(http.detail)


def test_log_celery_failure_generic():
    msg = log_celery_failure(task_id="t1", result=Exception("/var/lib/secret boom"))
    assert msg == CLIENT_TASK_FAILED
    assert "/var" not in msg
