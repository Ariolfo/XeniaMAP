"""Adapter: ProjectRepository vía SQLAlchemy."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import Project


class SqlAlchemyProjectRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, project_id: int, *, tenant_id: int | None = None) -> Project | None:
        q = self._db.query(Project).filter(Project.id == int(project_id))
        if tenant_id is not None:
            q = q.filter(Project.tenant_id == int(tenant_id))
        return q.first()

    def get_name(self, project_id: int) -> str | None:
        return (
            self._db.query(Project.name)
            .filter(Project.id == int(project_id))
            .scalar()
        )

    def save(self, project: Any) -> Any:
        self._db.add(project)
        self._db.commit()
        self._db.refresh(project)
        return project
