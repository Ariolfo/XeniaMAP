"""Puertos (interfaces) del dominio Fire — sin frameworks ni pandas."""

from __future__ import annotations

from datetime import date
from typing import Protocol, Sequence, TypedDict, Tuple


BBoxWSEN = Tuple[float, float, float, float]


class FirmsHotspotRecord(TypedDict, total=False):
    """Detección FIRMS canónica (DTO de puerto; sin DataFrame)."""

    latitude: float
    longitude: float
    acq_date: str
    acq_time: int | str
    frp: float
    confidence: str | float | int
    satellite: str
    firms_source: str
    version: str


class FirmsHotspotPort(Protocol):
    """Puerto de salida: descarga hotspots VIIRS NRT desde un proveedor externo."""

    def download(
        self,
        *,
        map_key: str,
        bbox: BBoxWSEN,
        start_date: date,
        end_date: date,
    ) -> Sequence[FirmsHotspotRecord]:
        """Devuelve detecciones FIRMS (lat/lon/acq_*); lista vacía si no hay datos."""
        ...
