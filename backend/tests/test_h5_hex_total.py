"""H5: DTOs FIRMS, UoW/repos Fire, domain sin pandas."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from app.application.fire.orders import (
    project_name,
    require_fire_order_access,
    require_fire_order_admin,
)
from app.domain.fire.ports import FirmsHotspotRecord
from app.infrastructure.firms.nasa_firms_adapter import NasaFirmsAreaAdapter, _dataframe_to_records


def test_domain_fire_ports_has_no_pandas_import():
    import app.domain.fire.ports as ports
    from pathlib import Path

    src = Path(ports.__file__).read_text(encoding="utf-8")
    assert "import pandas" not in src
    assert "FirmsHotspotRecord" in src


def test_dataframe_to_records_roundtrip():
    df = pd.DataFrame(
        [{"latitude": 4.1, "longitude": -75.0, "acq_date": "2026-01-01", "frp": 1.5}]
    )
    rows = _dataframe_to_records(df)
    assert len(rows) == 1
    assert rows[0]["latitude"] == 4.1
    assert isinstance(rows[0], dict)


def test_nasa_adapter_returns_sequence_not_dataframe(monkeypatch):
    monkeypatch.setattr(
        "app.infrastructure.firms.nasa_firms_adapter.download_firms_hotspots",
        lambda *a, **k: pd.DataFrame(
            [{"latitude": 1.0, "longitude": 2.0, "acq_date": "2026-01-01"}]
        ),
    )
    out = NasaFirmsAreaAdapter().download(
        map_key="k",
        bbox=(-1.0, -1.0, 1.0, 1.0),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
    )
    assert not isinstance(out, pd.DataFrame)
    assert len(out) == 1
    assert out[0]["longitude"] == 2.0


def test_require_fire_access_via_repository():
    repo = MagicMock()
    order = MagicMock()
    order.tenant_id = 1
    order.applicant_email = "a@b.com"
    order.created_by_user_id = 9
    repo.get_by_id.return_value = order
    user = MagicMock()
    user.id = 3
    user.role = "cliente"
    user.email = "a@b.com"
    user.tenant_id = 1
    assert require_fire_order_access(7, user, fire_orders=repo) is order


def test_require_fire_admin_via_repository():
    repo = MagicMock()
    order = MagicMock()
    repo.get_by_id_for_tenant.return_value = order
    admin = MagicMock()
    admin.tenant_id = 2
    assert require_fire_order_admin(5, admin, fire_orders=repo) is order
    repo.get_by_id_for_tenant.assert_called_once_with(5, tenant_id=2)


def test_project_name_via_projects_repo():
    order = MagicMock()
    order.project_id = 11
    projects = MagicMock()
    projects.get_name.return_value = "Fire — X"
    assert project_name(order, projects=projects) == "Fire — X"


def test_firms_hotspot_record_typing():
    rec: FirmsHotspotRecord = {"latitude": 0.0, "longitude": 1.0}
    assert rec["latitude"] == 0.0
