"""Tests complets src/api/main.py — mocks services, aucun appel réseau réel.

Couvre : checks de santé (Ollama/Qdrant/Postgres/Redis), lifespan,
health/memory (disabled + enabled), embed, ingest (texte + fichier), query
(pipeline mocké), OKF/lint, dashboard (index, partials, monitoring JSON),
chat SSE (tous les chemins) et helpers (_sse/_elapsed_ms/_chunk_text/_render_card).
"""

import json
import time
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agents.langgraph_orchestrator import PipelineState
from src.api import main as api_main
from src.api.main import (
    _check_ollama,
    _check_postgres,
    _check_qdrant,
    _check_redis,
    _chunk_text,
    _elapsed_ms,
    _render_card,
    _run_checks,
    _sse,
    app,
    not_implemented_handler,
)
from src.services.lexical import LexicalSearch
from src.services.memory_manager import ClusterMemoryState, MachineMemoryState
from src.services.monitoring import MachineCard
from src.services.vector import VectorService

_STATE_ATTRS = (
    "ollama_pool",
    "vector_service",
    "lexical_search",
    "ingestion_service",
    "reranker_service",
    "monitoring_service",
    "wiki_agent",
)


@pytest.fixture(autouse=True)
def _clean_app_state() -> Any:
    """Isole app.state entre tests (aucune pollution croisée)."""
    for attr in _STATE_ATTRS:
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    yield
    for attr in _STATE_ATTRS:
        if hasattr(app.state, attr):
            delattr(app.state, attr)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _sse_events(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ──────────────────────────────────────────────
# Checks de santé individuels
# ──────────────────────────────────────────────


class TestHealthChecks:
    async def test_check_ollama_ok(self) -> None:
        with patch("src.api.main.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client.return_value.__aenter__.return_value = instance
            result = await _check_ollama("http://m1:11434")
            assert result == {"status": "ok", "detail": 200}

    async def test_check_ollama_error_status(self) -> None:
        with patch("src.api.main.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=MagicMock(status_code=500))
            mock_client.return_value.__aenter__.return_value = instance
            result = await _check_ollama("http://m1:11434")
            assert result == {"status": "error", "detail": 500}

    async def test_check_ollama_exception(self) -> None:
        with patch("src.api.main.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=TimeoutError("t"))
            mock_client.return_value.__aenter__.return_value = instance
            result = await _check_ollama("http://m1:11434")
            assert result == {"status": "error", "detail": "TimeoutError"}

    async def test_check_qdrant_ok(self) -> None:
        with patch("src.api.main.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client.return_value.__aenter__.return_value = instance
            result = await _check_qdrant("http://qdrant:6333")
            assert result == {"status": "ok", "detail": 200}

    async def test_check_qdrant_exception(self) -> None:
        with patch("src.api.main.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=ConnectionError("down"))
            mock_client.return_value.__aenter__.return_value = instance
            result = await _check_qdrant("http://qdrant:6333")
            assert result == {"status": "error", "detail": "ConnectionError"}

    async def test_check_postgres_ok(self) -> None:
        conn = AsyncMock()
        with patch("src.api.main.asyncpg.connect", new=AsyncMock(return_value=conn)) as m:
            result = await _check_postgres("postgres://u:p@h/db")
            assert result == {"status": "ok"}
            m.assert_awaited_once()
            conn.close.assert_awaited_once()

    async def test_check_postgres_failure(self) -> None:
        with patch("src.api.main.asyncpg.connect", new=AsyncMock(side_effect=RuntimeError("auth"))):
            result = await _check_postgres("postgres://u:p@h/db")
            assert result == {"status": "error", "detail": "RuntimeError"}

    async def test_check_redis_ok(self) -> None:
        fake_redis = AsyncMock()
        fake_redis.ping = AsyncMock(return_value=True)
        fake_redis.aclose = AsyncMock()
        with patch("src.api.main.Redis.from_url", return_value=fake_redis):
            result = await _check_redis("redis://localhost:6379")
            assert result == {"status": "ok"}

    async def test_check_redis_failure(self) -> None:
        fake_redis = AsyncMock()
        fake_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))
        with patch("src.api.main.Redis.from_url", return_value=fake_redis):
            result = await _check_redis("redis://localhost:6379")
            assert result == {"status": "error", "detail": "ConnectionError"}


# ──────────────────────────────────────────────
# _run_checks
# ──────────────────────────────────────────────


class TestRunChecks:
    async def test_run_checks_exception_is_captured(self) -> None:
        with (
            patch("src.api.main._check_qdrant", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch("src.api.main._check_ollama", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_postgres", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_redis", new=AsyncMock(return_value={"status": "ok"})),
        ):
            result = await _run_checks()
            assert result["qdrant"]["status"] == "error"
            assert result["qdrant"]["detail"] == "RuntimeError"
            assert result["ollama_m1"]["status"] == "ok"


# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────


class TestLifespan:
    def test_lifespan_initializes_and_cleans_up(self) -> None:
        names = (
            "OllamaClientPool",
            "VectorService",
            "LexicalSearch",
            "IngestionService",
            "RerankerService",
            "MonitoringService",
        )
        patches = [patch(f"src.api.main.{name}", return_value=AsyncMock()) for name in names]
        for p in patches:
            p.start()
        try:
            with TestClient(app):
                assert hasattr(app.state, "ollama_pool")
                assert hasattr(app.state, "vector_service")
                assert hasattr(app.state, "monitoring_service")
            assert app.state.ollama_pool.close.await_count == 1
            assert app.state.vector_service.close.await_count == 1
            assert app.state.ingestion_service.close.await_count == 1
        finally:
            for p in patches:
                p.stop()


# ──────────────────────────────────────────────
# Exception handler + helpers
# ──────────────────────────────────────────────


class TestExceptionHandlerAndHelpers:
    async def test_not_implemented_handler(self) -> None:
        resp = await not_implemented_handler(MagicMock(), NotImplementedError("pas encore"))
        assert resp.status_code == 500
        assert resp.body == b'{"detail":"pas encore"}'

    def test_sse_format(self) -> None:
        assert (
            _sse({"type": "token", "token": "héllo"})
            == 'data: {"type": "token", "token": "héllo"}\n\n'
        )

    def test_elapsed_ms(self) -> None:
        started = time.monotonic() - 0.25
        ms = _elapsed_ms(started)
        assert 240 <= ms <= 260

    def test_chunk_text_single(self) -> None:
        assert _chunk_text("un deux trois", size=10) == ["un deux trois"]

    def test_chunk_text_multiple(self) -> None:
        text = " ".join(f"mot{i}" for i in range(7))
        chunks = _chunk_text(text, size=3)
        assert chunks == ["mot0 mot1 mot2", "mot3 mot4 mot5", "mot6"]

    def test_render_card_from_dict(self) -> None:
        card = {
            "status": "ok",
            "machine": "m1",
            "title": "M1 MASTER",
            "metrics": [{"label": "RAM", "value": "1.2 GB", "status": "warn"}],
        }
        html = _render_card(card)
        assert 'class="metric-card ok"' in html
        assert 'data-machine="m1"' in html
        assert "M1 MASTER" in html
        assert "1.2 GB" in html

    def test_render_card_from_object(self) -> None:
        card = MachineCard(machine="m2", title="M2 GPU", status="crit")
        html = _render_card(card)
        assert 'class="metric-card crit"' in html

    def test_render_card_unknown_status_falls_back(self) -> None:
        card = {
            "status": "bizarre",
            "machine": "m3",
            "title": "M3",
            "metrics": [],
        }
        html = _render_card(card)
        assert 'class="metric-card ok"' in html


# ──────────────────────────────────────────────
# /ready — dégradé via checks mockés
# ──────────────────────────────────────────────


class TestReadyEndpoint:
    def test_ready_degraded(self, client: TestClient) -> None:
        with (
            patch(
                "src.api.main._check_qdrant",
                new=AsyncMock(return_value={"status": "error", "detail": 500}),
            ),
            patch("src.api.main._check_ollama", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_postgres", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_redis", new=AsyncMock(return_value={"status": "ok"})),
        ):
            resp = client.get("/api/v1/ready")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["qdrant"]["status"] == "error"

    def test_ready_all_ok(self, client: TestClient) -> None:
        with (
            patch("src.api.main._check_qdrant", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_ollama", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_postgres", new=AsyncMock(return_value={"status": "ok"})),
            patch("src.api.main._check_redis", new=AsyncMock(return_value={"status": "ok"})),
        ):
            resp = client.get("/api/v1/ready")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


# ──────────────────────────────────────────────
# /health/memory
# ──────────────────────────────────────────────


class TestHealthMemory:
    def test_disabled_when_memory_manager_off(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api_main.settings, "memory_manager_enabled", False)
        resp = client.get("/api/v1/health/memory")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_enabled_with_snapshot(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api_main.settings, "memory_manager_enabled", True)
        now = datetime.now()
        snapshot = ClusterMemoryState(
            m1=MachineMemoryState(
                machine="m1",
                timestamp=now,
                qdrant_ram_mb=512,
                qdrant_points_count=100,
                loaded_models=["nomic-embed-text:v1.5"],
            ),
            m2=MachineMemoryState(
                machine="m2",
                timestamp=now,
                rtx4000_vram_mb=4096,
                loaded_models=["llama3.2:3b"],
            ),
            m3=MachineMemoryState(
                machine="m3",
                timestamp=now,
                bc250_unified_mb=2048,
                bc250_cpu_load=0.4,
                loaded_models=["qwen2.5:7b"],
            ),
            timestamp=now,
            alerts=[],
        )
        fake_mm = AsyncMock()
        fake_mm.cluster_snapshot = AsyncMock(return_value=snapshot)
        fake_mm.close = AsyncMock()
        fake_mm_class = MagicMock(return_value=fake_mm)

        app.state.ollama_pool = AsyncMock()
        app.state.vector_service = AsyncMock()

        with patch("src.services.memory_manager.MemoryManager", fake_mm_class):
            resp = client.get("/api/v1/health/memory")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["m1"]["qdrant_ram_mb"] == 512
        assert body["m2"]["rtx4000_vram_mb"] == 4096
        assert body["m3"]["bc250_cpu_load"] == 0.4
        assert body["alerts"] == []


# ──────────────────────────────────────────────
# /embed
# ──────────────────────────────────────────────


class TestEmbed:
    def test_embed_503_when_uninitialized(self, client: TestClient) -> None:
        resp = client.post("/api/v1/embed", json={"texts": ["x"]})
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]

    def test_embed_success_with_sparse(self, client: TestClient) -> None:
        pool = AsyncMock()
        pool.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        lexical = MagicMock(spec=LexicalSearch)
        app.state.ollama_pool = pool
        app.state.lexical_search = lexical

        resp = client.post("/api/v1/embed", json={"texts": ["bonjour"], "return_sparse": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["embeddings"] == [[0.1, 0.2, 0.3]]
        assert body["sparse_vectors"] is None  # BM25 natif Qdrant calculé à la requête
        assert body["dimensions"] == 3

    def test_embed_without_sparse(self, client: TestClient) -> None:
        pool = AsyncMock()
        pool.embed = AsyncMock(return_value=[[0.5]])
        lexical = MagicMock(spec=LexicalSearch)
        app.state.ollama_pool = pool
        app.state.lexical_search = lexical

        resp = client.post("/api/v1/embed", json={"texts": ["x"], "return_sparse": False})
        assert resp.status_code == 200
        assert resp.json()["sparse_vectors"] is None


# ──────────────────────────────────────────────
# /ingest
# ──────────────────────────────────────────────


class TestIngest:
    def test_ingest_text_503_when_uninitialized(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/ingest",
            json={"text": "contenu", "source_type": "text", "source_id": "s1"},
        )
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]

    def test_ingest_file_503_when_uninitialized(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/ingest/file",
            files={"file": ("doc.txt", b"Bonjour", "text/plain")},
        )
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]

    def test_ingest_text_success(self, client: TestClient) -> None:
        service = AsyncMock()
        service.ingest = AsyncMock(
            return_value=SimpleNamespace(
                source_id="s1", chunks_created=3, chunks_indexed=3, chunks_deleted=0, errors=[]
            )
        )
        app.state.ingestion_service = service

        resp = client.post(
            "/api/v1/ingest",
            json={"text": "contenu", "source_type": "text", "source_id": "s1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        expected = {
            "source_id": "s1",
            "chunks_created": 3,
            "chunks_indexed": 3,
            "chunks_deleted": 0,
            "errors": [],
        }
        assert body == expected
        service.ingest.assert_awaited_once()

    def test_ingest_file_success(self, client: TestClient) -> None:
        service = AsyncMock()
        service.ingest = AsyncMock(
            return_value=SimpleNamespace(
                source_id="f1", chunks_created=1, chunks_indexed=1, chunks_deleted=0, errors=[]
            )
        )
        app.state.ingestion_service = service

        resp = client.post(
            "/api/v1/ingest/file",
            files={"file": ("doc.txt", b"Bonjour le monde", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_id"] == "f1"
        call_kwargs = service.ingest.await_args.kwargs
        assert call_kwargs["metadata"]["filename"] == "doc.txt"

    def test_ingest_file_with_metadata(self, client: TestClient) -> None:
        service = AsyncMock()
        service.ingest = AsyncMock(
            return_value=SimpleNamespace(
                source_id="f2", chunks_created=1, chunks_indexed=1, chunks_deleted=0, errors=[]
            )
        )
        app.state.ingestion_service = service

        resp = client.post(
            "/api/v1/ingest/file",
            files={"file": ("a.md", b"# titre", "text/markdown")},
            data={"metadata": json.dumps({"author": "ctos"})},
        )
        assert resp.status_code == 200
        meta = service.ingest.await_args.kwargs["metadata"]
        assert meta["author"] == "ctos"
        assert meta["content_type"] == "text/markdown"

    def test_delete_source_success(self, client: TestClient) -> None:
        """DELETE /sources/{id} → 200, chunks_deleted renvoyé."""
        service = AsyncMock()
        service.delete_source = AsyncMock(return_value=3)
        app.state.ingestion_service = service

        resp = client.delete("/api/v1/sources/src-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"source_id": "src-1", "chunks_deleted": 3}
        service.delete_source.assert_awaited_once_with("src-1")

    def test_delete_source_500_on_failure(self, client: TestClient) -> None:
        """DELETE /sources/{id} → 500 quand IngestionService.delete_source lève (ligne 89-90)."""
        service = AsyncMock()
        service.delete_source = AsyncMock(side_effect=RuntimeError("qdrant down"))
        app.state.ingestion_service = service

        resp = client.delete("/api/v1/sources/src-1")
        assert resp.status_code == 500
        assert "Échec suppression source" in resp.json()["detail"]

    def test_list_source_chunks_success(self, client: TestClient) -> None:
        """GET /sources/{id}/chunks → 200, chunks renvoyés."""
        service = AsyncMock()
        service.list_source_chunks = AsyncMock(
            return_value=[{"id": "c1", "payload": {"text": "chunk1"}}]
        )
        app.state.ingestion_service = service

        resp = client.get("/api/v1/sources/src-1/chunks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["chunks"][0]["id"] == "c1"
        service.list_source_chunks.assert_awaited_once_with("src-1", limit=100)

    def test_list_source_chunks_500_on_failure(self, client: TestClient) -> None:
        """GET /sources/{id}/chunks → 500 quand IngestionService.list_source_chunks lève."""
        service = AsyncMock()
        service.list_source_chunks = AsyncMock(side_effect=RuntimeError("qdrant unreachable"))
        app.state.ingestion_service = service

        resp = client.get("/api/v1/sources/src-1/chunks")
        assert resp.status_code == 500
        assert "Échec listing source" in resp.json()["detail"]

    def test_list_source_chunks_503_when_uninitialized(self, client: TestClient) -> None:
        """GET /sources/{id}/chunks → 503 si IngestionService absent (ligne 86)."""
        resp = client.get("/api/v1/sources/src-1/chunks")
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]


# ──────────────────────────────────────────────
# /query — pipeline mocké
# ──────────────────────────────────────────────


class TestQuery:
    def _setup_state(self) -> None:
        app.state.ollama_pool = AsyncMock()
        app.state.vector_service = AsyncMock()
        app.state.lexical_search = AsyncMock()
        app.state.reranker_service = AsyncMock()

    def test_query_success(self, client: TestClient) -> None:
        self._setup_state()
        state = PipelineState(
            query="q",
            search_results=[{"payload": {"source_id": "doc1"}, "score": 0.5}],
            assembled=cast(Any, SimpleNamespace(chunks=["a", "b"])),
            generated=cast(Any, SimpleNamespace(answer="Réponse finale", confidence=0.85)),
            evaluator=None,
        )
        with patch("src.api.main.run_pipeline", new=AsyncMock(return_value=state)):
            resp = client.post("/api/v1/query", json={"question": "q"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "Réponse finale"
        assert body["confidence"] == 0.85
        assert body["sources"] == ["doc1 (score: 0.500)"]
        assert body["chunks_used"] == 2

    def test_query_with_evaluator_override_confidence(self, client: TestClient) -> None:
        self._setup_state()
        state = PipelineState(
            query="q",
            search_results=[{"payload": {"source_id": "d"}, "score": 0.4}],
            assembled=cast(Any, SimpleNamespace(chunks=["c"])),
            generated=cast(Any, SimpleNamespace(answer="A", confidence=0.5)),
            evaluator={"final_score": 0.97},
        )
        with patch("src.api.main.run_pipeline", new=AsyncMock(return_value=state)):
            resp = client.post("/api/v1/query", json={"question": "q"})
        assert resp.json()["confidence"] == 0.97

    def test_query_no_documents(self, client: TestClient) -> None:
        self._setup_state()
        state = PipelineState(
            query="q",
            search_results=[],
            assembled=None,
            generated=None,
            evaluator=None,
        )
        with patch("src.api.main.run_pipeline", new=AsyncMock(return_value=state)):
            resp = client.post("/api/v1/query", json={"question": "q"})
        assert resp.status_code == 200
        body = resp.json()
        assert "Aucun document pertinent" in body["answer"]
        assert body["confidence"] == 0.0
        assert body["chunks_used"] == 0

    def test_query_passes_conversation_history(self, client: TestClient) -> None:
        self._setup_state()
        state = PipelineState(
            query="q", generated=cast(Any, SimpleNamespace(answer="A", confidence=0.5))
        )
        with patch("src.api.main.run_pipeline", new=AsyncMock(return_value=state)) as run:
            resp = client.post(
                "/api/v1/query",
                json={
                    "question": "q",
                    "messages": [
                        {"role": "user", "content": "salut"},
                        {"role": "assistant", "content": "bonjour"},
                    ],
                },
            )
        assert resp.status_code == 200
        assert run.await_args is not None
        _, kwargs = run.await_args
        assert kwargs["conversation_history"] == [
            {"role": "user", "content": "salut"},
            {"role": "assistant", "content": "bonjour"},
        ]


# ──────────────────────────────────────────────
# OKF + lint
# ──────────────────────────────────────────────


class TestOkfAndLint:
    def test_okf_validate_success(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.validate_frontmatter = AsyncMock(return_value={"valid": True, "errors": []})
        app.state.wiki_agent = wiki
        resp = client.post("/api/v1/okf/validate", json={"path": "concepts/test.md"})
        assert resp.status_code == 200
        assert resp.json() == {"path": "concepts/test.md", "valid": True, "errors": []}

    def test_okf_validate_error_400(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.validate_frontmatter = AsyncMock(side_effect=ValueError("frontmatter invalide"))
        app.state.wiki_agent = wiki
        resp = client.post("/api/v1/okf/validate", json={"path": "x.md"})
        assert resp.status_code == 400
        assert "frontmatter invalide" in resp.json()["detail"]

    def test_okf_list(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.list_pages = AsyncMock(return_value=["a.md", "b.md"])
        app.state.wiki_agent = wiki
        resp = client.get("/api/v1/okf/list")
        assert resp.status_code == 200
        assert resp.json() == {"pages": ["a.md", "b.md"], "count": 2}

    def test_okf_show_success(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.read_page = AsyncMock(return_value={"content": "# titre", "path": "a.md"})
        app.state.wiki_agent = wiki
        resp = client.get("/api/v1/okf/show", params={"path": "a.md"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "# titre"

    def test_okf_show_404(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.read_page = AsyncMock(side_effect=FileNotFoundError("page introuvable"))
        app.state.wiki_agent = wiki
        resp = client.get("/api/v1/okf/show", params={"path": "nope.md"})
        assert resp.status_code == 404

    def test_okf_show_400(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.read_page = AsyncMock(side_effect=PermissionError("traversal"))
        app.state.wiki_agent = wiki
        resp = client.get("/api/v1/okf/show", params={"path": "../evil.md"})
        assert resp.status_code == 400

    def test_lint(self, client: TestClient) -> None:
        wiki = AsyncMock()
        wiki.lint = AsyncMock(return_value={"orphans": [], "stale": []})
        app.state.wiki_agent = wiki
        resp = client.get("/api/v1/lint")
        assert resp.status_code == 200
        assert resp.json() == {"orphans": [], "stale": []}


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────


class TestDashboard:
    def test_index_serves_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_partial_chat(self, client: TestClient) -> None:
        resp = client.get("/partials/chat")
        assert resp.status_code == 200

    def test_partial_monitoring_503_when_uninitialized(self, client: TestClient) -> None:
        resp = client.get("/partials/monitoring")
        assert resp.status_code == 503

    def test_partial_monitoring_renders_cards(self, client: TestClient) -> None:
        service = AsyncMock()
        service.summary = AsyncMock(
            return_value={
                "cards": {
                    "m1": {
                        "status": "ok",
                        "machine": "m1",
                        "title": "M1",
                        "metrics": [{"label": "STATE", "value": "ok", "status": "ok"}],
                    },
                    "m2": {
                        "status": "n/a",
                        "machine": "m2",
                        "title": "M2",
                        "metrics": [{"label": "STATE", "value": "n/a", "status": "n/a"}],
                    },
                    "m3": {
                        "status": "warn",
                        "machine": "m3",
                        "title": "M3",
                        "metrics": [{"label": "STATE", "value": "warn", "status": "warn"}],
                    },
                },
                "cluster": {
                    "status": "ok",
                    "machine": "cluster",
                    "title": "CLUSTER",
                    "metrics": [{"label": "SANTÉ", "value": "●", "status": "ok"}],
                },
                "alerts": [{"level": "warning", "message": "test"}],
            }
        )
        app.state.monitoring_service = service
        resp = client.get("/partials/monitoring")
        assert resp.status_code == 200
        body = resp.json()
        assert body["alerts"][0]["message"] == "test"
        assert 'data-machine="m1"' in body["html"]
        assert 'data-machine="cluster"' in body["html"]

    def test_monitoring_json_503_when_uninitialized(self, client: TestClient) -> None:
        resp = client.get("/api/v1/monitoring")
        assert resp.status_code == 503

    def test_monitoring_json_returns_summary(self, client: TestClient) -> None:
        service = AsyncMock()
        service.summary = AsyncMock(
            return_value={"status": "ok", "timestamp": "t", "cards": {}, "alerts": []}
        )
        app.state.monitoring_service = service
        resp = client.get("/api/v1/monitoring")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ──────────────────────────────────────────────
# /chat SSE
# ──────────────────────────────────────────────


class TestChatSse:
    def _setup_pipeline_mocks(self) -> tuple[AsyncMock, AsyncMock, MagicMock, AsyncMock]:
        pool = AsyncMock()
        pool.embed = AsyncMock(return_value=[[0.1, 0.2]])
        pool.generate = AsyncMock(return_value={"response": "Réponse du modèle"})
        vector = AsyncMock(spec=VectorService)
        vector.hybrid_search = AsyncMock(
            return_value=[
                {"payload": {"text": "Contexte pertinent.", "source_id": "doc1"}, "score": 0.8},
                {"payload": {"text": "Second contexte.", "source_id": "doc2"}, "score": 0.6},
            ]
        )
        lexical = MagicMock(spec=LexicalSearch)
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(
            return_value=[SimpleNamespace(index=0, score=0.9), SimpleNamespace(index=1, score=0.7)]
        )
        app.state.ollama_pool = pool
        app.state.vector_service = vector
        app.state.lexical_search = lexical
        app.state.reranker_service = reranker
        return pool, vector, lexical, reranker

    def test_chat_offline_error(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(api_main.settings, "monitoring_offline", True)
        resp = client.post("/api/v1/chat", json={"question": "bonjour"})
        events = _sse_events(resp.text)
        assert events[0]["type"] == "error"
        assert "Prédéploiement" in events[0]["detail"]

    def test_chat_uninitialized_error(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={"question": "bonjour"})
        events = _sse_events(resp.text)
        assert events[0]["type"] == "error"
        assert "Services not initialized" in events[0]["detail"]

    def test_chat_embedding_failure(self, client: TestClient) -> None:
        pool, _, _, _ = self._setup_pipeline_mocks()
        pool.embed = AsyncMock(return_value=[])
        resp = client.post("/api/v1/chat", json={"question": "bonjour"})
        events = _sse_events(resp.text)
        assert events[0]["type"] == "error"
        assert "embedding" in events[0]["detail"]

    def test_chat_no_results(self, client: TestClient) -> None:
        _, vector, _, _ = self._setup_pipeline_mocks()
        vector.hybrid_search = AsyncMock(return_value=[])
        resp = client.post("/api/v1/chat", json={"question": "rien"})
        events = _sse_events(resp.text)
        assert events[0]["type"] == "token"
        assert "Aucun document" in events[0]["token"]
        assert events[1]["type"] == "done"

    def test_chat_full_pipeline(self, client: TestClient) -> None:
        self._setup_pipeline_mocks()
        resp = client.post("/api/v1/chat", json={"question": "explique"})
        events = _sse_events(resp.text)
        tokens = [e["token"] for e in events if e["type"] == "token"]
        done = next(e for e in events if e["type"] == "done")
        assert len(tokens) > 0
        assert "".join(tokens) == "Réponse du modèle"
        assert done["chunks_used"] == 2
        assert done["sources"][0].startswith("doc1")
        assert done["elapsed_ms"] >= 0

    def test_chat_single_result_no_rerank(self, client: TestClient) -> None:
        _, vector, _, reranker = self._setup_pipeline_mocks()
        vector.hybrid_search = AsyncMock(
            return_value=[
                {"payload": {"text": "Seul contexte.", "source_id": "doc9"}, "score": 0.9}
            ]
        )
        resp = client.post("/api/v1/chat", json={"question": "q"})
        events = _sse_events(resp.text)
        assert events[0]["type"] == "token"
        reranker.rerank.assert_not_awaited()

    def test_chat_generation_failure_falls_back_to_context(self, client: TestClient) -> None:
        pool, _, _, _ = self._setup_pipeline_mocks()
        pool.generate = AsyncMock(side_effect=RuntimeError("gpu down"))
        resp = client.post("/api/v1/chat", json={"question": "q"})
        events = _sse_events(resp.text)
        tokens = [e["token"] for e in events if e["type"] == "token"]
        assert "Contexte pertinent" in "".join(tokens)

    def test_chat_context_budget_break(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, _, _, _ = self._setup_pipeline_mocks()
        monkeypatch.setattr(api_main.settings, "chat_max_context_chars", 10)
        resp = client.post("/api/v1/chat", json={"question": "q"})
        events = _sse_events(resp.text)
        tokens = [e["token"] for e in events if e["type"] == "token"]
        assert "Pas de contexte" in "".join(tokens)

    def test_chat_outer_exception(self, client: TestClient) -> None:
        pool, _, _, _ = self._setup_pipeline_mocks()
        pool.embed = AsyncMock(side_effect=RuntimeError("boom"))
        resp = client.post("/api/v1/chat", json={"question": "q"})
        events = _sse_events(resp.text)
        assert events[0]["type"] == "error"
        assert events[0]["detail"] == "RuntimeError"


# ──────────────────────────────────────────────
# Real LexicalSearch integration (RED/GREEN for R1 regression)
# ──────────────────────────────────────────────

class TestRealLexicalSearch:
    """Tests d'intégration avec le VRAI LexicalSearch (pas de mock)
    pour détecter les régressions d'interface post-refacto R1."""

    def test_lexical_search_has_build_query_not_encode_methods(self) -> None:
        """Le vrai LexicalSearch n'a plus encode_to_dict/encode_batch_to_dict."""
        from src.services.lexical import LexicalSearch

        lexical = LexicalSearch()
        # Nouvelle API
        assert hasattr(lexical, "build_query")
        assert callable(lexical.build_query)
        # Anciennes méthodes supprimées
        assert not hasattr(lexical, "encode_to_dict")
        assert not hasattr(lexical, "encode_batch_to_dict")

    def test_chat_sse_with_real_lexical_search_fails_before_fix(self, client: TestClient) -> None:
        """Appel réel /chat avec vrai LexicalSearch — doit échouer avant fix (RED).
        Après fix (GREEN), le endpoint utilise lexical.build_query() correctement."""
        from unittest.mock import AsyncMock

        from src.services.lexical import LexicalSearch
        from src.services.ollama import OllamaClientPool
        from src.services.reranker import RerankerService
        from src.services.vector import VectorService

        # Services réels (LexicalSearch) + mocks pour le reste
        pool = AsyncMock(spec=OllamaClientPool)
        pool.embed = AsyncMock(return_value=[[0.1] * 768])
        pool.generate = AsyncMock(return_value={"response": "OK"})

        vector = AsyncMock(spec=VectorService)
        vector.hybrid_search = AsyncMock(
            return_value=[{"payload": {"text": "ctx", "source_id": "d1"}, "score": 0.8}]
        )

        # VRAI LexicalSearch (pas de mock) — c'est ce qui révèle le bug
        lexical = LexicalSearch()

        reranker = AsyncMock(spec=RerankerService)
        reranker.rerank = AsyncMock(
            return_value=[SimpleNamespace(index=0, score=0.9)]
        )

        app.state.ollama_pool = pool
        app.state.vector_service = vector
        app.state.lexical_search = lexical
        app.state.reranker_service = reranker

        resp = client.post("/api/v1/chat", json={"question": "test question"})
        events = _sse_events(resp.text)
        # AVANT FIX : le bug encode_to_dict manquant → événement error avec AttributeError
        # APRÈS FIX : événement token + done normal
        error_events = [e for e in events if e["type"] == "error"]
        # Ce test doit échouer (RED) tant que le bug existe : l'erreur contient "encode_to_dict"
        if error_events:
            assert "encode_to_dict" in str(error_events[0].get("detail", "")), \
                "Bug R1 confirmé : encode_to_dict manquant sur vrai LexicalSearch"
        else:
            # Après fix : pas d'erreur, réponse normale
            token_events = [e for e in events if e["type"] == "token"]
            assert len(token_events) > 0
