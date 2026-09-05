"""Resolución flexible del DEM de entrada para Soil+ (.img y .tif)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.services.soilplus import _resolve_soilplus_dem_path


def _write_dem(path: Path, fill: int = 100) -> None:
    data = np.full((4, 4), fill, dtype=np.int16)
    data[0, 0] = -32767
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="int16",
        nodata=-32767,
        crs="EPSG:4326",
        transform=from_origin(-74.0, 4.6, 0.001, 0.001),
    ) as dst:
        dst.write(data, 1)


def test_prefers_band1_img_over_tif(tmp_path: Path) -> None:
    dem = tmp_path / "dem"
    dem.mkdir()
    (dem / "band_1.img").write_bytes(b"envi")
    _write_dem(dem / "band_1.tif")
    assert _resolve_soilplus_dem_path(dem).name == "band_1.img"


def test_accepts_band1_tif(tmp_path: Path) -> None:
    dem = tmp_path / "dem"
    dem.mkdir()
    _write_dem(dem / "band_1.tif")
    assert _resolve_soilplus_dem_path(dem).name == "band_1.tif"


def test_falls_back_to_named_dem_tif(tmp_path: Path) -> None:
    dem = tmp_path / "dem"
    dem.mkdir()
    _write_dem(dem / "DEM_Pastos_R_aux.tif")
    (dem / "soilplus_saved_fast_dem.png").write_bytes(b"png")
    assert _resolve_soilplus_dem_path(dem).name == "DEM_Pastos_R_aux.tif"


def test_missing_dem_returns_none(tmp_path: Path) -> None:
    dem = tmp_path / "dem"
    dem.mkdir()
    (dem / "soilplus_saved_fast.json").write_text("{}")
    assert _resolve_soilplus_dem_path(dem) is None
