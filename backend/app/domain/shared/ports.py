"""Puertos compartidos — sin frameworks."""

from __future__ import annotations

from typing import Any, Protocol


class CdseAuthPort(Protocol):
    """Puerto: autenticación OAuth CDSE (Copernicus Data Space)."""

    def credentials_from_settings(self, settings: Any) -> tuple[str, str]:
        """Usuario/contraseña desde settings; lanza RuntimeError si faltan."""
        ...

    def access_token(self, username: str, password: str) -> str:
        """Token Bearer CDSE."""
        ...
