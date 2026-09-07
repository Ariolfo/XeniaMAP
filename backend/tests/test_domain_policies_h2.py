"""H2: políticas Identity y estados Agro/Fire — sin FastAPI."""
from __future__ import annotations

import pytest

from app.domain.agro.project_status import (
    PROJECT_STATUS_EN_PROCESO,
    assert_project_transition,
    normalize_project_status,
    plan_project_status_change,
)
from app.domain.agro.study_order_status import (
    plan_study_order_status_change,
    normalize_study_order_status,
)
from app.domain.errors import AuthorizationError, InvalidStatusError
from app.domain.fire.order_status import (
    FIRE_STATUS_EN_DESCARGA,
    FIRE_STATUS_PROCESANDO,
    assert_fire_order_transition,
    normalize_fire_order_status,
)
from app.domain.identity.policies import (
    assert_can_access_fire_order,
    assert_can_delete_project,
    assert_cliente_can_view_published_dashboard,
    can_access_fire_order,
    can_cliente_view_published_dashboard,
    can_delete_project,
)
from app.domain.identity.roles import is_admin, is_cliente


def test_roles():
    assert is_admin("Admin")
    assert is_cliente(" CLIENTE ")
    assert not is_admin("cliente")


def test_cliente_dashboard_owner_published():
    assert can_cliente_view_published_dashboard(
        role="cliente",
        project_status="publicado",
        user_id=10,
        owner_user_id=10,
        has_study_order_link=False,
        has_project_share=False,
    )


def test_cliente_dashboard_unpublished_denied():
    with pytest.raises(AuthorizationError, match="no están publicados"):
        assert_cliente_can_view_published_dashboard(
            role="cliente",
            project_status="pendiente",
            user_id=10,
            owner_user_id=10,
            has_study_order_link=False,
            has_project_share=False,
        )


def test_cliente_dashboard_share_ok():
    assert can_cliente_view_published_dashboard(
        role="cliente",
        project_status="publicado",
        user_id=10,
        owner_user_id=99,
        has_study_order_link=False,
        has_project_share=True,
    )


def test_admin_skips_dashboard_gate():
    assert can_cliente_view_published_dashboard(
        role="admin",
        project_status="pendiente",
        user_id=1,
        owner_user_id=99,
        has_study_order_link=False,
        has_project_share=False,
    )


def test_delete_project_cliente_owner():
    assert can_delete_project(
        role="cliente", user_id=5, owner_user_id=5, has_study_order_link=False
    )


def test_delete_project_cliente_unrelated_denied():
    with pytest.raises(AuthorizationError, match="eliminar"):
        assert_can_delete_project(
            role="cliente", user_id=5, owner_user_id=9, has_study_order_link=False
        )


def test_fire_access_admin_same_tenant():
    assert can_access_fire_order(
        role="admin",
        user_id=1,
        user_email="a@x.com",
        user_tenant_id=2,
        order_tenant_id=2,
        applicant_email="c@x.com",
        created_by_user_id=9,
    )


def test_fire_access_admin_other_tenant_denied():
    with pytest.raises(AuthorizationError, match="Fire"):
        assert_can_access_fire_order(
            role="admin",
            user_id=1,
            user_email="a@x.com",
            user_tenant_id=2,
            order_tenant_id=3,
            applicant_email="c@x.com",
            created_by_user_id=9,
        )


def test_fire_access_cliente_by_email():
    assert can_access_fire_order(
        role="cliente",
        user_id=10,
        user_email="User@Mail.COM",
        user_tenant_id=1,
        order_tenant_id=1,
        applicant_email="user@mail.com",
        created_by_user_id=99,
    )


def test_project_status_normalize_enproceso():
    assert normalize_project_status("enproceso") == PROJECT_STATUS_EN_PROCESO
    assert normalize_project_status("en_proceso") == PROJECT_STATUS_EN_PROCESO


def test_project_status_invalid():
    with pytest.raises(InvalidStatusError):
        normalize_project_status("borrador")


def test_project_transition_and_effects():
    assert assert_project_transition("pendiente", "publicado") == "publicado"
    effects = plan_project_status_change("publicado")
    assert effects.set_published and effects.notify_owner


def test_study_order_effects_cascade():
    effects = plan_study_order_status_change("procesado")
    assert effects.project_status == "procesado"
    assert effects.set_project_processed_by_admin
    assert normalize_study_order_status("PUBLICADO") == "publicado"


def test_fire_pipeline_transition_ok():
    assert (
        assert_fire_order_transition("pendiente", FIRE_STATUS_EN_DESCARGA, mode="pipeline")
        == FIRE_STATUS_EN_DESCARGA
    )


def test_fire_pipeline_transition_blocked():
    with pytest.raises(InvalidStatusError, match="Pipeline"):
        assert_fire_order_transition("validado", FIRE_STATUS_PROCESANDO, mode="pipeline")


def test_fire_admin_transition_any():
    assert assert_fire_order_transition("error", "pendiente", mode="admin") == "pendiente"
    assert normalize_fire_order_status("validado") == "validado"
