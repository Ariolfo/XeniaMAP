"""Unit of Work — puerto de dominio (H5/H6). Sin SQLAlchemy en firmas."""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.agro.repositories import LayerRepository, RasterLayerRepository
from app.domain.fire.repositories import FireOrderRepository
from app.domain.shared.ports import ProjectRepository


class UnitOfWork(Protocol):
    """Agrupa repositorios y controla commit/rollback."""

    @property
    def projects(self) -> ProjectRepository:
        ...

    @property
    def fire_orders(self) -> FireOrderRepository:
        ...

    @property
    def layers(self) -> LayerRepository:
        ...

    @property
    def raster_layers(self) -> RasterLayerRepository:
        ...

    def persistence_handle(self) -> Any:
        """Handle opaco para módulos legacy (Session en adapter SQLAlchemy)."""
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...
