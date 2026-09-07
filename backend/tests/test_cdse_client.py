"""Offline unit tests for shared CDSE client helpers."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.cdse.client import (
    TOKEN_URL,
    get_copernicus_credentials,
    get_copernicus_token,
    odata_attribute,
    odata_cloud_cover_pct,
)


def test_get_copernicus_token_success() -> None:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "tok-abc"}
    mock_resp.raise_for_status = MagicMock()

    with patch("app.infrastructure.cdse.client.requests.post", return_value=mock_resp) as post:
        token = get_copernicus_token("user@example.com", "secret")

    assert token == "tok-abc"
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == TOKEN_URL
    assert kwargs["data"]["grant_type"] == "password"
    assert kwargs["data"]["username"] == "user@example.com"
    assert kwargs["timeout"] == 30


def test_cdse_auth_adapter_roundtrip() -> None:
    from app.infrastructure.cdse.client import CdseAuthAdapter

    adapter = CdseAuthAdapter()
    settings = SimpleNamespace(copernicus_user="u", copernicus_password="p")
    assert adapter.credentials_from_settings(settings) == ("u", "p")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"access_token": "t1"}
    mock_resp.raise_for_status = MagicMock()
    with patch("app.infrastructure.cdse.client.requests.post", return_value=mock_resp):
        assert adapter.access_token("u", "p") == "t1"


def test_get_copernicus_credentials_empty_raises() -> None:
    settings = SimpleNamespace(copernicus_user="", copernicus_password="")
    with pytest.raises(RuntimeError, match="COPERNICUS_USER"):
        get_copernicus_credentials(settings)

    settings2 = SimpleNamespace(copernicus_user="u", copernicus_password="")
    with pytest.raises(RuntimeError, match="Credenciales Copernicus"):
        get_copernicus_credentials(settings2)


def test_get_copernicus_credentials_ok() -> None:
    settings = SimpleNamespace(copernicus_user="  alice  ", copernicus_password="pw")
    assert get_copernicus_credentials(settings) == ("alice", "pw")


def test_odata_attribute_case_insensitive() -> None:
    product = {"Attributes": [{"Name": "cloudCover", "Value": 12.5}]}
    assert odata_attribute(product, "CloudCover") == 12.5
    assert odata_cloud_cover_pct(product) == 12.5
    assert odata_cloud_cover_pct({"Attributes": []}) is None
