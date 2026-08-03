"""Tests for PlanetScope polygon clip helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from app.services.ps_recorte_clip import (
    clip_ps_tifs_by_wkt,
    list_ps_clip_tifs,
    normalize_ps_clip_source,
)
from app.services.raster_clip import clip_raster_by_wkt_polygon


def _write_geotiff(path: Path, *, value: float = 1.0, dtype=np.float32) -> None:
    transform = from_origin(-75.0, 5.0, 0.001, 0.001)
    data = np.full((4, 20, 20), value, dtype=dtype)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=20,
        width=20,
        count=4,
        dtype=dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data)


def test_normalize_ps_clip_source():
    assert normalize_ps_clip_source(None) == "rasterPS"
    assert normalize_ps_clip_source("rasterPS") == "rasterPS"
    assert normalize_ps_clip_source("recortesPS") == "recortesPS"
    assert normalize_ps_clip_source("raster") == "rasterPS"


def test_clip_uint16_planet_dtype(tmp_path: Path):
    src = tmp_path / "PS_23-03-26.tif"
    out = tmp_path / "out.tif"
    _write_geotiff(src, value=1000, dtype=np.uint16)
    wkt = box(-74.995, 4.985, -74.985, 4.995).wkt
    clip_raster_by_wkt_polygon(src, wkt, out)
    assert out.is_file()
    with rasterio.open(out) as ds:
        assert ds.width < 20 or ds.height < 20
        assert ds.dtypes[0] == "uint16"


def test_list_and_clip_recortes_ps(tmp_path: Path):
    root = tmp_path / "recortesPS"
    root.mkdir()
    src = root / "PS_23-03-26.tif"
    _write_geotiff(src, value=10.0)
    assert len(list_ps_clip_tifs(root, "recortesPS")) == 1

    wkt = box(-74.995, 4.985, -74.985, 4.995).wkt
    result = clip_ps_tifs_by_wkt(root, root, wkt, "recortesPS", ["PS_23-03-26.tif"])
    assert result["ok"] is True
    assert result["processed"] == 1
    assert src.is_file()
    with rasterio.open(src) as ds:
        assert ds.width < 20 or ds.height < 20


def test_clip_from_raster_ps_to_recortes_overwrite_ps_name(tmp_path: Path):
    raster = tmp_path / "rasterPS"
    out = tmp_path / "recortesPS"
    raster.mkdir()
    out.mkdir()
    src = raster / "PS_23-03-26.tif"
    old = out / "PS_23-03-26.tif"
    _write_geotiff(src, value=1000, dtype=np.uint16)
    _write_geotiff(old, value=50, dtype=np.uint16)
    wkt = box(-74.995, 4.985, -74.985, 4.995).wkt
    result = clip_ps_tifs_by_wkt(raster, out, wkt, "rasterPS", ["PS_23-03-26.tif"])
    assert result["ok"] is True
    assert result["processed"] == 1
    assert old.is_file()
    assert not (out / "PS_23-03-26_1.tif").exists()
    with rasterio.open(old) as ds:
        assert ds.width < 20 or ds.height < 20
