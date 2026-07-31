"""Tests unitaires de base — Phase 0 : valider le squelette avant code métier."""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ready_returns_structured(self, client):
        resp = client.get("/api/v1/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body
        assert "checks" in body


class TestQueryEndpoint:
    def test_query_not_implemented(self, client):
        resp = client.post("/api/v1/query", json={"question": "test"})
        assert resp.status_code == 500
