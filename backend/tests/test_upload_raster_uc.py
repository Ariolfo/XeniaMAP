"""F2: upload_raster vive en application (thin router)."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pytest

from app.application.agro.rasters import upload_raster


def test_upload_raster_project_missing():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(LookupError, match="Project not found"):
        upload_raster(
            db,
            tenant_id=1,
            project_id=99,
            filename="a.tif",
            file_obj=BytesIO(b"x"),
        )


def test_upload_raster_unsupported_format():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock()
    with pytest.raises(ValueError, match="Unsupported raster format"):
        upload_raster(
            db,
            tenant_id=1,
            project_id=1,
            filename="notes.txt",
            file_obj=BytesIO(b"x"),
        )
