"""SqlAlchemy UnitOfWork + FireOrderRepository."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.infrastructure.persistence.sqlalchemy_layer_repository import (
    SqlAlchemyLayerRepository,
)
from app.infrastructure.persistence.sqlalchemy_project_repository import (
    SqlAlchemyProjectRepository,
)
from app.infrastructure.persistence.sqlalchemy_raster_layer_repository import (
    SqlAlchemyRasterLayerRepository,
)
from app.models.models import FireOrder


class SqlAlchemyFireOrderRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, order_id: int) -> FireOrder | None:
        return self._db.query(FireOrder).filter(FireOrder.id == int(order_id)).first()

    def get_by_id_for_tenant(self, order_id: int, *, tenant_id: int) -> FireOrder | None:
        return (
            self._db.query(FireOrder)
            .filter(FireOrder.id == int(order_id), FireOrder.tenant_id == int(tenant_id))
            .first()
        )

    def save(self, order: Any) -> Any:
        self._db.add(order)
        self._db.commit()
        self._db.refresh(order)
        return order


class SqlAlchemyUnitOfWork:
    """UoW delgado: repos tipados + commit/rollback sobre Session inyectada."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self.projects = SqlAlchemyProjectRepository(db)
        self.fire_orders = SqlAlchemyFireOrderRepository(db)
        self.layers = SqlAlchemyLayerRepository(db)
        self.raster_layers = SqlAlchemyRasterLayerRepository(db)

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    def persistence_handle(self) -> Any:
        return self._db


def unit_of_work(db: Session) -> SqlAlchemyUnitOfWork:
    """Glue delivery→UoW (API/tasks)."""
    return SqlAlchemyUnitOfWork(db)
