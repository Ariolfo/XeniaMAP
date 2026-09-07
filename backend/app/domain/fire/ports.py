"""Puertos (interfaces) del dominio Fire — sin dependencias de frameworks."""

from __future__ import annotations

from datetime import date
from typing import Protocol, Tuple

import pandas as pd


BBoxWSEN = Tuple[float, float, float, float]


class FirmsHotspotPort(Protocol):
    """Puerto de salida: descarga hotspots VIIRS NRT desde un proveedor externo."""

    def download(
        self,
        *,
        map_key: str,
        bbox: BBoxWSEN,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Devuelve detecciones FIRMS (lat/lon/acq_*) en un DataFrame (puede estar vacío)."""
        ...
