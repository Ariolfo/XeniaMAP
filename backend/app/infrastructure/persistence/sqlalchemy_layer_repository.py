"""Adapter: LayerRepository vía SQLAlchemy."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.models.models import Layer


class SqlAlchemyLayerRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id_for_project(
        self,
        layer_id: int,
        *,
        project_id: int,
        tenant_id: int,
    ) -> Layer | None:
        return (
            self._db.query(Layer)
            .filter(
                Layer.id == int(layer_id),
                Layer.project_id == int(project_id),
                Layer.tenant_id == int(tenant_id),
            )
            .first()
        )

    def geom_meta(self, layer_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
        ids = [int(x) for x in layer_ids]
        if not ids:
            return {}
        stmt = text(
            """
            SELECT id,
                   (geom IS NOT NULL) AS mvt_ready,
                   CASE
                     WHEN geom IS NULL THEN NULL
                     ELSE ARRAY[
                       ST_XMin(geom)::float8,
                       ST_YMin(geom)::float8,
                       ST_XMax(geom)::float8,
                       ST_YMax(geom)::float8
                     ]
                   END AS bbox
            FROM layers
            WHERE id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))
        rows = self._db.execute(stmt, {"ids": ids}).mappings()
        out: dict[int, dict[str, Any]] = {}
        for row in rows:
            bbox = row["bbox"]
            if bbox is not None:
                bbox = [float(x) for x in bbox]
            out[int(row["id"])] = {
                "mvt_ready": bool(row["mvt_ready"]),
                "bbox": bbox,
            }
        return out

    def upsert_geom_geojson(
        self,
        *,
        layer_id: int,
        tenant_id: int,
        project_id: int,
        geom_geojson: str,
    ) -> None:
        self._db.execute(
            text(
                """
                UPDATE layers
                SET geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:gj)), 4326)
                WHERE id = :id
                  AND tenant_id = :tid
                  AND project_id = :pid
                """
            ),
            {
                "gj": geom_geojson,
                "id": int(layer_id),
                "tid": int(tenant_id),
                "pid": int(project_id),
            },
        )
        self._db.commit()

    def persistence_handle(self) -> Any:
        return self._db
