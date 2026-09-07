"""Tests F6: COG helper + FIRMS stale cache."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin


def test_rewrite_as_cog_roundtrip(tmp_path: Path):
    from app.infrastructure.raster.cog import is_cloud_optimized, rewrite_as_cog

    src = tmp_path / "plain.tif"
    arr = np.arange(64, dtype=np.float32).reshape(8, 8)
    profile = {
        "driver": "GTiff",
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-74.0, 5.0, 0.01, 0.01),
    }
    with rasterio.open(src, "w", **profile) as dst:
        dst.write(arr, 1)

    assert not is_cloud_optimized(src)
    out = rewrite_as_cog(src, overview_resampling="AVERAGE")
    assert out == src
    assert is_cloud_optimized(src)
    # second call no-op
    rewrite_as_cog(src)
    with rasterio.open(src) as check:
        assert check.read(1).shape == (8, 8)


def test_firms_stale_cache_roundtrip(monkeypatch):
    from app.infrastructure.firms import live_cache as lc

    monkeypatch.setattr(lc, "_redis", lambda: None)
    monkeypatch.setattr(lc.settings, "firms_live_cache_ttl_sec", 300)
    lc._mem.clear()

    payload = {"counts": {"hotspots_24h": 2}, "layers": {}}
    lc.set_firms_live_cached(42, 48, payload)
    fresh = lc.get_firms_live_cached(42, 48)
    assert fresh is not None
    assert fresh["counts"]["hotspots_24h"] == 2
    stale = lc.get_firms_live_stale(42, 48)
    assert stale is not None
    assert stale["counts"]["hotspots_24h"] == 2
