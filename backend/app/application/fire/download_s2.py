"""Caso de uso: descarga parcial S2 PRE/POST para una orden Fire."""

from __future__ import annotations

from typing import Any

from app.domain.shared.ports import CdseAuthPort
from app.infrastructure.cdse.client import CdseAuthAdapter


class DownloadFireS2:
    """Punto de entrada hexagonal hacia ``modules.fire.download_s2``."""

    def __init__(self, auth: CdseAuthPort | None = None) -> None:
        self._auth = auth or CdseAuthAdapter()

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        from app.modules.fire.download_s2 import run_fire_s2_download

        kwargs.setdefault("auth", self._auth)
        return run_fire_s2_download(**kwargs)
