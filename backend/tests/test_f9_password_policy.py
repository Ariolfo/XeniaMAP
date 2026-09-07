"""F9: política de contraseñas + HIBP k-anonymity."""

from __future__ import annotations

import hashlib

import pytest

from app.core.password_policy import (
    MIN_PASSWORD_LEN,
    PasswordRejected,
    assert_new_password,
    hibp_sha1_suffix_in_range,
    validate_password_local,
)
from app.schemas.schemas import ChangePasswordRequest, RegisterRequest


def test_local_rejects_short():
    with pytest.raises(PasswordRejected, match="at least"):
        validate_password_local("Ab1")


def test_local_rejects_no_digit():
    with pytest.raises(PasswordRejected, match="letter and one digit"):
        validate_password_local("a" * MIN_PASSWORD_LEN)


def test_local_accepts_strong():
    pw = "CorrectHorse1"
    assert validate_password_local(pw) == pw


def test_register_schema_uses_local_policy():
    with pytest.raises(Exception):
        RegisterRequest(tenant_name="t", email="a@b.co", password="short1")
    ok = RegisterRequest(tenant_name="t", email="a@b.co", password="GoodPass99")
    assert ok.password == "GoodPass99"


def test_change_password_schema_local():
    with pytest.raises(Exception):
        ChangePasswordRequest(current_password="x", new_password="short1")
    with pytest.raises(Exception):
        ChangePasswordRequest(current_password="x", new_password="1234567890")
    with pytest.raises(Exception):
        ChangePasswordRequest(current_password="x", new_password="OnlyLetters")
    ChangePasswordRequest(current_password="old", new_password="GoodPass99")


def test_hibp_detects_pwned_password(monkeypatch):
    # SHA1("Password1!") known; use controlled range response.
    digest = hashlib.sha1(b"Password1!").hexdigest().upper()
    suffix = digest[5:]

    class FakeResp:
        status_code = 200
        text = f"{suffix}:12345\nAABBCC:1\n"

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None):
            assert "/range/" in url
            return FakeResp()

    monkeypatch.setattr("app.core.password_policy.httpx.Client", FakeClient)
    monkeypatch.setattr("app.core.password_policy.settings.hibp_enabled", True)
    assert hibp_sha1_suffix_in_range("Password1!") is True
    with pytest.raises(PasswordRejected, match="breaches"):
        assert_new_password("Password1!", check_hibp=True)


def test_hibp_fail_open(monkeypatch):
    monkeypatch.setattr("app.core.password_policy.settings.hibp_enabled", True)
    monkeypatch.setattr("app.core.password_policy.settings.hibp_fail_open", True)

    class BoomClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise ConnectionError("offline")

    monkeypatch.setattr("app.core.password_policy.httpx.Client", BoomClient)
    # Local-ok password; HIBP down → allow when fail_open
    assert assert_new_password("UniqueOkPass9", check_hibp=True) == "UniqueOkPass9"


def test_hibp_fail_closed(monkeypatch):
    monkeypatch.setattr("app.core.password_policy.settings.hibp_enabled", True)
    monkeypatch.setattr("app.core.password_policy.settings.hibp_fail_open", False)

    class BoomClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise ConnectionError("offline")

    monkeypatch.setattr("app.core.password_policy.httpx.Client", BoomClient)
    with pytest.raises(PasswordRejected, match="unavailable"):
        assert_new_password("UniqueOkPass9", check_hibp=True)
