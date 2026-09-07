"""Glue delivery→repos Agro (H6)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.agro.repositories import LayerRepository, RasterLayerRepository
from app.infrastructure.persistence.sqlalchemy_layer_repository import (
    SqlAlchemyLayerRepository,
)
from app.infrastructure.persistence.sqlalchemy_raster_layer_repository import (
    SqlAlchemyRasterLayerRepository,
)


def layers_repo(db: Session) -> LayerRepository:
    return SqlAlchemyLayerRepository(db)


def raster_layers_repo(db: Session) -> RasterLayerRepository:
    return SqlAlchemyRasterLayerRepository(db)
