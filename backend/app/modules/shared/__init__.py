"""Frontera compartida entre Agro y Fire (paths, helpers de storage).

Hoy la mayoría de utilidades compartidas siguen en ``app.api.v1.helpers`` y
``app.core.storage_paths``. Este paquete marca el hueco ``modules/shared``
del audit F2 sin forzar un big-bang de imports.
"""

from __future__ import annotations

__all__ = ("DOMAIN",)

DOMAIN = "shared"
