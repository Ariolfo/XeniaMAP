"""
Compat: CDSE helpers viven en ``app.infrastructure.cdse.client``.

Preferir imports desde infrastructure; este módulo reexporta la API estable.
"""
from app.infrastructure.cdse.client import (  # noqa: F401
    CATALOGUE_URL,
    STAC_SEARCH_URL,
    TOKEN_URL,
    CdseAuthAdapter,
    get_copernicus_credentials,
    get_copernicus_token,
    odata_attribute,
    odata_cloud_cover_pct,
)

__all__ = [
    "CATALOGUE_URL",
    "STAC_SEARCH_URL",
    "TOKEN_URL",
    "CdseAuthAdapter",
    "get_copernicus_credentials",
    "get_copernicus_token",
    "odata_attribute",
    "odata_cloud_cover_pct",
]
