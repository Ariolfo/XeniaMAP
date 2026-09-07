"""Registro task_id Celery → tenant (y opcionalmente project) para autorizar task-status."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "xeniamap:celery_task:"
_DEFAULT_TTL_SEC = 7 * 24 * 3600  # 7 días
_mem: dict[str, tuple[dict[str, Any], float]] = {}


def _redis():
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def register_celery_task(
    task_id: str | None,
    *,
    tenant_id: int,
    project_id: int | None = None,
    task_name: str | None = None,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> None:
    """Asocia un task_id encolado al tenant del JWT (y proyecto si se conoce)."""
    from app.core.metrics import observe_celery_enqueued

    tid = str(task_id or "").strip()
    if not tid:
        return
    payload = {
        "tenant_id": int(tenant_id),
        "project_id": int(project_id) if project_id is not None else None,
        "task_name": str(task_name).strip() if task_name else None,
    }
    key = f"{_PREFIX}{tid}"
    r = _redis()
    if r:
        try:
            r.setex(key, int(ttl_sec), json.dumps(payload))
            observe_celery_enqueued(task_name)
            return
        except Exception as exc:
            logger.debug("celery_task_registry redis set: %s", exc)
    _mem[tid] = (payload, time.time() + float(ttl_sec))
    observe_celery_enqueued(task_name)


def get_celery_task_owner(task_id: str | None) -> dict[str, Any] | None:
    """Devuelve ``{tenant_id, project_id}`` o ``None`` si no hay registro / expiró."""
    tid = str(task_id or "").strip()
    if not tid:
        return None
    key = f"{_PREFIX}{tid}"
    r = _redis()
    if r:
        try:
            raw = r.get(key)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict) and "tenant_id" in data:
                    return {
                        "tenant_id": int(data["tenant_id"]),
                        "project_id": (
                            int(data["project_id"]) if data.get("project_id") is not None else None
                        ),
                    }
        except Exception as exc:
            logger.debug("celery_task_registry redis get: %s", exc)
    tup = _mem.get(tid)
    if not tup:
        return None
    payload, exp = tup
    if time.time() > exp:
        _mem.pop(tid, None)
        return None
    return {
        "tenant_id": int(payload["tenant_id"]),
        "project_id": (
            int(payload["project_id"]) if payload.get("project_id") is not None else None
        ),
    }
