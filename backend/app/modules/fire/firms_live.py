"""
Compatibilidad: FIRMS live ahora vive en application/infrastructure (hexagonal).

Preferir:
  from app.application.fire.firms_live import GetFirmsLiveHotspots
  from app.infrastructure.firms.nasa_firms_adapter import NasaFirmsAreaAdapter
"""

from __future__ import annotations

from typing import Any

from app.application.fire.firms_live import GetFirmsLiveHotspots, split_hotspots_by_age
from app.infrastructure.firms.nasa_firms_adapter import NasaFirmsAreaAdapter

# Alias usados por tests previos
_hotspots_to_feature_collections = split_hotspots_by_age


def fetch_firms_live(
    *,
    geometry_geojson: dict,
    map_key: str,
    hours: int = 48,
) -> dict[str, Any]:
    """Facade estable para routers/tasks existentes."""
    return GetFirmsLiveHotspots(NasaFirmsAreaAdapter()).execute(
        geometry_geojson=geometry_geojson,
        map_key=map_key,
        hours=hours,
    )


__all__ = [
    "fetch_firms_live",
    "GetFirmsLiveHotspots",
    "NasaFirmsAreaAdapter",
    "split_hotspots_by_age",
    "_hotspots_to_feature_collections",
]
