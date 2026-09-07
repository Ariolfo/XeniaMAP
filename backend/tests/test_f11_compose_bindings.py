"""F11: Postgres/Redis no deben publicarse en 0.0.0.0 sin auth."""

from __future__ import annotations

from pathlib import Path


def test_compose_binds_db_redis_to_loopback():
    root = Path(__file__).resolve().parents[2]
    text = (root / "docker-compose.yml").read_text()
    assert "127.0.0.1:5433:5432" in text
    assert "127.0.0.1:6379:6379" in text
    assert "requirepass" in text
    assert "REDIS_PASSWORD" in text
    # Exposición antigua en todas las interfaces
    assert '"5433:5432"' not in text
    assert '"6379:6379"' not in text
