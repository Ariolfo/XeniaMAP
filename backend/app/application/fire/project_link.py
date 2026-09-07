"""Project link Fire — UC sobre ``modules.fire.project_link`` (H4: api no importa modules)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import FireOrder, Project, User


class EnsureFireOrderProject:
    def execute(self, db: Session, order: FireOrder, owner: User) -> Project:
        from app.modules.fire.project_link import ensure_fire_order_project

        return ensure_fire_order_project(db, order, owner)


class MaterializeFireProjectsForApplicant:
    def execute(self, db: Session, **kwargs: Any) -> Any:
        from app.modules.fire.project_link import materialize_fire_projects_for_applicant

        return materialize_fire_projects_for_applicant(db, **kwargs)
