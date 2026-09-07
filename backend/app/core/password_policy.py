"""F9: política de contraseñas nuevas + HIBP Passwords API (k-anonymity)."""

from __future__ import annotations

import hashlib
import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MIN_PASSWORD_LEN = 10
_HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"

# Letras + dígito; evita solo letras o solo números.
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


class PasswordRejected(ValueError):
    """Contraseña nueva no aceptable (política local o HIBP)."""


def validate_password_local(password: str) -> str:
    """Reglas locales (sin red). Devuelve la contraseña o lanza ``PasswordRejected``."""
    pw = password if isinstance(password, str) else str(password or "")
    if len(pw) < MIN_PASSWORD_LEN:
        raise PasswordRejected(
            f"Password must be at least {MIN_PASSWORD_LEN} characters"
        )
    if len(pw) > 128:
        raise PasswordRejected("Password must be at most 128 characters")
    if not _HAS_LETTER.search(pw) or not _HAS_DIGIT.search(pw):
        raise PasswordRejected("Password must include at least one letter and one digit")
    # Espacios solo al borde suelen ser typos de pegado.
    if pw != pw.strip():
        raise PasswordRejected("Password must not start or end with whitespace")
    return pw


def hibp_sha1_suffix_in_range(password: str, *, timeout: float | None = None) -> bool | None:
    """
    Consulta HIBP range API (solo prefijo SHA-1 de 5 hex).

    Returns:
        True si aparece en filtraciones, False si no, None si el chequeo no está disponible.
    """
    if not getattr(settings, "hibp_enabled", True):
        return None
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    url = _HIBP_RANGE_URL.format(prefix=prefix)
    to = float(timeout if timeout is not None else settings.hibp_timeout_seconds)
    try:
        with httpx.Client(timeout=to) as client:
            resp = client.get(
                url,
                headers={
                    "Add-Padding": "true",
                    "User-Agent": "XeniaMAP-password-check",
                },
            )
        if resp.status_code != 200:
            logger.warning("HIBP range API status=%s", resp.status_code)
            return None
        needle = suffix.upper()
        for line in resp.text.splitlines():
            parts = line.split(":")
            if not parts:
                continue
            if parts[0].strip().upper() == needle:
                return True
        return False
    except Exception as exc:
        logger.warning("HIBP range API unavailable: %s", exc)
        return None


def assert_new_password(password: str, *, check_hibp: bool = True) -> str:
    """
    Valida política local y, si está habilitado, HIBP.

    Si HIBP no responde: respeta ``settings.hibp_fail_open`` (True → permite con log).
    """
    pw = validate_password_local(password)
    if not check_hibp:
        return pw
    pwned = hibp_sha1_suffix_in_range(pw)
    if pwned is True:
        raise PasswordRejected(
            "Password appears in known data breaches; choose a different one"
        )
    if pwned is None and not bool(getattr(settings, "hibp_fail_open", True)):
        raise PasswordRejected(
            "Password safety check unavailable; try again later"
        )
    return pw
