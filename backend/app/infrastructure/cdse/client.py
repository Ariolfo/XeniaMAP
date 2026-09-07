"""
Cliente CDSE: OAuth, catálogo OData/STAC helpers.

Implementación concreta del puerto ``CdseAuthPort``.
"""
from __future__ import annotations

from typing import Any

import requests

CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"


def get_copernicus_credentials(settings: Any) -> tuple[str, str]:
    """
    Usuario y contraseña CDSE desde la configuración.

    Variables ``COPERNICUS_USER`` y ``COPERNICUS_PASSWORD`` en ``.env``.
    """
    u = (getattr(settings, "copernicus_user", None) or "").strip()
    p = getattr(settings, "copernicus_password", None) or ""
    if not u or not p:
        raise RuntimeError(
            "Credenciales Copernicus no configuradas. Defina COPERNICUS_USER y COPERNICUS_PASSWORD."
        )
    return u, p


def get_copernicus_token(username: str, password: str) -> str:
    data = {
        "client_id": "cdse-public",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    r = requests.post(TOKEN_URL, data=data, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def odata_attribute(product: dict, name: str, default: Any = None) -> Any:
    """Read an OData Attributes entry by Name (case-insensitive)."""
    target = str(name or "").lower()
    for attr in product.get("Attributes") or []:
        if str(attr.get("Name") or "").lower() == target:
            return attr.get("Value", default)
    return default


def odata_cloud_cover_pct(product: dict) -> float | None:
    """Cloud cover de la escena completa (Attributes OData), 0–100."""
    value = odata_attribute(product, "cloudCover")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class CdseAuthAdapter:
    """Adapter hexagonal para autenticación CDSE."""

    def credentials_from_settings(self, settings: Any) -> tuple[str, str]:
        return get_copernicus_credentials(settings)

    def access_token(self, username: str, password: str) -> str:
        return get_copernicus_token(username, password)
