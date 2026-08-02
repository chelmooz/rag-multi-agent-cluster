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

        await vector_service.create_collection(vector_size=512)

        vector_service._client.create_collection.assert_awaited_once()
        args = vector_service._client.create_collection.call_args.kwargs
        assert args["collection_name"] == vector_service.collection
        assert args["sparse_vectors_config"]["bm25"] is not None

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

    async def test_upsert_dict_sparse(self, vector_service: VectorService) -> None:
        vector_service._client.upsert = AsyncMock(
            return_value=SimpleNamespace(operation_id=None)
        )
        points = [
            {
                "id": "abc",
                "vector": [0.1, 0.2],
                "sparse_vector": {1: 0.5, 2: 0.5},
                "payload": {"text": "hello"},
            }
        ]
        result = await vector_service.upsert_points(points)
        assert result == 1
        call = vector_service._client.upsert.call_args
        qpoint = call.kwargs["points"][0]
        assert qpoint.id == "abc"
        assert "bm25" in qpoint.vector

    async def test_upsert_returns_operation_id(self, vector_service: VectorService) -> None:
        vector_service._client.upsert = AsyncMock(
            return_value=SimpleNamespace(operation_id=42)
        )
        points = [{"id": "x", "vector": [1.0], "payload": {}}]
        result = await vector_service.upsert_points(points)
        assert result == 42

    async def test_upsert_without_sparse(self, vector_service: VectorService) -> None:
        vector_service._client.upsert = AsyncMock(
            return_value=SimpleNamespace(operation_id=None)
        )
        points = [{"id": "x", "vector": [1.0, 0.0], "payload": {"text": "a"}}]
        result = await vector_service.upsert_points(points)
        assert result == 1
        call = vector_service._client.upsert.call_args
        qpoint = call.kwargs["points"][0]
        assert "bm25" not in qpoint.vector


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

    async def test_dense_and_sparse(self, vector_service: VectorService) -> None:
        vector_service._client.query_points = AsyncMock(
            return_value=SimpleNamespace(points=[])
        )
        sparse = {1: 0.5, 2: 0.5}
        await vector_service.hybrid_search([0.1], sparse, top_k=10)
        call = vector_service._client.query_points.call_args.kwargs
        assert len(call["prefetch"]) == 2
        assert call["limit"] == 10

    async def test_sparse_as_object(self, vector_service: VectorService) -> None:
        from qdrant_client.http import models as qmodels

        vector_service._client.query_points = AsyncMock(
            return_value=SimpleNamespace(points=[])
        )
        sv = qmodels.SparseVector(indices=[1], values=[0.5])
        await vector_service.hybrid_search([0.1], sv)
        call = vector_service._client.query_points.call_args.kwargs
        assert len(call["prefetch"]) == 2

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
