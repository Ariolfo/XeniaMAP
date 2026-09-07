"""H4: pipelines Fire / jobs solo via application (sin importar modules desde api/tasks)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.application.fire.aoi import FireOrderAoiPaths, WriteFireOrderAoi
from app.application.fire.pipeline_jobs import (
    RunFireDownloadS2Job,
    RunFireProcessDnbrJob,
    RunFireValidateFirmsJob,
)
from app.application.fire.process_dnbr import ProcessDnbrPipeline
from app.application.fire.validate_firms import ValidateFirmsPipeline
from app.application.fire.seed import SeedTolimaFireOrders
from app.application.fire.project_link import EnsureFireOrderProject
from app.application.agro.run_landing_markdown import RunLandingMarkdownJob
from app.tasks import fire_jobs


def test_fire_jobs_module_has_no_modules_fire_imports():
    src = Path(fire_jobs.__file__).read_text(encoding="utf-8")
    assert "app.modules.fire" not in src
    assert "RunFireDownloadS2Job" in src
    assert "RunFireProcessDnbrJob" in src
    assert "RunFireValidateFirmsJob" in src


def test_api_fire_orders_has_no_modules_fire_imports():
    from app.api.v1 import fire_orders as fo

    src = Path(fo.__file__).read_text(encoding="utf-8")
    assert "app.modules.fire" not in src
    assert "EnsureFireOrderProject" in src
    assert "SeedTolimaFireOrders" in src


def test_validate_firms_pipeline_delegates():
    with patch(
        "app.modules.fire.validate_firms.run_firms_pipeline",
        return_value={"high_count": 1},
    ) as run:
        out = ValidateFirmsPipeline().execute(
            aoi_path="/tmp/a.gpkg",
            results_dir="/tmp/r",
            fire_start="2024-01-01",
            fire_end="2024-01-05",
            map_key="k",
        )
    assert out["high_count"] == 1
    run.assert_called_once()


def test_process_dnbr_pipeline_delegates():
    with patch(
        "app.modules.fire.process_dnbr.run_dnbr_pipeline",
        return_value={"candidate_count": 3},
    ) as run:
        out = ProcessDnbrPipeline().execute(
            aoi_path="/tmp/a.gpkg",
            s2_root="/tmp/s2",
            output_dir="/tmp/out",
        )
    assert out["candidate_count"] == 3
    run.assert_called_once()


def test_aoi_paths_delegate():
    with patch(
        "app.modules.fire.aoi_io.order_paths",
        return_value={"aoi": Path("/tmp/aoi.gpkg")},
    ) as paths:
        out = FireOrderAoiPaths().execute(storage_path="/data", order_id=9)
    assert out["aoi"] == Path("/tmp/aoi.gpkg")
    paths.assert_called_once_with("/data", 9)


def test_write_aoi_delegate():
    with patch(
        "app.modules.fire.aoi_io.write_order_aoi_gpkg",
        return_value=Path("/tmp/aoi.gpkg"),
    ) as write:
        out = WriteFireOrderAoi().execute(
            geometry_geojson={"type": "Polygon", "coordinates": []},
            request_name="X",
            department="Y",
            output_path="/tmp/aoi.gpkg",
        )
    assert out == Path("/tmp/aoi.gpkg")
    write.assert_called_once()


def test_seed_and_project_link_ucs_delegate():
    uow = MagicMock()
    handle = object()
    uow.persistence_handle.return_value = handle
    admin = MagicMock()
    with patch(
        "app.modules.fire.seed.seed_tolima_fire_orders",
        return_value={"created": []},
    ) as seed:
        assert SeedTolimaFireOrders().execute(uow, admin) == {"created": []}
        seed.assert_called_once_with(handle, admin)
    order = MagicMock()
    owner = MagicMock()
    with patch(
        "app.modules.fire.project_link.ensure_fire_order_project",
        return_value="proj",
    ) as ensure:
        assert EnsureFireOrderProject().execute(uow, order, owner) == "proj"
        ensure.assert_called_once_with(handle, order, owner)


def test_run_fire_download_job_dispatches_pipeline(monkeypatch):
    order = MagicMock()
    order.id = 1
    order.data_root = "/tmp/s2"
    order.geometry_geojson = {}
    order.pre_start.isoformat.return_value = "2024-01-01"
    order.pre_end.isoformat.return_value = "2024-01-10"
    order.post_start.isoformat.return_value = "2024-02-01"
    order.post_end.isoformat.return_value = "2024-02-10"
    order.max_cloud_cover = 90

    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = order
    monkeypatch.setattr(
        "app.application.fire.pipeline_jobs._session_factory",
        lambda url: (lambda: session),
    )
    monkeypatch.setattr(
        "app.application.fire.pipeline_jobs.DownloadFireS2.execute",
        lambda self, **kw: {
            "pre": {"product_count": 1},
            "post": {"product_count": 2},
            "backend": "x",
            "elapsed_sec": 1,
        },
    )
    out = RunFireDownloadS2Job().execute(order_id=1, db_url="postgresql://x")
    assert out["pre"]["product_count"] == 1
    assert order.status == "descargado"


def test_landing_markdown_job_missing_script(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.application.agro.run_landing_markdown.Path",
        lambda *a, **k: tmp_path / "missing.py",
    )
    # Path("/repo/...") is hardcoded — patch is_file via execute internals
    with patch("app.application.agro.run_landing_markdown.Path") as P:
        inst = MagicMock()
        inst.is_file.return_value = False
        P.return_value = inst
        out = RunLandingMarkdownJob().execute(project_id=3)
    assert out["ok"] is False
    assert out["error"] == "script_missing"
