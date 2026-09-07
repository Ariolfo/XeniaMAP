"""Rate limiting helpers (F6: bucket auth fail-closed)."""

from __future__ import annotations

# Rutas sensibles a brute-force / enumeración (sin prefijo /api/v1).
# /auth/register queda fuera: siempre 410 (F1); no debe depender de Redis (fail-closed).
AUTH_RATE_LIMIT_SUFFIXES: tuple[str, ...] = (
    "/auth/login",
    "/auth/request-otp",
    "/auth/verify-otp",
    "/auth/check-email",
    "/auth/change-password",
)


def is_auth_rate_limited_path(path: str, *, api_prefix: str) -> bool:
    """True si ``path`` es un endpoint auth que debe usar el bucket estricto."""
    p = (path or "").rstrip("/") or "/"
    prefix = (api_prefix or "").rstrip("/")
    for suffix in AUTH_RATE_LIMIT_SUFFIXES:
        if p == f"{prefix}{suffix}" or p.endswith(suffix):
            return True
    return False
