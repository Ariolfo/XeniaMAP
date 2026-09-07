"""Tests índices agro simples (sin Celery)."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from app.application.agro.indices import ComputeSimpleVegetationIndex, SUPPORTED_SIMPLE_INDICES


def _write_tiny_tif(path: Path) -> None:
    data = (np.arange(16, dtype="float32").reshape(4, 4) + 10)
    transform = from_origin(-74.0, 5.0, 0.001, 0.001)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)


def test_compute_simple_ndvi(tmp_path: Path) -> None:
    src = tmp_path / "src.tif"
    out = tmp_path / "ndvi.tif"
    _write_tiny_tif(src)
    key = ComputeSimpleVegetationIndex().execute(src_path=src, out_path=out, index_type="ndvi")
    assert key == "NDVI"
    assert out.is_file()
    with rasterio.open(out) as ds:
        assert ds.count == 1
        assert ds.dtypes[0] == "float32"


def test_unsupported_index_raises(tmp_path: Path) -> None:
    src = tmp_path / "src.tif"
    out = tmp_path / "x.tif"
    _write_tiny_tif(src)
    try:
        ComputeSimpleVegetationIndex().execute(src_path=src, out_path=out, index_type="FOO")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    assert SUPPORTED_SIMPLE_INDICES == frozenset({"NDVI", "EVI", "NDWI"})
