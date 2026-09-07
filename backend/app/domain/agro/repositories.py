"""Puertos de persistencia Agro (H6+) — sin SQLAlchemy en firmas."""

from __future__ import annotations

from typing import Any, Protocol, Sequence


class LayerRepository(Protocol):
    def get_by_id_for_project(
        self,
        layer_id: int,
        *,
        project_id: int,
        tenant_id: int,
    ) -> Any | None:
        ...

    def geom_meta(self, layer_ids: Sequence[int]) -> dict[int, dict[str, Any]]:
        """``mvt_ready`` + bbox WGS84 por id."""
        ...

    def upsert_geom_geojson(
        self,
        *,
        layer_id: int,
        tenant_id: int,
        project_id: int,
        geom_geojson: str,
    ) -> None:
        """Escribe ``layers.geom`` (EPSG:4326) desde GeoJSON."""
        ...

    def persistence_handle(self) -> Any:
        """Handle opaco para ``TileRenderPort`` (Session en el adapter SQLAlchemy)."""
        ...


class RasterLayerRepository(Protocol):
    def get_by_id_for_project(
        self,
        raster_id: int,
        *,
        project_id: int,
        tenant_id: int,
    ) -> Any | None:
        ...

    def save(self, raster: Any) -> Any:
        ...

    def list_for_project_excluding(
        self,
        *,
        project_id: int,
        tenant_id: int,
        exclude_id: int,
    ) -> list[Any]:
        ...

    def list_for_project(self, *, project_id: int, tenant_id: int) -> list[Any]:
        ...

    def delete(self, raster: Any) -> None:
        """Marca fila para borrado (sin commit; el caller/UoW decide)."""
        ...
