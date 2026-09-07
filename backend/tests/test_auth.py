from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError

from app.main import app


def test_register_flow():
    client = TestClient(app)
    payload = {
        "tenant_name": "tenant-test",
        "email": "qa@example.com",
        "password": "secret123",
    }
    try:
        response = client.post("/api/v1/auth/register", json=payload)
    except OperationalError:
        pytest.skip("Postgres no disponible (solo CI / stack local)")
    assert response.status_code in [200, 400]
