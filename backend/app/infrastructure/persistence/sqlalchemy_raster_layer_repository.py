"""Adapter: RasterLayerRepository vía SQLAlchemy."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import RasterLayer


class SqlAlchemyRasterLayerRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id_for_project(
        self,
        raster_id: int,
        *,
        project_id: int,
        tenant_id: int,
    ) -> RasterLayer | None:
        return (
            self._db.query(RasterLayer)
            .filter(
                RasterLayer.id == int(raster_id),
                RasterLayer.project_id == int(project_id),
                RasterLayer.tenant_id == int(tenant_id),
            )
            .first()
        )

    def save(self, raster: Any) -> Any:
        self._db.add(raster)
        self._db.commit()
        self._db.refresh(raster)
        return raster

    def list_for_project_excluding(
        self,
        *,
        project_id: int,
        tenant_id: int,
        exclude_id: int,
    ) -> list[RasterLayer]:
        return (
            self._db.query(RasterLayer)
            .filter(
                RasterLayer.project_id == int(project_id),
                RasterLayer.tenant_id == int(tenant_id),
                RasterLayer.id != int(exclude_id),
            )
            .all()
        )

    def list_for_project(self, *, project_id: int, tenant_id: int) -> list[RasterLayer]:
        return (
            self._db.query(RasterLayer)
            .filter(
                RasterLayer.project_id == int(project_id),
                RasterLayer.tenant_id == int(tenant_id),
            )
            .all()
        )

    def delete(self, raster: Any) -> None:
        self._db.delete(raster)
