"""F8: check-email no enumera exists/role/is_admin."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("APP_ENV", "dev")

from app.api.v1.auth import check_email, request_registration_otp, _OTP_REQUEST_OK_MESSAGE
from app.schemas.schemas import CheckEmailRequest, CheckEmailResponse, RequestOtpRequest


def test_check_email_response_schema_has_only_next():
    fields = set(CheckEmailResponse.model_fields.keys())
    assert fields == {"next"}
    assert "exists" not in fields
    assert "role" not in fields
    assert "is_admin" not in fields


def test_check_email_unknown_returns_otp():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    out = check_email(CheckEmailRequest(email="new@example.com"), db=db)
    assert out == {"next": "otp"}


def test_check_email_cliente_returns_otp():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        role="cliente"
    )
    out = check_email(CheckEmailRequest(email="cli@example.com"), db=db)
    assert out == {"next": "otp"}


def test_check_email_admin_returns_password():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        role="admin"
    )
    out = check_email(CheckEmailRequest(email="admin@example.com"), db=db)
    assert out == {"next": "password"}


def test_request_otp_admin_same_message_as_ok(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        role="admin"
    )
    out = request_registration_otp(RequestOtpRequest(email="admin@example.com"), db=db)
    assert out["message"] == _OTP_REQUEST_OK_MESSAGE
    assert out.get("debug_otp") is None
    assert "admin" not in out["message"].lower()
