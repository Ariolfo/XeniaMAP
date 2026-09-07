"""Unit of Work — puerto de dominio (H5). Sin SQLAlchemy en firmas."""

from __future__ import annotations

from typing import Protocol

from app.domain.shared.ports import ProjectRepository


class UnitOfWork(Protocol):
    """Agrupa repositorios y controla commit/rollback."""

    @property
    def projects(self) -> ProjectRepository:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...
