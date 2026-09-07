"""AOI / paths de orden Fire — punto de entrada hexagonal (H4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FireOrderAoiPaths:
    """Resuelve rutas bajo ``storage/fire/order_{id}/``."""

    def execute(self, *, storage_path: str | Path, order_id: int) -> dict[str, Path]:
        from app.modules.fire.aoi_io import order_paths

        return order_paths(storage_path, order_id)


class WriteFireOrderAoi:
    """Materializa el GeoPackage AOI esperado por scripts 02/03."""

    def execute(
        self,
        *,
        geometry_geojson: dict[str, Any],
        request_name: str,
        department: str | None,
        output_path: str | Path,
    ) -> Path:
        from app.modules.fire.aoi_io import write_order_aoi_gpkg

        return write_order_aoi_gpkg(
            geometry_geojson=geometry_geojson,
            request_name=request_name,
            department=department,
            output_path=output_path,
        )
