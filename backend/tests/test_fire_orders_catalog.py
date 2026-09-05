"""Offline checks for fire result catalog and severity labels."""
from __future__ import annotations

from app.api.v1.fire_orders import FIRE_RESULT_CATALOG
from app.services.raster_geo import BURN_SEVERITY_CLASS_LABELS


def test_fire_dnbr_has_severity_class_group() -> None:
    item = next(c for c in FIRE_RESULT_CATALOG if c["filename"] == "Fire_dNBR.tif")
    assert item.get("severity_class_group") is True


def test_fire_burn_severity_nested_discrete() -> None:
    item = next(c for c in FIRE_RESULT_CATALOG if c["filename"] == "Fire_burn_severity.tif")
    assert item.get("ui_nested_only") is True
    assert item.get("discrete_severity") is True


def test_fire_result_catalog_filenames_unique() -> None:
    names = [c["filename"] for c in FIRE_RESULT_CATALOG]
    assert len(names) == len(set(names))


def test_burn_severity_class_labels_seven_classes() -> None:
    assert len(BURN_SEVERITY_CLASS_LABELS) == 7
    assert set(BURN_SEVERITY_CLASS_LABELS.keys()) == {1, 2, 3, 4, 5, 6, 7}
