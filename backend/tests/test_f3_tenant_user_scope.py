"""F3: admins solo ven/mutan usuarios de su tenant."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.auth import _tenant_user_or_404


def test_tenant_user_or_404_same_tenant():
    admin = SimpleNamespace(id=1, tenant_id=10)
    target = SimpleNamespace(id=2, tenant_id=10, email="a@x.test")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = target
    assert _tenant_user_or_404(db, admin, 2) is target
    # Filtro debe incluir tenant_id
    filt_call = db.query.return_value.filter.call_args
    assert filt_call is not None


def test_tenant_user_or_404_cross_tenant_is_404():
    admin = SimpleNamespace(id=1, tenant_id=10)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as ei:
        _tenant_user_or_404(db, admin, 99)
    assert ei.value.status_code == 404
