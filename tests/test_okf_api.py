"""Tests B8+B9 — endpoints OKF/Lint avec vault temporaire + /query pipeline mocké."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agents.wiki_agent import WikiAgent
from src.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return tmp_path / "vault"


@pytest.fixture
def wiki_agent(vault: Path) -> WikiAgent:
    agent = WikiAgent(vault)
    app.state.wiki_agent = agent
    return agent


# ── OKF endpoints ──────────────────────────────────────────────────

def test_okf_validate_valid_page(client: TestClient, wiki_agent: WikiAgent) -> None:
    import asyncio

    asyncio.run(
        wiki_agent.write_page(
            "concepts/bc250.md",
            "Le BC-250 est une carte Vulkan.",
            {"type": "concept", "title": "BC-250"},
        )
    )
    resp = client.post("/api/v1/okf/validate", json={"path": "concepts/bc250.md"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_okf_validate_invalid_page(client: TestClient, wiki_agent: WikiAgent) -> None:
    import asyncio

    asyncio.run(
        wiki_agent.write_page(
            "concepts/no_okf.md",
            "contenu sans frontmatter",
            {"type": "concept", "title": "No OKF"},
        )
    )
    resp = client.post(
        "/api/v1/okf/validate", json={"path": "concepts/no_okf.md"}
    )
    body = resp.json()
    assert body["valid"] is True  # write_page complète les champs OKF manquants


def test_okf_validate_missing_page(client: TestClient, wiki_agent: WikiAgent) -> None:
    resp = client.post("/api/v1/okf/validate", json={"path": "absent.md"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
    assert any("introuvable" in i for i in resp.json()["issues"])


def test_okf_validate_rejects_traversal(client: TestClient, wiki_agent: WikiAgent) -> None:
    resp = client.post("/api/v1/okf/validate", json={"path": "../escape.md"})
    assert resp.status_code == 400


def test_okf_validate_requires_body(client: TestClient) -> None:
    resp = client.post("/api/v1/okf/validate")
    assert resp.status_code == 422


def test_okf_list_lists_pages(client: TestClient, wiki_agent: WikiAgent) -> None:
    import asyncio

    asyncio.run(wiki_agent.write_page("a.md", "A", {"type": "concept"}))
    asyncio.run(wiki_agent.write_page("b.md", "B", {"type": "entity"}))
    resp = client.get("/api/v1/okf/list")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    paths = {p["path"] for p in body["pages"]}
    assert paths == {"a.md", "b.md"}


def test_okf_list_empty(client: TestClient, wiki_agent: WikiAgent) -> None:
    resp = client.get("/api/v1/okf/list")
    assert resp.status_code == 200
    assert resp.json() == {"pages": [], "count": 0}


def test_okf_show_returns_page(client: TestClient, wiki_agent: WikiAgent) -> None:
    import asyncio

    asyncio.run(
        wiki_agent.write_page(
            "concepts/x.md", "corps", {"type": "concept", "title": "X"}
        )
    )
    resp = client.get("/api/v1/okf/show", params={"path": "concepts/x.md"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["frontmatter"]["type"] == "concept"
    assert "corps" in body["content"]


def test_okf_show_missing_page_404(client: TestClient) -> None:
    resp = client.get("/api/v1/okf/show", params={"path": "absent.md"})
    assert resp.status_code == 404


def test_okf_show_requires_path(client: TestClient) -> None:
    resp = client.get("/api/v1/okf/show")
    assert resp.status_code == 422


# ── Lint endpoint ──────────────────────────────────────────────────

def test_lint_returns_report(client: TestClient, wiki_agent: WikiAgent) -> None:
    import asyncio

    asyncio.run(
        wiki_agent.write_page(
            "concepts/orphan.md",
            "contenu",
            {"type": "concept", "stale_after": "2000-01-01"},
        )
    )
    resp = client.get("/api/v1/lint")
    assert resp.status_code == 200
    body = resp.json()
    assert "concepts/orphan.md" in body["orphans"]
    assert "concepts/orphan.md" in body["stale"]
    for key in ("contradictions", "gaps", "frontmatter_issues"):
        assert key in body


# ── /query pipeline mocké ──────────────────────────────────────────

def _mock_state_dict() -> dict:
    return {
        "query": "Question ?",
        "conversation_history": [],
        "evaluation_enabled": False,
        "top_k": 8,
        "use_reranker": True,
        "score_threshold": None,
        "plan": None,
        "rewritten_query": "q",
        "search_results": [
            {"id": "d1", "score": 0.9, "payload": {"text": "Contexte [s1]", "source_id": "s1"}}
        ],
        "assembled": None,
        "generated": {
            "answer": "Réponse générée [s1].",
            "citations": ["s1"],
            "confidence": 0.9,
            "reasoning_trace": None,
        },
        "judge": None,
        "advocate": None,
        "evaluator": None,
        "wiki_note": None,
    }


def test_query_uses_pipeline(client: TestClient, wiki_agent: WikiAgent) -> None:
    """/query passe par run_pipeline (services mockés) — plus de concaténation brute."""
    from src.agents.langgraph_orchestrator import PipelineServices

    fake_pool = AsyncMock()
    fake_pool.embed.return_value = [[0.1] * 768]

    services = PipelineServices(pool=fake_pool)
    services.vector = AsyncMock()
    services.vector.hybrid_search.return_value = [
        {"id": "d1", "score": 0.9, "payload": {"text": "Contexte [s1]", "source_id": "s1"}}
    ]
    services.lexical = AsyncMock()
    services.lexical.encode_to_dict.return_value = {1: 0.5}
    services.generator = AsyncMock()
    services.generator.generate.return_value = _generator_output()

    app.state.ollama_pool = fake_pool
    app.state.vector_service = services.vector
    app.state.lexical_search = services.lexical
    app.state.reranker_service = services.reranker
    with (
        patch("src.api.main.PipelineServices", return_value=services),
        patch("src.api.main.settings.similarity_threshold", 0.3),
    ):
        resp = client.post(
            "/api/v1/query",
            json={"question": "Question ?", "use_reranker": False},
        )
    del app.state.ollama_pool
    assert resp.status_code == 200
    body = resp.json()
    assert "Réponse générée" in body["answer"]
    assert body["confidence"] == 0.9
    assert body["chunks_used"] == 1


def _generator_output():
    from src.agents.generator import GeneratorOutput

    return GeneratorOutput(
        answer="Réponse générée [s1].",
        citations=["s1"],
        confidence=0.9,
    )


def test_query_with_messages_sends_conversation_history(
    client: TestClient,
) -> None:
    """QueryRequest.messages extrait et passé à run_pipeline()."""
    from unittest.mock import AsyncMock, patch

    fake_pool = AsyncMock()
    fake_pool.embed.return_value = [[0.1] * 768]

    app.state.ollama_pool = fake_pool
    app.state.vector_service = AsyncMock()
    app.state.vector_service.hybrid_search.return_value = []
    app.state.lexical_search = AsyncMock()
    app.state.lexical_search.encode_to_dict.return_value = {1: 0.5}
    app.state.reranker_service = AsyncMock()

    messages_in = [
        {"role": "user", "content": "C'est quoi le BC-250 ?"},
        {"role": "assistant", "content": "Un GPU AMD."},
    ]

    mock_state = MagicMock()
    mock_state.search_results = []
    mock_state.assembled = None
    mock_state.generated = None
    mock_state.evaluator = None

    with patch("src.api.main.run_pipeline", return_value=mock_state) as mock_run:
        resp = client.post(
            "/api/v1/query",
            json={"question": "Et ensuite ?", "messages": messages_in},
        )

    del app.state.ollama_pool
    del app.state.vector_service
    del app.state.lexical_search
    del app.state.reranker_service
    assert resp.status_code == 200
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["conversation_history"] == [
        {"role": "user", "content": "C'est quoi le BC-250 ?"},
        {"role": "assistant", "content": "Un GPU AMD."},
    ]


def test_query_without_messages_passes_none(
    client: TestClient,
) -> None:
    """QueryRequest sans messages passe conversation_history=None."""
    from unittest.mock import AsyncMock, patch

    fake_pool = AsyncMock()
    fake_pool.embed.return_value = [[0.1] * 768]

    app.state.ollama_pool = fake_pool
    app.state.vector_service = AsyncMock()
    app.state.vector_service.hybrid_search.return_value = []
    app.state.lexical_search = AsyncMock()
    app.state.lexical_search.encode_to_dict.return_value = {1: 0.5}
    app.state.reranker_service = AsyncMock()

    mock_state = MagicMock()
    mock_state.search_results = []
    mock_state.assembled = None
    mock_state.generated = None
    mock_state.evaluator = None

    with patch("src.api.main.run_pipeline", return_value=mock_state) as mock_run:
        resp = client.post(
            "/api/v1/query",
            json={"question": "Pas d'historique ?"},
        )

    del app.state.ollama_pool
    del app.state.vector_service
    del app.state.lexical_search
    del app.state.reranker_service
    assert resp.status_code == 200
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs["conversation_history"] is None


def test_query_evaluation_enabled_flag(client: TestClient, wiki_agent: WikiAgent) -> None:
    """evaluation_enabled du body override le défaut (settings.evaluation_enabled=False)."""
    from src.agents.langgraph_orchestrator import PipelineServices

    fake_pool = AsyncMock()
    fake_pool.embed.return_value = [[0.1] * 768]
    fake_pool.judge.return_value = {
        "response": json.dumps(
            {
                "score": 0.8,
                "critique": "ok",
                "checks_passed": ["factualite"],
                "flags": [],
                "confidence": 0.9,
            }
        )
    }

    services = PipelineServices(pool=fake_pool)
    services.vector = AsyncMock()
    services.vector.hybrid_search.return_value = []
    services.lexical = AsyncMock()
    services.lexical.encode_to_dict.return_value = {1: 0.5}
    services.generator = AsyncMock()
    services.generator.generate.return_value = _generator_output()
    services.judge = AsyncMock()
    services.judge.evaluate.return_value = _judge_output()

    app.state.ollama_pool = fake_pool
    app.state.vector_service = services.vector
    app.state.lexical_search = services.lexical
    app.state.reranker_service = services.reranker
    with patch("src.api.main.PipelineServices", return_value=services):
        resp = client.post(
            "/api/v1/query",
            json={"question": "Question ?", "evaluation_enabled": True},
        )
    del app.state.ollama_pool
    assert resp.status_code == 200
    services.judge.evaluate.assert_awaited()


def _judge_output():
    from src.agents.judge import JudgeOutput

    return JudgeOutput(
        score=0.8,
        critique="ok",
        checks_passed=["factualite"],
        flags=[],
        confidence=0.9,
    )
