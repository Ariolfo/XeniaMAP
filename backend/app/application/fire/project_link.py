"""Project link Fire — UC sobre ``modules.fire.project_link`` (H4: api no importa modules)."""

from __future__ import annotations

from typing import Any

from app.domain.shared.uow import UnitOfWork
from app.models.models import FireOrder, Project, User


class EnsureFireOrderProject:
    def execute(self, uow: UnitOfWork, order: FireOrder, owner: User) -> Project:
        from app.modules.fire.project_link import ensure_fire_order_project

        return ensure_fire_order_project(uow.persistence_handle(), order, owner)


class MaterializeFireProjectsForApplicant:
    def execute(self, uow: UnitOfWork, **kwargs: Any) -> Any:
        from app.modules.fire.project_link import materialize_fire_projects_for_applicant

        return materialize_fire_projects_for_applicant(uow.persistence_handle(), **kwargs)
