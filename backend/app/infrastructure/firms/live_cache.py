"""Cache TTL para FIRMS live (Redis si disponible; fallback en memoria).

F6: además del cache fresco (TTL corto + bucket horario), guarda una copia
``stale`` de larga duración para responder si NASA falla.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_mem: dict[str, tuple[float, str]] = {}

# Copia degradada: sirve si FIRMS/NASA cae (24 h por defecto).
_STALE_TTL_SEC = 86400


def _redis():
    try:
        import redis

        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def firms_live_cache_key(order_id: int, hours: int) -> str:
    """Bucket por hora UTC para no servir datos más viejos que el TTL nominal."""
    hour_bucket = int(time.time() // 3600)
    return f"xeniamap:firms_live:v1:{int(order_id)}:{int(hours)}:{hour_bucket}"


def firms_live_stale_key(order_id: int, hours: int) -> str:
    return f"xeniamap:firms_live:stale:v1:{int(order_id)}:{int(hours)}"


def _get_raw(key: str) -> str | None:
    r = _redis()
    if r is not None:
        try:
            raw = r.get(key)
            if raw:
                return raw
        except Exception as exc:
            logger.debug("firms live redis get: %s", exc)
    entry = _mem.get(key)
    if not entry:
        return None
    expires_at, raw = entry
    if time.time() > expires_at:
        _mem.pop(key, None)
        return None
    return raw


def _set_raw(key: str, raw: str, ttl: int) -> None:
    r = _redis()
    if r is not None:
        try:
            r.setex(key, ttl, raw)
            return
        except Exception as exc:
            logger.debug("firms live redis set: %s", exc)
    _mem[key] = (time.time() + ttl, raw)
    if len(_mem) > 512:
        now = time.time()
        for k, (exp, _) in list(_mem.items()):
            if exp <= now:
                _mem.pop(k, None)


def get_firms_live_cached(order_id: int, hours: int) -> dict[str, Any] | None:
    from app.core.metrics import observe_firms_cache

    ttl = int(getattr(settings, "firms_live_cache_ttl_sec", 300) or 0)
    if ttl <= 0:
        observe_firms_cache("disabled")
        return None
    raw = _get_raw(firms_live_cache_key(order_id, hours))
    if not raw:
        observe_firms_cache("miss")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        observe_firms_cache("miss")
        return None
    observe_firms_cache("hit")
    return data


def get_firms_live_stale(order_id: int, hours: int) -> dict[str, Any] | None:
    """Última respuesta buena (puede ser de hace horas)."""
    from app.core.metrics import observe_firms_cache

    raw = _get_raw(firms_live_stale_key(order_id, hours))
    if not raw:
        observe_firms_cache("stale_miss")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        observe_firms_cache("stale_miss")
        return None
    observe_firms_cache("stale_hit")
    return data


def set_firms_live_cached(order_id: int, hours: int, payload: dict[str, Any]) -> None:
    ttl = int(getattr(settings, "firms_live_cache_ttl_sec", 300) or 0)
    try:
        raw = json.dumps(payload, separators=(",", ":"))
    except (TypeError, ValueError):
        return
    if ttl > 0:
        _set_raw(firms_live_cache_key(order_id, hours), raw, ttl)
    # Siempre refrescar stale (aunque TTL fresco sea 0 en tests).
    _set_raw(firms_live_stale_key(order_id, hours), raw, _STALE_TTL_SEC)
