"""H6: UoW/repos sin Session en UC piloto + requirements slim."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from app.application.agro.crop_recortes import _require_project_layer
from app.application.agro.download import GetSentinelDownloadStatus
from app.infrastructure.persistence.sqlalchemy_uow import SqlAlchemyUnitOfWork


def test_uow_protocol_exposes_fire_and_agro_repos():
    src = Path(__file__).resolve().parents[1] / "app/domain/shared/uow.py"
    text = src.read_text(encoding="utf-8")
    for name in ("projects", "fire_orders", "layers", "raster_layers"):
        assert f"def {name}(self)" in text or f"{name}:" in text or f".{name}" in text
    # Adapter concreto
    uow = SqlAlchemyUnitOfWork(MagicMock())
    assert hasattr(uow, "fire_orders")
    assert hasattr(uow, "layers")
    assert hasattr(uow, "raster_layers")
    assert hasattr(uow, "projects")


def test_require_project_layer_via_repository():
    layers = MagicMock()
    layers.get_by_id_for_project.return_value = MagicMock()
    _require_project_layer(layers, tenant_id=1, project_id=2, layer_id=9)
    layers.get_by_id_for_project.assert_called_once_with(9, project_id=2, tenant_id=1)

    layers.get_by_id_for_project.return_value = None
    try:
        _require_project_layer(layers, tenant_id=1, project_id=2, layer_id=9)
        assert False, "expected LookupError"
    except LookupError:
        pass


def test_get_sentinel_download_status_via_raster_repo():
    raster = MagicMock()
    raster.raster_metadata = {"status": "completed", "progress_message": "ok"}
    repo = MagicMock()
    repo.get_by_id_for_project.return_value = raster
    out = GetSentinelDownloadStatus().execute(
        raster_layers=repo, tenant_id=1, project_id=2, raster_id=3
    )
    assert out["ui_status"] == "completed"
    assert out["progress"] == 100


def test_requirements_api_excludes_boto3():
    root = Path(__file__).resolve().parents[1]
    api = (root / "requirements-api.txt").read_text(encoding="utf-8")
    common = (root / "requirements-common.txt").read_text(encoding="utf-8")
    worker = (root / "requirements-worker.txt").read_text(encoding="utf-8")
    assert "boto3==" not in api
    assert "boto3==" not in common
    assert "boto3==" in worker
    assert "-r requirements-common.txt" in api
    assert "-r requirements-common.txt" in worker


def test_soilplus_router_does_not_import_soilplus_at_module_level():
    src = Path(__file__).resolve().parents[1] / "app/api/v1/soilplus.py"
    text = src.read_text(encoding="utf-8")
    assert "from app.application.agro import soilplus as sp" not in text
    assert "def _sp()" in text


def test_layer_mvt_uc_uses_layer_repository_not_session_type():
    src = Path(__file__).resolve().parents[1] / "app/application/agro/layer_mvt.py"
    text = src.read_text(encoding="utf-8")
    assert "db: Session" not in text
    assert "LayerRepository" in text
