"""Unit tests for Project.module column metadata (no DB)."""
from __future__ import annotations

from app.models.models import Project


def test_project_has_module_column_default_agro() -> None:
    assert "module" in Project.__table__.columns
    col = Project.__table__.columns["module"]
    assert col.nullable is False
    assert col.default is not None
    assert col.default.arg == "agro"
