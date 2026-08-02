"""Tests OllamaClientPool + OllamaClient — mocks httpx (aucun nœud réel)."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.ollama import (
    CircuitBreakerOpenError,
    CircuitBreakerState,
    OllamaClient,
    OllamaClientPool,
    OllamaError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)


class TestCircuitBreakerState:
    def test_initial_state(self) -> None:
        cb = CircuitBreakerState()
        assert cb.failures == 0
        assert not cb.is_open

    def test_record_failure_opens_after_max(self) -> None:
        cb = CircuitBreakerState(max_failures=2, cooldown=60.0)
        cb.record_failure()
        assert not cb.is_open
        cb.record_failure()
        assert cb.is_open

    def test_record_success_resets(self) -> None:
        cb = CircuitBreakerState(max_failures=1, cooldown=60.0)
        cb.record_failure()
        assert cb.is_open
        cb.record_success()
        assert cb.failures == 0
        assert not cb.is_open

    def test_reset(self) -> None:
        cb = CircuitBreakerState(max_failures=1, cooldown=60.0)
        cb.record_failure()
        cb.reset()
        assert cb.failures == 0
        assert not cb.is_open

    def test_is_open_false_after_cooldown(self) -> None:
        cb = CircuitBreakerState(max_failures=1, cooldown=1.0)
        cb.record_failure()
        assert cb.is_open
        time.sleep(1.1)
        assert not cb.is_open


@pytest.fixture
def client() -> OllamaClient:
    c = OllamaClient("http://m1:11434", timeout=5, max_retries=1)
    c._client = AsyncMock()  # type: ignore[assignment]
    return c


class TestOllamaClientGenerate:
    async def test_generate_payload(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(return_value=_http_resp({"response": "hi"}))
        data = await client.generate("llama3", "hello", temperature=0.5)
        assert data == {"response": "hi"}
        call = client._client.request.call_args
        assert call.args[1] == "/api/generate"
        payload = call.kwargs["json"]
        assert payload["model"] == "llama3"
        assert payload["prompt"] == "hello"
        assert payload["stream"] is False
        assert payload["temperature"] == 0.5

    async def test_base_url_strips_trailing_slash(self) -> None:
        c = OllamaClient("http://m1:11434/", timeout=5)
        assert c.base_url == "http://m1:11434"
        await c.close()

    async def test_timeout_raises_wrapped(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            side_effect=httpx.TimeoutException("slow")
        )
        with pytest.raises(OllamaTimeoutError):
            await client.generate("m", "p")
        assert client._cb.failures == 0  # timeout ne compte pas comme failure


class TestOllamaClientEmbed:
    async def test_embed_returns_embeddings(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            return_value=_http_resp({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
        )
        result = await client.embed("nomic", ["a", "b"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        call = client._client.request.call_args
        assert call.kwargs["json"]["input"] == ["a", "b"]

    async def test_embed_missing_key_returns_empty(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(return_value=_http_resp({}))
        assert await client.embed("nomic", ["a"]) == []


class TestOllamaClientRerank:
    async def test_rerank_scores_in_order(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            return_value=_http_resp(
                {"results": [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.3}]}
            )
        )
        scores = await client.rerank("bge", "q", ["a", "b"])
        assert scores == [0.3, 0.9]

    async def test_rerank_missing_results_zeros(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(return_value=_http_resp({}))
        assert await client.rerank("bge", "q", ["a", "b"]) == [0.0, 0.0]

    async def test_rerank_out_of_range_index_raises(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            return_value=_http_resp({"results": [{"index": 5, "score": 0.9}]})
        )
        with pytest.raises(IndexError):
            await client.rerank("bge", "q", ["a"])


class TestOllamaClientHealthModels:
    async def test_health_true(self, client: OllamaClient) -> None:
        client._client.get = AsyncMock(
            return_value=MagicMock(status_code=200)
        )
        assert await client.health() is True

    async def test_health_false_on_error(self, client: OllamaClient) -> None:
        client._client.get = AsyncMock(side_effect=httpx.ConnectError("no"))
        assert await client.health() is False

    async def test_list_models(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            return_value=_http_resp({"models": [{"name": "x", "size_vram": 100}]})
        )
        models = await client.list_models()
        assert models == [{"name": "x", "size_vram": 100}]

    async def test_list_models_empty(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(return_value=_http_resp({}))
        assert await client.list_models() == []

    async def test_unload_model_true(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(return_value=_http_resp({"done": True}))
        assert await client.unload_model("llama3") is True
        call = client._client.request.call_args
        assert call.kwargs["json"]["keep_alive"] == "0s"

    async def test_unload_model_false_on_error(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("down")
        )
        assert await client.unload_model("llama3") is False


class TestRequestMechanics:
    async def test_http_status_error_records_failure(
        self, client: OllamaClient
    ) -> None:
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "internal error"
        client._client.request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=resp
            )
        )
        with pytest.raises(OllamaError, match="HTTP 500"):
            await client.generate("m", "p")
        assert client._cb.failures == 1

    async def test_connect_error_wraps_unavailable(self, client: OllamaClient) -> None:
        client._client.request = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(OllamaUnavailableError, match="Impossible de joindre"):
            await client.generate("m", "p")
        assert client._cb.failures == 1

    async def test_open_circuit_raises_immediately(self, client: OllamaClient) -> None:
        client._cb.open_until = time.time() + 60
        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker ouvert"):
            await client.generate("m", "p")
        client._client.request.assert_not_called()

    async def test_success_records_success(self, client: OllamaClient) -> None:
        client._cb.record_failure()
        client._client.request = AsyncMock(return_value=_http_resp({"ok": True}))
        await client.generate("m", "p")
        assert client._cb.failures == 0

    async def test_reset_circuit_breaker(self, client: OllamaClient) -> None:
        client._cb.record_failure()
        client.reset_circuit_breaker()
        assert client._cb.failures == 0


class TestClientLifecycle:
    async def test_close(self, client: OllamaClient) -> None:
        await client.close()
        client._client.aclose.assert_awaited_once()

    async def test_async_context_manager(self) -> None:
        c = OllamaClient("http://x:1", timeout=5)
        c._client = AsyncMock()  # type: ignore[assignment]
        async with c:
            pass
        c._client.aclose.assert_awaited_once()

    async def test_retry_after_transient_error(self) -> None:
        c = OllamaClient("http://x:1", timeout=5, max_retries=1)
        c._client = AsyncMock()  # type: ignore[assignment]
        c._client.request = AsyncMock(
            side_effect=[
                httpx.ConnectError("first"),
                _http_resp({"ok": True}),
            ]
        )
        data = await c.generate("m", "p")
        assert data == {"ok": True}
        assert c._client.request.await_count == 2

    async def test_wrapped_error_after_retries_exhausted(self) -> None:
        c = OllamaClient("http://x:1", timeout=5, max_retries=1)
        c._client = AsyncMock()  # type: ignore[assignment]
        c._client.request = AsyncMock(
            side_effect=httpx.ConnectError("always down")
        )
        with pytest.raises(OllamaUnavailableError, match="Impossible de joindre"):
            await c.generate("m", "p")
        assert c._client.request.await_count == 2  # 1 retry effectué


def _http_resp(json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.status_code = 200
    return resp


@pytest.fixture
def pool() -> OllamaClientPool:
    p = OllamaClientPool.__new__(OllamaClientPool)
    p.m1 = AsyncMock()
    p.m2 = AsyncMock()
    p.m3 = AsyncMock()
    p._settings = MagicMock()
    return p


class TestPoolRouting:
    async def test_embed_primary_m1(self, pool: OllamaClientPool) -> None:
        pool._settings.embedding_model = "nomic"
        pool.m1.embed = AsyncMock(return_value=[[0.1]])
        result = await pool.embed(["t"])
        assert result == [[0.1]]
        pool.m1.embed.assert_awaited_once_with("nomic", ["t"])

    async def test_embed_fallback_m2(self, pool: OllamaClientPool) -> None:
        pool._settings.embedding_model = "nomic"
        pool._settings.embedding_host = "m1"
        pool.m1.embed = AsyncMock(side_effect=OllamaUnavailableError("down"))
        pool.m2.embed = AsyncMock(return_value=[[0.2]])
        result = await pool.embed(["t"])
        assert result == [[0.2]]

    async def test_embed_no_fallback_reraises(self, pool: OllamaClientPool) -> None:
        pool._settings.embedding_model = "nomic"
        pool._settings.embedding_host = "m3"
        pool.m1.embed = AsyncMock(side_effect=OllamaUnavailableError("down"))
        with pytest.raises(OllamaUnavailableError):
            await pool.embed(["t"])

    async def test_generate_routes_m3(self, pool: OllamaClientPool) -> None:
        pool._settings.generator_model = "gen14b"
        pool.m3.generate = AsyncMock(return_value={"response": "ok"})
        result = await pool.generate("hello")
        assert result == {"response": "ok"}
        pool.m3.generate.assert_awaited_once_with("gen14b", "hello")

    async def test_generate_custom_model(self, pool: OllamaClientPool) -> None:
        pool.m3.generate = AsyncMock(return_value={})
        await pool.generate("p", model="custom")
        pool.m3.generate.assert_awaited_once_with("custom", "p")

    async def test_rerank_routes_m2(self, pool: OllamaClientPool) -> None:
        pool._settings.reranker_model = "bge"
        pool.m2.rerank = AsyncMock(return_value=[0.5])
        result = await pool.rerank("q", ["d"])
        assert result == [0.5]
        pool.m2.rerank.assert_awaited_once_with("bge", "q", ["d"])

    async def test_judge_generates_and_unloads(self, pool: OllamaClientPool) -> None:
        pool._settings.judge_model = "judge"
        pool.m2.generate = AsyncMock(return_value={"response": "ok"})
        pool.m2.unload_model = AsyncMock(return_value=True)
        result = await pool.judge("p")
        assert result == {"response": "ok"}
        pool.m2.unload_model.assert_awaited_once_with("judge")

    async def test_advocate_generates_and_unloads(self, pool: OllamaClientPool) -> None:
        pool._settings.advocate_model = "adv"
        pool.m2.generate = AsyncMock(return_value={})
        pool.m2.unload_model = AsyncMock(return_value=True)
        await pool.advocate("p")
        pool.m2.unload_model.assert_awaited_once_with("adv")

    async def test_evaluate_routes_m1(self, pool: OllamaClientPool) -> None:
        pool._settings.evaluator_model = "eval"
        pool.m1.generate = AsyncMock(return_value={})
        await pool.evaluate("p")
        pool.m1.generate.assert_awaited_once_with("eval", "p")

    async def test_text2sql_routes_m3(self, pool: OllamaClientPool) -> None:
        pool._settings.text2sql_model = "sql"
        pool.m3.generate = AsyncMock(return_value={})
        await pool.text2sql("p")
        pool.m3.generate.assert_awaited_once_with("sql", "p")

    async def test_vision_sends_image(self, pool: OllamaClientPool) -> None:
        pool._settings.vision_model = "vision"
        pool.m3._request = AsyncMock(return_value={})
        await pool.vision("p", "BASE64IMG")
        call = pool.m3._request.call_args
        assert call.args[1] == "/api/generate"
        assert call.kwargs["json"]["images"] == ["BASE64IMG"]

    async def test_fastcheck_routes_m3(self, pool: OllamaClientPool) -> None:
        pool._settings.fastcheck_model = "fast"
        pool.m3.generate = AsyncMock(return_value={})
        await pool.fastcheck("p")
        pool.m3.generate.assert_awaited_once_with("fast", "p")

    async def test_health_all_parallel(self, pool: OllamaClientPool) -> None:
        pool.m1.health = AsyncMock(return_value=True)
        pool.m2.health = AsyncMock(return_value=False)
        pool.m3.health = AsyncMock(return_value=True)
        result = await pool.health_all()
        assert result == {"m1": True, "m2": False, "m3": True}

    async def test_close_all(self, pool: OllamaClientPool) -> None:
        await pool.close()
        pool.m1.close.assert_awaited_once()
        pool.m2.close.assert_awaited_once()
        pool.m3.close.assert_awaited_once()

    def test_reset_all_circuit_breakers(self, pool: OllamaClientPool) -> None:
        pool.m1.reset_circuit_breaker = MagicMock()
        pool.m2.reset_circuit_breaker = MagicMock()
        pool.m3.reset_circuit_breaker = MagicMock()
        pool.reset_all_circuit_breakers()
        pool.m1.reset_circuit_breaker.assert_called_once()
        pool.m2.reset_circuit_breaker.assert_called_once()
        pool.m3.reset_circuit_breaker.assert_called_once()


class TestPoolInit:
    @patch("src.services.ollama.OllamaClient")
    def test_init_creates_three_clients(self, mock_client_cls) -> None:
        OllamaClientPool()
        assert mock_client_cls.call_count == 3
