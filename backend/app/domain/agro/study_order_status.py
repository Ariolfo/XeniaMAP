"""Estados y transiciones de StudyOrder (+ cascada a Project)."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.agro.project_status import (
    PROJECT_STATUS_PENDIENTE,
    PROJECT_STATUS_PROCESADO,
    PROJECT_STATUS_PUBLICADO,
)
from app.domain.errors import InvalidStatusError

STUDY_STATUS_PENDIENTE = "pendiente"
STUDY_STATUS_PROCESADO = "procesado"
STUDY_STATUS_PUBLICADO = "publicado"

STUDY_ORDER_STATUSES: frozenset[str] = frozenset(
    {
        STUDY_STATUS_PENDIENTE,
        STUDY_STATUS_PROCESADO,
        STUDY_STATUS_PUBLICADO,
    }
)

STUDY_ORDER_TRANSITIONS: dict[str, frozenset[str]] = {
    s: frozenset(STUDY_ORDER_STATUSES) for s in STUDY_ORDER_STATUSES
}


def normalize_study_order_status(raw: str) -> str:
    s = str(raw or "").strip().lower().replace("_", " ")
    if s not in STUDY_ORDER_STATUSES:
        raise InvalidStatusError(
            "Estado debe ser: pendiente, procesado o publicado"
        )
    return s


def assert_study_order_transition(current: str | None, new: str) -> str:
    target = normalize_study_order_status(new)
    if current is None or str(current).strip() == "":
        return target
    try:
        src = normalize_study_order_status(current)
    except InvalidStatusError:
        return target
    if target not in STUDY_ORDER_TRANSITIONS.get(src, STUDY_ORDER_STATUSES):
        raise InvalidStatusError(
            f"Transición de orden de estudio no permitida: {src} → {target}"
        )
    return target


@dataclass(frozen=True)
class StudyOrderStatusEffects:
    status: str
    project_status: str | None
    assign_admin: bool = False
    set_order_processing_started_if_missing: bool = False
    set_order_processing_completed: bool = False
    set_order_processing_completed_if_missing: bool = False
    set_project_processing_started_if_missing: bool = False
    set_project_processing_completed: bool = False
    set_project_processing_completed_if_missing: bool = False
    set_project_published_if_missing: bool = False
    set_project_processed_by_admin: bool = False
    set_project_approved_by_admin: bool = False


def plan_study_order_status_change(new_status: str) -> StudyOrderStatusEffects:
    s = normalize_study_order_status(new_status)
    if s == STUDY_STATUS_PENDIENTE:
        return StudyOrderStatusEffects(
            status=s,
            project_status=PROJECT_STATUS_PENDIENTE,
        )
    if s == STUDY_STATUS_PROCESADO:
        return StudyOrderStatusEffects(
            status=s,
            project_status=PROJECT_STATUS_PROCESADO,
            assign_admin=True,
            set_order_processing_completed=True,
            set_order_processing_started_if_missing=True,
            set_project_processing_started_if_missing=True,
            set_project_processing_completed=True,
            set_project_processed_by_admin=True,
        )
    # publicado
    return StudyOrderStatusEffects(
        status=s,
        project_status=PROJECT_STATUS_PUBLICADO,
        assign_admin=True,
        set_order_processing_started_if_missing=True,
        set_order_processing_completed_if_missing=True,
        set_project_processing_started_if_missing=True,
        set_project_processing_completed_if_missing=True,
        set_project_published_if_missing=True,
        set_project_processed_by_admin=True,
        set_project_approved_by_admin=True,
    )
