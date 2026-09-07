"""Paquete Identity — roles y políticas de acceso."""

from app.domain.identity.policies import (
    assert_admin_role,
    assert_can_access_fire_order,
    assert_can_delete_project,
    assert_cliente_can_view_published_dashboard,
    can_access_fire_order,
    can_cliente_view_published_dashboard,
    can_delete_project,
)
from app.domain.identity.roles import ROLE_ADMIN, ROLE_CLIENTE, is_admin, is_cliente, normalize_role

__all__ = [
    "ROLE_ADMIN",
    "ROLE_CLIENTE",
    "assert_admin_role",
    "assert_can_access_fire_order",
    "assert_can_delete_project",
    "assert_cliente_can_view_published_dashboard",
    "can_access_fire_order",
    "can_cliente_view_published_dashboard",
    "can_delete_project",
    "is_admin",
    "is_cliente",
    "normalize_role",
]
