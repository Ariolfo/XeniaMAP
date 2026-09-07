"""Inventarios preprocess: use cases ópticos / recortes (thin router)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.application.agro.optical_inventory import (
    ListIndexStacksInventory,
    PreviewIndexStackPng,
    canonical_index_dir_name,
)
from app.application.agro.recortes_inventory import ListRecortesInventory, PreviewRecortePng


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ndvi", "NDVI"),
        ("CIRE", "CIre"),
        ("msavi2", "MSAVI2"),
        ("RSTRUCTURE", "RSTRUCTURE"),
        ("bogus", None),
        ("  evi  ", "EVI"),
    ],
)
def test_canonical_index_dir_name(raw, expected):
    assert canonical_index_dir_name(raw) == expected


def test_preview_index_stack_requires_path():
    with pytest.raises(ValueError, match="Indica path"):
        PreviewIndexStackPng().execute(
            tenant_id=1, project_id=1, stack_relpath=None, pipeline_variant="s2"
        )


def test_preview_index_stack_rejects_traversal():
    with patch("app.application.agro.optical_inventory._tenant_storage") as storage:
        storage.return_value = MagicMock()
        storage.return_value.resolve.return_value = MagicMock()
        with pytest.raises(ValueError, match="Ruta relativa no válida"):
            PreviewIndexStackPng().execute(
                tenant_id=1,
                project_id=1,
                stack_relpath="../etc/passwd",
                pipeline_variant="s2",
            )


def test_preview_recorte_requires_path_or_name():
    db = MagicMock()
    with patch("app.application.agro.recortes_inventory._tenant_storage") as storage:
        root = MagicMock()
        root.resolve.return_value = root
        storage.return_value = root
        with pytest.raises(ValueError, match="Indica path o name"):
            PreviewRecortePng().execute(MagicMock(), tenant_id=1, project_id=1)


def test_preview_recorte_rejects_path_traversal():
    db = MagicMock()
    with patch("app.application.agro.recortes_inventory._tenant_storage") as storage:
        root = MagicMock()
        root.resolve.return_value = root
        storage.return_value = root
        with pytest.raises(ValueError, match="Ruta relativa no válida"):
            PreviewRecortePng().execute(
                MagicMock(),
                tenant_id=1,
                project_id=1,
                recorte_relpath="../secret.tif",
                pipeline_variant="s2",
            )


def test_list_index_stacks_empty_root():
    with patch("app.application.agro.optical_inventory._tenant_storage") as storage:
        root = MagicMock()
        root.is_dir.return_value = False
        storage.return_value = root
        out = ListIndexStacksInventory().execute(
            tenant_id=1, project_id=2, pipeline_variant="s2"
        )
        assert out["items"] == []
        assert out["pipeline_variant"] == "s2"
        assert "indices" in out["indices_dir"]


def test_list_recortes_empty_root():
    db = MagicMock()
    with patch("app.application.agro.recortes_inventory._tenant_storage") as storage:
        root = MagicMock()
        root.is_dir.return_value = False
        storage.return_value = root
        out = ListRecortesInventory().execute(
            db, tenant_id=1, project_id=2, pipeline_variant="ps"
        )
        assert out["items"] == []
        assert out["pipeline_variant"] == "ps"
        assert out["recortes_dir"]
