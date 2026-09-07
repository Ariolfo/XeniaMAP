from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError

from app.main import app


def test_register_endpoint_disabled_requires_otp():
    """F1: /auth/register no debe crear cuentas ni emitir JWT."""
    client = TestClient(app)
    payload = {
        "tenant_name": "tenant-test",
        "email": "qa-f1-disabled@example.com",
        "password": "secret123",
    }
    try:
        response = client.post("/api/v1/auth/register", json=payload)
    except OperationalError:
        pytest.skip("Postgres no disponible (solo CI / stack local)")
    assert response.status_code == 410
    detail = response.json().get("detail", "")
    assert "request-otp" in detail or "verify-otp" in detail
