"""Tests routeur Ingestion (src/api/routers/ingestion.py) — TestClient.

Couvre les branches d'erreur 500 non testées ailleurs (§5.9 R3.2) :
- DELETE /sources/{id} : succès + 500 (delete_source failure)
- GET /sources/{id}/chunks : succès + 500 (list_source_chunks failure)
- GET /sources/{id}/chunks : 503 (service non initialisé)
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    """Nettoie app.state ingestions entre tests."""
    attrs = {"ingestion_service", "vector_service", "ollama_pool"}
    for a in attrs:
        if hasattr(app.state, a):
            delattr(app.state, a)
    yield
    for a in attrs:
        if hasattr(app.state, a):
            delattr(app.state, a)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _inject_service(client: TestClient, service: AsyncMock | None = None) -> None:
    """Injecte un IngestionService mocké dans app.state."""
    if service is None:
        service = AsyncMock()
    app.state.ingestion_service = service


class TestDeleteSource:
    def test_delete_source_success(self, client: TestClient) -> None:
        """DELETE /sources/{id} → 200, chunks_deleted renvoyé."""
        service = AsyncMock()
        service.delete_source = AsyncMock(return_value=3)
        _inject_service(client, service)

        resp = client.delete("/api/v1/sources/src-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"source_id": "src-1", "chunks_deleted": 3}
        service.delete_source.assert_awaited_once_with("src-1")

    def test_delete_source_500_on_failure(self, client: TestClient) -> None:
        """DELETE /sources/{id} → 500 quand IngestionService.delete_source lève (ligne 90)."""
        service = AsyncMock()
        service.delete_source = AsyncMock(side_effect=RuntimeError("qdrant down"))
        _inject_service(client, service)

        resp = client.delete("/api/v1/sources/src-1")
        assert resp.status_code == 500
        assert "Échec suppression source" in resp.json()["detail"]

    def test_delete_source_503_when_uninitialized(self, client: TestClient) -> None:
        """DELETE → 503 si IngestionService absent (ligne 86 _get_service)."""
        resp = client.delete("/api/v1/sources/src-1")
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]


class TestListSourceChunks:
    def test_list_chunks_success(self, client: TestClient) -> None:
        """GET /sources/{id}/chunks → 200, chunks mappés en SourceChunk."""
        service = AsyncMock()
        service.list_source_chunks = AsyncMock(
            return_value=[{"id": "c1", "payload": {"text": "chunk1"}}]
        )
        _inject_service(client, service)

        resp = client.get("/api/v1/sources/src-1/chunks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["chunks"][0]["id"] == "c1"
        service.list_source_chunks.assert_awaited_once_with("src-1", limit=100)

    def test_list_chunks_500_on_failure(self, client: TestClient) -> None:
        """GET /sources/{id}/chunks → 500 quand IngestionService.list_source_chunks lève."""
        service = AsyncMock()
        service.list_source_chunks = AsyncMock(
            side_effect=RuntimeError("qdrant unreachable")
        )
        _inject_service(client, service)

        resp = client.get("/api/v1/sources/src-1/chunks")
        assert resp.status_code == 500
        assert "Échec listing source" in resp.json()["detail"]

    def test_list_chunks_503_when_uninitialized(self, client: TestClient) -> None:
        """GET /sources/{id}/chunks → 503 si service absent (ligne 99 _get_service)."""
        resp = client.get("/api/v1/sources/src-1/chunks")
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]
