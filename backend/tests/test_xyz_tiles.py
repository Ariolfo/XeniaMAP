"""Smoke XYZ tiles (sin GDAL file real: empty tile helper)."""

from app.infrastructure.raster.xyz_tiles import empty_tile_png


def test_empty_tile_png_is_png():
    raw = empty_tile_png()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 50
