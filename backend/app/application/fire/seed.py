"""Seed Tolima Fire — UC (H4: api no importa modules)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.models import User


class SeedTolimaFireOrders:
    def execute(self, db: Session, admin: User, **kwargs: Any) -> dict[str, Any]:
        from app.modules.fire.seed import seed_tolima_fire_orders

        return seed_tolima_fire_orders(db, admin, **kwargs)
