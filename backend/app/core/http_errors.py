"""F7: mensajes de error seguros hacia el cliente (sin rutas/traceback internos)."""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException

logger = logging.getLogger(__name__)

CLIENT_INTERNAL = "Internal error"
CLIENT_TASK_FAILED = "Task failed"
CLIENT_UNAVAILABLE = "Service temporarily unavailable"
CLIENT_NOT_FOUND = "Not found"
CLIENT_BAD_REQUEST = "Bad request"

_INTERNAL_HINT = re.compile(
    r"("
    r"/home/|/data(?:_xeniamap)?/|/var/|/tmp/|/app/|"
    r"[A-Za-z]:\\|"
    r"Traceback|File \"|psycopg2|sqlalchemy|OperationalError|"
    r"redis\.|celery\.|Permission denied|No such file|Errno "
    r")",
    re.I,
)


def client_safe_message(exc: BaseException | str | None, *, fallback: str) -> str:
    """Devuelve un mensaje usable en API o ``fallback`` si parece interno."""
    msg = str(exc or "").strip() if not isinstance(exc, BaseException) else str(exc).strip()
    if not msg or len(msg) > 240 or _INTERNAL_HINT.search(msg):
        return fallback
    return msg


def http_from_app_exc(exc: Exception, *, log: logging.Logger | None = None) -> HTTPException:
    """Lookup/Value → 404/400 sanitizados; resto → 500 genérico + log."""
    log = log or logger
    if isinstance(exc, LookupError):
        return HTTPException(
            status_code=404,
            detail=client_safe_message(exc, fallback=CLIENT_NOT_FOUND),
        )
    if isinstance(exc, FileNotFoundError):
        return HTTPException(
            status_code=404,
            detail=client_safe_message(exc, fallback=CLIENT_NOT_FOUND),
        )
    if isinstance(exc, ValueError):
        return HTTPException(
            status_code=400,
            detail=client_safe_message(exc, fallback=CLIENT_BAD_REQUEST),
        )
    log.exception("Unhandled application error for HTTP mapping")
    return HTTPException(status_code=500, detail=CLIENT_INTERNAL)


def log_celery_failure(*, task_id: str | None, result: object | None) -> str:
    """Registra el fallo real y devuelve mensaje genérico al cliente."""
    logger.warning("Celery task failed task_id=%s result=%r", task_id, result)
    return CLIENT_TASK_FAILED


def celery_progress_info(info: object | None) -> dict | None:
    """Solo progress/message seguros (sin excepciones crudas en ``info``)."""
    if not isinstance(info, dict):
        return None
    out: dict = {}
    if "progress" in info:
        try:
            out["progress"] = int(info.get("progress") or 0)
        except (TypeError, ValueError):
            pass
    if info.get("message") is not None:
        out["message"] = client_safe_message(info.get("message"), fallback="In progress")
    for key in ("status", "stage"):
        if key in info and info[key] is not None:
            out[key] = client_safe_message(info[key], fallback=str(key))
    return out or None
