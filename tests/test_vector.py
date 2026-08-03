"""Tests VectorService — AsyncMock sur AsyncQdrantClient (aucun serveur)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from qdrant_client.http.exceptions import UnexpectedResponse

from src.services.vector import VectorService, VectorServiceError


@pytest.fixture
def vector_service() -> VectorService:
    svc = VectorService()
    svc._client = AsyncMock()  # type: ignore[assignment]
    return svc


class TestCreateCollection:
    async def test_creates_when_absent(self, vector_service: VectorService) -> None:
        vector_service._client.get_collection = AsyncMock(
            side_effect=UnexpectedResponse(
                status_code=404,
                reason_phrase="Not Found",
                content=b"",
                headers=httpx.Headers({"content-type": "application/json"}),
            )
        )
        vector_service._client.create_collection = AsyncMock()
        vector_service._client.create_payload_index = AsyncMock()

        await vector_service.create_collection(vector_size=512)

        vector_service._client.create_collection.assert_awaited_once()
        args = vector_service._client.create_collection.call_args.kwargs
        assert args["collection_name"] == vector_service.collection
        assert "sparse_vectors_config" not in args
        # Vérifier que le full-text index est créé
        vector_service._client.create_payload_index.assert_awaited_once()
        payload_args = vector_service._client.create_payload_index.call_args.kwargs
        assert payload_args["field_name"] == "text"
        assert payload_args["field_schema"].type == "text"

    async def test_skips_when_exists(self, vector_service: VectorService) -> None:
        vector_service._client.get_collection = AsyncMock(return_value="exists")
        vector_service._client.create_collection = AsyncMock()

        await vector_service.create_collection()

        vector_service._client.create_collection.assert_not_awaited()

    async def test_sets_vector_size(self, vector_service: VectorService) -> None:
        vector_service._client.get_collection = AsyncMock(
            side_effect=UnexpectedResponse(
                status_code=404,
                reason_phrase="Not Found",
                content=b"",
                headers=httpx.Headers({"content-type": "application/json"}),
            )
        )
        await vector_service.create_collection(vector_size=768)
        assert vector_service._vector_size == 768


class TestUpsertPoints:
    async def test_empty_returns_zero(self, vector_service: VectorService) -> None:
        assert await vector_service.upsert_points([]) == 0

    async def test_upsert_basic(self, vector_service: VectorService) -> None:
        vector_service._client.upsert = AsyncMock(
            return_value=SimpleNamespace(operation_id=None)
        )
        points = [
            {
                "id": "abc",
                "vector": [0.1, 0.2],
                "payload": {"text": "hello"},
            }
        ]
        result = await vector_service.upsert_points(points)
        assert result == 1
        call = vector_service._client.upsert.call_args
        qpoint = call.kwargs["points"][0]
        assert qpoint.id == "abc"
        assert qpoint.vector == [0.1, 0.2]
        assert qpoint.payload == {"text": "hello"}

    async def test_upsert_returns_operation_id(self, vector_service: VectorService) -> None:
        vector_service._client.upsert = AsyncMock(
            return_value=SimpleNamespace(operation_id=42)
        )
        points = [{"id": "x", "vector": [1.0], "payload": {}}]
        result = await vector_service.upsert_points(points)
        assert result == 42


class TestHybridSearch:
    async def test_dense_only(self, vector_service: VectorService) -> None:
        hits = [SimpleNamespace(id="1", score=0.9, payload={"text": "x"})]
        vector_service._client.query_points = AsyncMock(
            return_value=SimpleNamespace(points=hits)
        )

        results = await vector_service.hybrid_search([0.1, 0.2], None, top_k=5)
        assert results == [{"id": "1", "score": 0.9, "payload": {"text": "x"}}]
        call = vector_service._client.query_points.call_args.kwargs
        assert len(call["prefetch"]) == 1  # dense only

    async def test_dense_and_fulltext(self, vector_service: VectorService) -> None:
        vector_service._client.query_points = AsyncMock(
            return_value=SimpleNamespace(points=[])
        )
        await vector_service.hybrid_search([0.1], query_text="test query", top_k=10)
        call = vector_service._client.query_points.call_args.kwargs
        assert len(call["prefetch"]) == 2  # dense + fulltext
        assert call["limit"] == 10
        # Vérifier que le second prefetch contient le texte en query
        second_prefetch = call["prefetch"][1]
        assert second_prefetch.query == "test query"

    async def test_score_threshold_and_filter(self, vector_service: VectorService) -> None:
        from qdrant_client.http import models as qmodels

        vector_service._client.query_points = AsyncMock(
            return_value=SimpleNamespace(points=[])
        )
        filt = qmodels.Filter(must=[qmodels.FieldCondition(
            key="source_type", match=qmodels.MatchValue(value="file")
        )])
        await vector_service.hybrid_search(
            [0.1], None, score_threshold=0.5, filter_=filt
        )
        call = vector_service._client.query_points.call_args.kwargs
        assert call["score_threshold"] == 0.5
        assert call["query_filter"] == filt


class TestDeleteSource:
    async def test_deletes_matching_points(self, vector_service: VectorService) -> None:
        vector_service._client.scroll = AsyncMock(
            return_value=(
                [SimpleNamespace(id="1"), SimpleNamespace(id="2")],
                None,
            )
        )
        vector_service._client.delete = AsyncMock(
            return_value=SimpleNamespace(operation_id=99)
        )

        count = await vector_service.delete_source("source-1")
        assert count == 2
        vector_service._client.scroll.assert_awaited_once()
        delete_call = vector_service._client.delete.call_args.kwargs
        assert delete_call["points_selector"].points == ["1", "2"]

    async def test_no_matches_returns_zero(self, vector_service: VectorService) -> None:
        vector_service._client.scroll = AsyncMock(
            return_value=([], None)
        )
        vector_service._client.delete = AsyncMock()

        count = await vector_service.delete_source("source-none")
        assert count == 0
        vector_service._client.delete.assert_not_awaited()

    async def test_multi_page_scroll(self, vector_service: VectorService) -> None:
        vector_service._client.scroll = AsyncMock(
            side_effect=[
                ([SimpleNamespace(id="1")], "next"),
                ([SimpleNamespace(id="2")], None),
            ]
        )
        vector_service._client.delete = AsyncMock()

        count = await vector_service.delete_source("source-2")
        assert count == 2


class TestScrollSourceChunks:
    async def test_returns_payloads(self, vector_service: VectorService) -> None:
        vector_service._client.scroll = AsyncMock(
            return_value=(
                [SimpleNamespace(id="1", payload={"text": "a"})],
                None,
            )
        )
        chunks = await vector_service.scroll_source_chunks("src-1")
        assert chunks == [{"id": "1", "payload": {"text": "a"}}]
        call = vector_service._client.scroll.call_args.kwargs
        assert call["limit"] == 100

    async def test_respects_limit(self, vector_service: VectorService) -> None:
        vector_service._client.scroll = AsyncMock(return_value=([], None))
        await vector_service.scroll_source_chunks("src-1", limit=25)
        call = vector_service._client.scroll.call_args.kwargs
        assert call["limit"] == 25


class TestStatsHealth:
    async def test_stats_success(self, vector_service: VectorService) -> None:
        vector_service._client.get_collection = AsyncMock(
            return_value=SimpleNamespace(points_count=10)
        )
        stats = await vector_service.get_collection_stats()
        assert stats == {"points_count": 10}

    async def test_stats_error_returns_zero(self, vector_service: VectorService) -> None:
        vector_service._client.get_collection = AsyncMock(side_effect=UnexpectedResponse(
                status_code=503,
                reason_phrase="Service Unavailable",
                content=b"",
                headers=httpx.Headers({"content-type": "application/json"}),
            ))
        stats = await vector_service.get_collection_stats()
        assert stats == {"points_count": 0}

    async def test_health_true(self, vector_service: VectorService) -> None:
        vector_service._client.collection_exists = AsyncMock(return_value=True)
        assert await vector_service.health() is True

    async def test_health_false_on_error(self, vector_service: VectorService) -> None:
        vector_service._client.collection_exists = AsyncMock(side_effect=UnexpectedResponse(
                status_code=503,
                reason_phrase="Service Unavailable",
                content=b"",
                headers=httpx.Headers({"content-type": "application/json"}),
            ))
        assert await vector_service.health() is False


class TestSnapshot:
    async def test_snapshot_create(self, vector_service: VectorService) -> None:
        vector_service._client.create_snapshot = AsyncMock(
            return_value=SimpleNamespace(name="snap-1")
        )
        assert await vector_service.snapshot_create() == "snap-1"

    async def test_snapshot_none_raises(self, vector_service: VectorService) -> None:
        vector_service._client.create_snapshot = AsyncMock(return_value=None)
        with pytest.raises(VectorServiceError, match="snapshot"):
            await vector_service.snapshot_create()


class TestLifecycle:
    async def test_close(self, vector_service: VectorService) -> None:
        await vector_service.close()
        vector_service._client.close.assert_awaited_once()

    @patch("src.services.vector.AsyncQdrantClient")
    async def test_async_context_manager(self, mock_client_cls) -> None:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        svc = VectorService()
        svc._client = mock_client  # type: ignore[assignment]
        async with svc:
            pass
        mock_client.close.assert_awaited_once()

    @patch("src.services.vector.AsyncQdrantClient")
    def test_init_creates_client(self, mock_client_cls) -> None:
        svc = VectorService()
        mock_client_cls.assert_called_once()
        assert svc.collection
