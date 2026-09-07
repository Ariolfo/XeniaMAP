"""Permisos cliente: dashboard access en capas/rasters; auth en task-status/capabilities."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import assert_cliente_can_view_published_dashboard, require_project_dashboard_access


def _user(*, role: str, uid: int = 10, tenant_id: int = 1):
    u = MagicMock()
    u.id = uid
    u.role = role
    u.tenant_id = tenant_id
    return u


def _project(*, status: str = "publicado", owner_user_id: int | None = 10, tenant_id: int = 1, pid: int = 5):
    p = MagicMock()
    p.id = pid
    p.status = status
    p.owner_user_id = owner_user_id
    p.tenant_id = tenant_id
    return p


def test_cliente_blocked_on_unpublished_project():
    db = MagicMock()
    user = _user(role="cliente", uid=10)
    project = _project(status="pendiente", owner_user_id=10)
    with pytest.raises(HTTPException) as ei:
        assert_cliente_can_view_published_dashboard(db, user, project)
    assert ei.value.status_code == 403


def test_cliente_owner_published_ok():
    db = MagicMock()
    user = _user(role="cliente", uid=10)
    project = _project(status="publicado", owner_user_id=10)
    assert_cliente_can_view_published_dashboard(db, user, project)


def test_cliente_other_owner_no_share_forbidden():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    user = _user(role="cliente", uid=10)
    project = _project(status="publicado", owner_user_id=99)
    with pytest.raises(HTTPException) as ei:
        assert_cliente_can_view_published_dashboard(db, user, project)
    assert ei.value.status_code == 403


def test_admin_skips_cliente_dashboard_gate():
    db = MagicMock()
    user = _user(role="admin", uid=1)
    project = _project(status="pendiente", owner_user_id=99)
    assert_cliente_can_view_published_dashboard(db, user, project)


def test_require_project_dashboard_access_404():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as ei:
        require_project_dashboard_access(db, _user(role="admin"), 1, 999)
    assert ei.value.status_code == 404


def test_task_status_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/preprocess/task-status/fake-task-id")
    assert res.status_code == 401


def test_cluster_capabilities_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/cluster-analysis/capabilities")
    assert res.status_code == 401


def _cliente_bearer() -> dict[str, str]:
    from datetime import timedelta

    from app.core.security import create_token

    tok = create_token("999", tenant_id=1, role="cliente", expires_delta=timedelta(minutes=10))
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("/api/v1/raster/12", True),
        ("/api/v1/raster/12/34/preview", True),
        ("/api/v1/raster/tenant-storage-browse", False),
        ("/api/v1/raster/external-data-status", False),
        ("/api/v1/raster/external-data-browse", False),
        ("/api/v1/raster/project-storage-browse/12", False),
        ("/api/v1/raster/project-downloads-inventory/12", False),
        ("/api/v1/raster/project-sentinel1-inventory/12", False),
        ("/api/v1/raster/project-planetscope-zip-inventory/12", False),
        ("/api/v1/raster/project-downloads/12", False),
    ],
)
def test_cliente_raster_middleware_allowlist(path, allowed):
    from unittest.mock import MagicMock

    from app.main import _is_cliente_allowed_request

    req = MagicMock()
    req.url.path = path
    req.method = "GET"
    assert _is_cliente_allowed_request(req) is allowed


def test_cliente_middleware_blocks_admin_raster_browse():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/raster/tenant-storage-browse", headers=_cliente_bearer())
    assert res.status_code == 403
    assert res.json()["detail"] == "Forbidden for cliente role"


def test_cliente_middleware_allows_raster_list_path():
    """List path pasa middleware; sin usuario en DB el endpoint responde 401 (no 403 middleware)."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/raster/12", headers=_cliente_bearer())
    assert res.json().get("detail") != "Forbidden for cliente role"
    assert res.status_code in {401, 404, 200}
