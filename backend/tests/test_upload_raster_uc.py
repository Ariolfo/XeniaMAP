"""F2: upload_raster vive en application (thin router)."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pytest

from app.application.agro.rasters import upload_raster


def test_upload_raster_project_missing():
    projects = MagicMock()
    projects.get_by_id.return_value = None
    with pytest.raises(LookupError, match="Project not found"):
        upload_raster(
            MagicMock(),
            tenant_id=1,
            project_id=99,
            filename="a.tif",
            file_obj=BytesIO(b"x"),
            projects=projects,
        )


def test_upload_raster_unsupported_format():
    projects = MagicMock()
    projects.get_by_id.return_value = MagicMock()
    with pytest.raises(ValueError, match="Unsupported raster format"):
        upload_raster(
            MagicMock(),
            tenant_id=1,
            project_id=1,
            filename="notes.txt",
            file_obj=BytesIO(b"x"),
            projects=projects,
        )
