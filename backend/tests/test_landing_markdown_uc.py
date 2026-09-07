"""Landing markdown use cases (H1/H3 ports)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.application.agro.landing_markdown import (
    LANDING_MARKDOWN_NAMES,
    EnqueueLandingMarkdown,
    ListLandingMarkdownFiles,
    ResolveLandingMarkdownPath,
)


def test_list_landing_markdown_empty(tmp_path: Path):
    storage = MagicMock()
    storage.tenant_kind_dir.return_value = tmp_path
    out = ListLandingMarkdownFiles(storage=storage).execute(tenant_id=1, project_id=9)
    assert out["project_id"] == 9
    assert out["files"] == []
    assert out["max_md_mb"] == 4.9
    storage.tenant_kind_dir.assert_called_once_with(1, 9, "markdown")


def test_list_landing_markdown_finds_files(tmp_path: Path):
    name = LANDING_MARKDOWN_NAMES["S2"]
    (tmp_path / name).write_text("# s2\n", encoding="utf-8")
    storage = MagicMock()
    storage.tenant_kind_dir.return_value = tmp_path
    out = ListLandingMarkdownFiles(storage=storage).execute(tenant_id=1, project_id=2)
    assert len(out["files"]) == 1
    assert out["files"][0]["sensor"] == "S2"
    assert out["files"][0]["name"] == name


def test_resolve_landing_markdown_path_ok(tmp_path: Path):
    name = LANDING_MARKDOWN_NAMES["PS"]
    target = tmp_path / name
    target.write_text("x", encoding="utf-8")
    storage = MagicMock()
    storage.tenant_kind_dir.return_value = tmp_path
    p = ResolveLandingMarkdownPath(storage=storage).execute(
        tenant_id=1, project_id=1, sensor="ps"
    )
    assert p == target


def test_resolve_landing_markdown_bad_sensor():
    with pytest.raises(ValueError, match="PS, S1 o S2"):
        ResolveLandingMarkdownPath(storage=MagicMock()).execute(
            tenant_id=1, project_id=1, sensor="XX"
        )


def test_resolve_landing_markdown_missing(tmp_path: Path):
    storage = MagicMock()
    storage.tenant_kind_dir.return_value = tmp_path
    with pytest.raises(FileNotFoundError, match="landing_narrativa_S1"):
        ResolveLandingMarkdownPath(storage=storage).execute(
            tenant_id=1, project_id=1, sensor="S1"
        )


def test_enqueue_landing_markdown_via_job_queue():
    jobs = MagicMock()
    jobs.enqueue.return_value = "task-abc"
    out = EnqueueLandingMarkdown(jobs=jobs).execute(tenant_id=7, project_id=3)
    assert out == {"status": "queued", "task_id": "task-abc"}
    assert jobs.enqueue.call_args.kwargs["tenant_id"] == 7
    assert jobs.enqueue.call_args.kwargs["project_id"] == 3
    assert jobs.enqueue.call_args.kwargs["task_name"] == "landing_markdown_pipeline"


def test_enqueue_landing_markdown_wraps_broker_errors():
    jobs = MagicMock()
    jobs.enqueue.side_effect = RuntimeError("Redis/worker down")
    with pytest.raises(RuntimeError, match="Redis/worker"):
        EnqueueLandingMarkdown(jobs=jobs).execute(tenant_id=1, project_id=1)


def test_rasters_routers_importable():
    from app.api.v1 import rasters, rasters_admin

    map_paths = {getattr(r, "path", None) for r in rasters.router.routes}
    admin_paths = {getattr(r, "path", None) for r in rasters_admin.router.routes}
    assert "/raster/{project_id}" in map_paths
    assert "/raster/tenant-storage-browse" in admin_paths
    assert "/raster/{project_id}" not in admin_paths
