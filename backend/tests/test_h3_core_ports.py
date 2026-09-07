"""H3: puertos núcleo — UC con mocks (sin Celery/SMTP/PostGIS reales)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.application.agro.download import StartSentinel2ProjectDownload
from app.application.agro.layer_mvt import RenderLayerMvtTile
from app.application.agro.notify import NotifyStudyOrderOrProject
from app.application.fire.orders import EnqueueFireDownloadS2, project_name
from app.application.fire.results import FireResultXyzTile
from app.infrastructure.jobs.celery_job_queue import CeleryJobQueue


def test_celery_job_queue_enqueue_registers(monkeypatch):
    task = MagicMock()
    task.delay.return_value = MagicMock(id="tid-1")
    task.name = "demo.task"
    registered = {}

    def _reg(tid, *, tenant_id, project_id=None, task_name=None, ttl_sec=0):
        registered["payload"] = {
            "tid": tid,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "task_name": task_name,
        }

    monkeypatch.setattr(
        "app.infrastructure.jobs.celery_job_queue.register_celery_task", _reg
    )
    out = CeleryJobQueue().enqueue(
        task, 42, tenant_id=3, project_id=9, task_name="demo.task"
    )
    assert out == "tid-1"
    task.delay.assert_called_once_with(42)
    assert registered["payload"]["tenant_id"] == 3
    assert registered["payload"]["project_id"] == 9


def test_notify_study_order_uses_mail_port():
    mail = MagicMock()
    NotifyStudyOrderOrProject(mail=mail).execute(
        order_id=5, user_email="a@b.com", lines=["hola"]
    )
    mail.send_study_order_notification.assert_called_once_with(
        order_id=5, user_email="a@b.com", lines=["hola"]
    )


def test_fire_xyz_tile_uses_tile_port(tmp_path: Path, monkeypatch):
    tif = tmp_path / "Fire_dNBR.tif"
    tif.write_bytes(b"fake")
    tiles = MagicMock()
    tiles.render_fire_xyz_tile_png.return_value = b"PNG"

    monkeypatch.setattr(
        "app.application.fire.results.safe_result_path", lambda *a, **k: tif
    )
    monkeypatch.setattr(
        "app.application.fire.results.catalog_entry",
        lambda name: {"index_palette": False, "discrete_severity": False},
    )

    out = FireResultXyzTile(tiles=tiles).execute(
        order_id=1, filename="Fire_dNBR.tif", z=8, x=1, y=2
    )
    assert out == b"PNG"
    tiles.render_fire_xyz_tile_png.assert_called_once()
    assert tiles.render_fire_xyz_tile_png.call_args.args[0] == tif


def test_render_layer_mvt_uses_tile_port():
    tiles = MagicMock()
    tiles.render_layer_mvt_tile.return_value = b"mvt"
    db = MagicMock()
    layer = MagicMock()
    layer.id = 7
    layer.tenant_id = 1
    layer.project_id = 2

    monkeypatch_meta = MagicMock(return_value={7: {"mvt_ready": True}})
    import app.application.agro.layer_mvt as mvt_mod

    original = mvt_mod.layer_geom_meta
    mvt_mod.layer_geom_meta = monkeypatch_meta
    try:
        out = RenderLayerMvtTile(tiles=tiles).execute(db, layer=layer, z=5, x=1, y=1)
    finally:
        mvt_mod.layer_geom_meta = original
    assert out == b"mvt"
    tiles.render_layer_mvt_tile.assert_called_once()


def test_project_name_via_repository():
    repo = MagicMock()
    repo.get_name.return_value = "Lote A"
    order = MagicMock()
    order.project_id = 11
    assert project_name(order, projects=repo) == "Lote A"
    repo.get_name.assert_called_once_with(11)


def test_enqueue_fire_download_via_job_queue(monkeypatch):
    jobs = MagicMock()
    jobs.enqueue.return_value = "fire-task"
    order = MagicMock()
    order.id = 4
    order.tenant_id = 2
    order.pre_start = order.pre_end = order.post_start = order.post_end = MagicMock()
    # comparable dates
    from datetime import date

    order.pre_start = date(2024, 1, 1)
    order.pre_end = date(2024, 1, 10)
    order.post_start = date(2024, 2, 1)
    order.post_end = date(2024, 2, 10)
    order.max_cloud_cover = 90
    order.status = "pendiente"
    db = MagicMock()

    monkeypatch.setattr(
        "app.application.fire.orders.fire_storage_root",
        lambda oid: Path(f"/tmp/fire/{oid}"),
    )
    monkeypatch.setattr(
        "app.application.fire.orders.settings.database_url",
        "postgresql://x",
        raising=False,
    )

    out = EnqueueFireDownloadS2(jobs=jobs).execute(order=order, db=db)
    assert out["task_id"] == "fire-task"
    assert order.download_task_id == "fire-task"
    assert jobs.enqueue.call_args.kwargs["task_name"] == "fire_download_s2"


def test_start_s2_download_via_job_queue(monkeypatch):
    jobs = MagicMock()
    jobs.enqueue.return_value = "s2-task"
    db = MagicMock()

    raster = MagicMock()
    raster.id = 99
    raster.raster_metadata = {}

    def _refresh(obj):
        obj.id = 99
        obj.raster_metadata = obj.raster_metadata or {}

    db.refresh.side_effect = _refresh

    monkeypatch.setattr(
        "app.application.agro.download.ensure_external_sensor_download_dirs",
        lambda sub, sensor: (Path("/data/s2"), Path("/data"), "ext:foo"),
    )
    monkeypatch.setattr(
        "app.application.agro.download.RasterLayer",
        lambda **kw: raster,
    )

    out = StartSentinel2ProjectDownload(jobs=jobs).execute(
        db=db,
        tenant_id=1,
        project_id=2,
        start_date="2024-01-01",
        end_date="2024-01-31",
        download_subpath="ext:foo",
        wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
        copernicus_configured=True,
        database_url="postgresql://x",
    )
    assert out["task_id"] == "s2-task"
    assert jobs.enqueue.call_args.kwargs["task_name"] == "download_sentinel2"


def test_start_s2_download_requires_credentials():
    with pytest.raises(RuntimeError, match="Copernicus"):
        StartSentinel2ProjectDownload(jobs=MagicMock()).execute(
            db=MagicMock(),
            tenant_id=1,
            project_id=2,
            start_date="2024-01-01",
            end_date="2024-01-31",
            download_subpath="ext:foo",
            wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
            copernicus_configured=False,
            database_url="postgresql://x",
        )
