"""Tests RerankerService — AsyncMock sur OllamaClientPool (aucun réseau)."""
from unittest.mock import AsyncMock

import pytest

from src.services.ollama import OllamaError
from src.services.reranker import RerankerError, RerankerService, RerankResult


@pytest.fixture
def reranker() -> RerankerService:
    pool = AsyncMock()
    pool.rerank = AsyncMock(
        return_value=[0.1, 0.9, 0.5]
    )
    return RerankerService(ollama_pool=pool, model="bge-reranker-v2-m3")


class TestRerank:
    async def test_empty_documents_returns_empty(self) -> None:
        svc = RerankerService(ollama_pool=AsyncMock(), model="m")
        assert await svc.rerank("q", []) == []

    async def test_missing_pool_raises(self) -> None:
        svc = RerankerService(ollama_pool=None, model="m")
        with pytest.raises(RerankerError, match="non initialisé"):
            await svc.rerank("q", ["doc"])

    async def test_missing_model_raises(self) -> None:
        svc = RerankerService(ollama_pool=AsyncMock(), model=None)
        with pytest.raises(RerankerError, match="non configuré"):
            await svc.rerank("q", ["doc"])

    async def test_results_sorted_descending(self, reranker: RerankerService) -> None:
        results = await reranker.rerank("query", ["a", "b", "c"])
        assert [r.score for r in results] == [0.9, 0.5, 0.1]
        assert [r.index for r in results] == [1, 2, 0]
        assert [r.text for r in results] == ["b", "c", "a"]

    async def test_top_k_applied(self, reranker: RerankerService) -> None:
        results = await reranker.rerank("query", ["a", "b", "c"], top_k=2)
        assert len(results) == 2
        assert [r.text for r in results] == ["b", "c"]

    async def test_top_k_zero_returns_none(self, reranker: RerankerService) -> None:
        results = await reranker.rerank("query", ["a", "b", "c"], top_k=0)
        assert results == []

    async def test_rerank_result_dataclass(self) -> None:
        r = RerankResult(index=0, score=0.5, text="x")
        assert r.index == 0
        assert r.score == 0.5
        assert r.text == "x"

    async def test_ollama_error_wrapped(self) -> None:
        pool = AsyncMock()
        pool.rerank = AsyncMock(side_effect=OllamaError("node down"))
        svc = RerankerService(ollama_pool=pool, model="m")
        with pytest.raises(RerankerError, match="Échec reranking"):
            await svc.rerank("q", ["doc"])


class TestRerankWithPayload:
    async def test_empty_documents_returns_empty(self) -> None:
        svc = RerankerService(ollama_pool=AsyncMock(), model="m")
        assert await svc.rerank_with_payload("q", []) == []

    async def test_payloads_scored_and_sorted(self, reranker: RerankerService) -> None:
        docs = [
            {"id": 1, "text": "a"},
            {"id": 2, "text": "b"},
            {"id": 3, "text": "c"},
        ]
        scored = await reranker.rerank_with_payload("query", docs)
        assert [d["id"] for d in scored] == [2, 3, 1]
        assert scored[0]["rerank_score"] == 0.9
        assert scored[1]["rerank_score"] == 0.5
        assert scored[2]["rerank_score"] == 0.1

    async def test_payload_top_k(self, reranker: RerankerService) -> None:
        docs = [{"id": i, "text": str(i)} for i in range(3)]
        scored = await reranker.rerank_with_payload("query", docs, top_k=1)
        assert len(scored) == 1
        assert scored[0]["id"] == 1

    async def test_custom_text_key(self) -> None:
        pool = AsyncMock()
        pool.rerank = AsyncMock(return_value=[0.8, 0.2])
        svc = RerankerService(ollama_pool=pool, model="m")
        docs = [{"content": "x"}, {"content": "y"}]
        scored = await svc.rerank_with_payload("q", docs, text_key="content")
        assert len(scored) == 2

    async def test_missing_text_key_uses_empty(self) -> None:
        pool = AsyncMock()
        pool.rerank = AsyncMock(return_value=[0.8])
        svc = RerankerService(ollama_pool=pool, model="m")
        docs = [{"id": 1}]
        scored = await svc.rerank_with_payload("q", docs)
        assert scored[0]["rerank_score"] == 0.8


class TestLifecycle:
    async def test_close_closes_pool(self) -> None:
        pool = AsyncMock()
        svc = RerankerService(ollama_pool=pool, model="m")
        await svc.close()
        pool.close.assert_awaited_once()

    async def test_async_context_manager(self) -> None:
        pool = AsyncMock()
        async with RerankerService(ollama_pool=pool, model="m") as svc:
            assert isinstance(svc, RerankerService)
        pool.close.assert_awaited_once()

    async def test_close_without_pool_noop(self) -> None:
        svc = RerankerService(ollama_pool=None, model="m")
        await svc.close()


class TestFromSettings:
    def test_from_settings_returns_instance(self) -> None:
        svc = RerankerService.from_settings()
        assert isinstance(svc, RerankerService)
