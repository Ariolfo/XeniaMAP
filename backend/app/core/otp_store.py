import logging
import secrets
import time

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)
_mem: dict[str, tuple[str, float]] = {}


def _redis():
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def set_otp(email: str, code: str, ttl_sec: int = 600) -> None:
    key_email = email.strip().lower()
    r = _redis()
    if r:
        r.setex(f"xeniamap:otp:{key_email}", ttl_sec, code)
    else:
        _mem[key_email] = (code, time.time() + ttl_sec)
    logger.info("OTP almacenado para verificación de correo (dominio=%s)", key_email.split("@")[-1])


def verify_and_consume_otp(email: str, code: str) -> bool:
    key_email = email.strip().lower()
    r = _redis()
    if r:
        key = f"xeniamap:otp:{key_email}"
        stored = r.get(key)
        if not stored or not secrets.compare_digest(stored.strip(), code.strip()):
            return False
        r.delete(key)
        return True
    tup = _mem.pop(key_email, None)
    if not tup:
        return False
    c, exp = tup
    if time.time() > exp:
        return False
    return secrets.compare_digest(c.strip(), code.strip())


def peek_otp_for_dev(email: str) -> str | None:
    """Solo depuración / demos cuando no hay correo SMTP."""
    import os

    if os.environ.get("LOG_OTP", "").strip() not in {"1", "true", "yes"}:
        return None
    key_email = email.strip().lower()
    r = _redis()
    if r:
        return r.get(f"xeniamap:otp:{key_email}")
    tup = _mem.get(key_email)
    return tup[0] if tup else None
