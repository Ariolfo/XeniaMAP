"""Adapter concreto: Area API CSV de NASA FIRMS VIIRS."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.domain.fire.ports import BBoxWSEN
from app.modules.fire.validate_firms import download_firms_hotspots


class NasaFirmsAreaAdapter:
    """Implementa FirmsHotspotPort delegando en el cliente CSV existente."""

    def download(
        self,
        *,
        map_key: str,
        bbox: BBoxWSEN,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        return download_firms_hotspots(map_key, bbox, start_date, end_date)
