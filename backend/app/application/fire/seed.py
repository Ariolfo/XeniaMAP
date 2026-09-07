"""Seed Tolima Fire — UC (H4: api no importa modules)."""

from __future__ import annotations

from typing import Any

from app.domain.shared.uow import UnitOfWork
from app.models.models import User


class SeedTolimaFireOrders:
    def execute(self, uow: UnitOfWork, admin: User, **kwargs: Any) -> dict[str, Any]:
        from app.modules.fire.seed import seed_tolima_fire_orders

        # Módulo legacy aún usa Session; UoW es la frontera de application/.
        return seed_tolima_fire_orders(uow.persistence_handle(), admin, **kwargs)
