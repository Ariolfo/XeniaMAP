"""Errores de dominio — sin FastAPI."""

from __future__ import annotations


class DomainError(Exception):
    """Base de reglas de negocio / invariantes."""

    def __init__(self, message: str, *, code: str = "domain_error"):
        super().__init__(message)
        self.message = message
        self.code = code


class AuthorizationError(DomainError):
    """Acceso denegado por política de identidad."""

    def __init__(self, message: str, *, code: str = "forbidden"):
        super().__init__(message, code=code)


class InvalidStatusError(DomainError):
    """Estado o transición inválidos."""

    def __init__(self, message: str, *, code: str = "invalid_status"):
        super().__init__(message, code=code)
