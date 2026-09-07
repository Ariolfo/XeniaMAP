"""Adapter concreto: Area API CSV de NASA FIRMS VIIRS → DTOs de dominio."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from app.domain.fire.ports import BBoxWSEN, FirmsHotspotRecord
from app.modules.fire.validate_firms import download_firms_hotspots


def _dataframe_to_records(df) -> list[FirmsHotspotRecord]:
    if df is None or getattr(df, "empty", True):
        return []
    records: list[FirmsHotspotRecord] = []
    for row in df.to_dict(orient="records"):
        # TypedDict structural — keep only JSON-ish scalars.
        clean: FirmsHotspotRecord = {}
        for key, val in row.items():
            if val is None:
                continue
            try:
                if hasattr(val, "item"):
                    val = val.item()
            except Exception:
                pass
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            clean[str(key)] = val  # type: ignore[literal-required]
        if "latitude" in clean and "longitude" in clean:
            records.append(clean)
    return records


class NasaFirmsAreaAdapter:
    """Implementa FirmsHotspotPort; pandas queda encapsulado en el adaptador."""

    def download(
        self,
        *,
        map_key: str,
        bbox: BBoxWSEN,
        start_date: date,
        end_date: date,
    ) -> Sequence[FirmsHotspotRecord]:
        df = download_firms_hotspots(map_key, bbox, start_date, end_date)
        return _dataframe_to_records(df)
