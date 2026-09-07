"""Puerto: persistencia de órdenes Fire (H5)."""

from __future__ import annotations

from typing import Any, Protocol


class FireOrderRepository(Protocol):
    def get_by_id(self, order_id: int) -> Any | None:
        ...

    def get_by_id_for_tenant(self, order_id: int, *, tenant_id: int) -> Any | None:
        ...

    def save(self, order: Any) -> Any:
        ...
