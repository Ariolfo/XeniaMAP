"""Políticas de acceso Identity — puro (sin FastAPI / ORM)."""

from __future__ import annotations

from app.domain.errors import AuthorizationError
from app.domain.identity.roles import is_admin, is_cliente

# Contrato con Agro: cliente solo ve resultados cuando el proyecto está publicado.
_PUBLISHED = "publicado"


def _norm_project_status(raw: str | None) -> str:
    s = str(raw or "").strip().lower().replace("_", " ")
    if s.replace(" ", "") == "enproceso":
        s = "en proceso"
    return s


def assert_admin_role(role: str | None) -> None:
    if not is_admin(role):
        raise AuthorizationError("Admin role required")


def can_delete_project(
    *,
    role: str | None,
    user_id: int,
    owner_user_id: int | None,
    has_study_order_link: bool,
) -> bool:
    """Admin: sí. Cliente: dueño o con StudyOrder vinculada."""
    if is_admin(role):
        return True
    if not is_cliente(role):
        return False
    if owner_user_id is not None and int(owner_user_id) == int(user_id):
        return True
    return bool(has_study_order_link)


def assert_can_delete_project(
    *,
    role: str | None,
    user_id: int,
    owner_user_id: int | None,
    has_study_order_link: bool,
) -> None:
    if can_delete_project(
        role=role,
        user_id=user_id,
        owner_user_id=owner_user_id,
        has_study_order_link=has_study_order_link,
    ):
        return
    if not is_cliente(role) and not is_admin(role):
        raise AuthorizationError("No autorizado")
    raise AuthorizationError("No tienes permiso para eliminar este proyecto.")


def can_cliente_view_published_dashboard(
    *,
    role: str | None,
    project_status: str | None,
    user_id: int,
    owner_user_id: int | None,
    has_study_order_link: bool,
    has_project_share: bool,
) -> bool:
    """
    Admin / no-cliente: siempre True (gate no aplica).
    Cliente: proyecto publicado + vínculo (dueño | StudyOrder | ProjectShare).
    """
    if not is_cliente(role):
        return True
    if _norm_project_status(project_status) != _PUBLISHED:
        return False
    if owner_user_id is not None and int(owner_user_id) == int(user_id):
        return True
    return bool(has_study_order_link or has_project_share)


def assert_cliente_can_view_published_dashboard(
    *,
    role: str | None,
    project_status: str | None,
    user_id: int,
    owner_user_id: int | None,
    has_study_order_link: bool,
    has_project_share: bool,
) -> None:
    if can_cliente_view_published_dashboard(
        role=role,
        project_status=project_status,
        user_id=user_id,
        owner_user_id=owner_user_id,
        has_study_order_link=has_study_order_link,
        has_project_share=has_project_share,
    ):
        return
    if is_cliente(role) and _norm_project_status(project_status) != _PUBLISHED:
        raise AuthorizationError(
            "Los resultados de este proyecto no están publicados."
        )
    raise AuthorizationError("No tienes acceso a los resultados de este proyecto.")


def can_access_fire_order(
    *,
    role: str | None,
    user_id: int,
    user_email: str | None,
    user_tenant_id: int,
    order_tenant_id: int,
    applicant_email: str | None,
    created_by_user_id: int | None,
) -> bool:
    """Admin: mismo tenant. Cliente/otros: applicant_email o created_by."""
    if is_admin(role):
        return int(order_tenant_id) == int(user_tenant_id)
    email = str(user_email or "").strip().lower()
    order_email = str(applicant_email or "").strip().lower()
    if order_email and order_email == email:
        return True
    if created_by_user_id is not None and int(created_by_user_id) == int(user_id):
        return True
    return False


def assert_can_access_fire_order(
    *,
    role: str | None,
    user_id: int,
    user_email: str | None,
    user_tenant_id: int,
    order_tenant_id: int,
    applicant_email: str | None,
    created_by_user_id: int | None,
) -> None:
    if can_access_fire_order(
        role=role,
        user_id=user_id,
        user_email=user_email,
        user_tenant_id=user_tenant_id,
        order_tenant_id=order_tenant_id,
        applicant_email=applicant_email,
        created_by_user_id=created_by_user_id,
    ):
        return
    # Misma opacidad que hoy: no filtrar existencia a clientes ajenos.
    raise AuthorizationError("Solicitud Fire no encontrada", code="not_found")
