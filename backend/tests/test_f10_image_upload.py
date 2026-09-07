"""F10: validación magic bytes / decode de imágenes landing."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.core.image_upload import InvalidImageUpload, validate_raster_image_bytes


def _minimal_png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (2, 2), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_accepts_valid_png():
    data = _minimal_png()
    ext, mime = validate_raster_image_bytes(data, claimed_ext=".png")
    assert ext == ".png"
    assert mime == "image/png"


def test_rejects_svg_polyglot_as_png():
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>'
    with pytest.raises(InvalidImageUpload):
        validate_raster_image_bytes(svg, claimed_ext=".png")


def test_rejects_extension_mismatch():
    data = _minimal_png()
    with pytest.raises(InvalidImageUpload, match="coincide"):
        validate_raster_image_bytes(data, claimed_ext=".jpg")


def test_rejects_empty():
    with pytest.raises(InvalidImageUpload, match="vacío"):
        validate_raster_image_bytes(b"", claimed_ext=".png")


def test_rejects_random_bytes():
    with pytest.raises(InvalidImageUpload):
        validate_raster_image_bytes(b"not-an-image-at-all!!!!", claimed_ext=".png")
