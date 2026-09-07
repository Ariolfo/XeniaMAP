"""Landing markdown use cases (H1)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.application.agro.landing_markdown import (
    LANDING_MARKDOWN_NAMES,
    EnqueueLandingMarkdown,
    ListLandingMarkdownFiles,
    ResolveLandingMarkdownPath,
)


def test_list_landing_markdown_empty(tmp_path: Path):
    with patch(
        "app.application.agro.landing_markdown._tenant_storage",
        return_value=tmp_path,
    ):
        out = ListLandingMarkdownFiles().execute(tenant_id=1, project_id=9)
    assert out["project_id"] == 9
    assert out["files"] == []
    assert out["max_md_mb"] == 4.9


def test_list_landing_markdown_finds_files(tmp_path: Path):
    name = LANDING_MARKDOWN_NAMES["S2"]
    (tmp_path / name).write_text("# s2\n", encoding="utf-8")
    with patch(
        "app.application.agro.landing_markdown._tenant_storage",
        return_value=tmp_path,
    ):
        out = ListLandingMarkdownFiles().execute(tenant_id=1, project_id=2)
    assert len(out["files"]) == 1
    assert out["files"][0]["sensor"] == "S2"
    assert out["files"][0]["name"] == name


def test_resolve_landing_markdown_path_ok(tmp_path: Path):
    name = LANDING_MARKDOWN_NAMES["PS"]
    target = tmp_path / name
    target.write_text("x", encoding="utf-8")
    with patch(
        "app.application.agro.landing_markdown._tenant_storage",
        return_value=tmp_path,
    ):
        p = ResolveLandingMarkdownPath().execute(
            tenant_id=1, project_id=1, sensor="ps"
        )
    assert p == target


def test_resolve_landing_markdown_bad_sensor():
    with pytest.raises(ValueError, match="PS, S1 o S2"):
        ResolveLandingMarkdownPath().execute(
            tenant_id=1, project_id=1, sensor="XX"
        )


def test_resolve_landing_markdown_missing(tmp_path: Path):
    with patch(
        "app.application.agro.landing_markdown._tenant_storage",
        return_value=tmp_path,
    ):
        with pytest.raises(FileNotFoundError, match="landing_narrativa_S1"):
            ResolveLandingMarkdownPath().execute(
                tenant_id=1, project_id=1, sensor="S1"
            )


def test_enqueue_landing_markdown_registers_task():
    async_result = MagicMock()
    async_result.id = "task-abc"
    with (
        patch(
            "app.tasks.jobs.landing_markdown_pipeline.delay",
            return_value=async_result,
        ) as delay,
        patch(
            "app.core.celery_task_registry.register_celery_task"
        ) as register,
    ):
        out = EnqueueLandingMarkdown().execute(tenant_id=7, project_id=3)
    delay.assert_called_once_with(3)
    register.assert_called_once_with(
        "task-abc",
        tenant_id=7,
        project_id=3,
        task_name="landing_markdown_pipeline",
    )
    assert out == {"status": "queued", "task_id": "task-abc"}


def test_enqueue_landing_markdown_wraps_broker_errors():
    with patch(
        "app.tasks.jobs.landing_markdown_pipeline.delay",
        side_effect=ConnectionError("redis down"),
    ):
        with pytest.raises(RuntimeError, match="Redis/worker"):
            EnqueueLandingMarkdown().execute(tenant_id=1, project_id=1)


def test_rasters_routers_importable():
    from app.api.v1 import rasters, rasters_admin

    map_paths = {getattr(r, "path", None) for r in rasters.router.routes}
    admin_paths = {getattr(r, "path", None) for r in rasters_admin.router.routes}
    assert "/raster/{project_id}" in map_paths
    assert "/raster/tenant-storage-browse" in admin_paths
    assert "/raster/{project_id}" not in admin_paths
