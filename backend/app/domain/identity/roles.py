"""Roles de identidad (valores canónicos)."""

from __future__ import annotations

ROLE_ADMIN = "admin"
ROLE_CLIENTE = "cliente"


def normalize_role(role: str | None) -> str:
    return str(role or "").strip().lower()


def is_admin(role: str | None) -> bool:
    return normalize_role(role) == ROLE_ADMIN


def is_cliente(role: str | None) -> bool:
    return normalize_role(role) == ROLE_CLIENTE
