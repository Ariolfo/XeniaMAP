"""Frontera de dominio Agro (monolito modular).

Los pipelines/algoritmos viven en ``app.services`` y ``app.application.agro``.
Este paquete documenta el límite de módulo frente a Fire (`app.modules.fire`)
sin mover Celery task names ni rutas HTTP.

Puntos de entrada application:

- ``app.application.agro.soilplus`` — SoilPlus + dashboard IA Planet
- ``app.application.agro.rasters`` — browse/inventario/borrado de rasters
- ``app.application.agro.download`` / ``crop_recortes`` / ``indices`` / …
  — preprocess (ya cableado desde ``api.v1.preprocess``)
"""

from __future__ import annotations

__all__ = ("DOMAIN",)

DOMAIN = "agro"
