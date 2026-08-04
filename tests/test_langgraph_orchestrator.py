"""Tests B6+B7 — build_graph LangGraph (services mockés, chemins éval ON/OFF)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from src.agents.langgraph_orchestrator import (
    PipelineServices,
    _job_result,
    build_graph,
    process_job,
    run_pipeline,
)


def _full_services() -> PipelineServices:
    """Services complets avec mocks AsyncMock — retour JSON conforme."""
    pool = AsyncMock()
    pool.embed.return_value = [[0.1] * 768]
    pool.generate.return_value = {
        "response": json.dumps(
            {"answer": "Réponse générée [s1].", "citations": ["s1"], "confidence": 0.9}
        )
    }
    pool.judge.return_value = {
        "response": json.dumps(
            {
                "score": 0.85,
                "critique": "Bonne réponse.",
                "checks_passed": ["factualite"],
                "flags": [],
                "confidence": 0.9,
            }
        )
    }
    pool.advocate.return_value = {
        "response": json.dumps(
            {
                "score": 0.9,
                "faille": "aucune",
                "claims_contested": [],
                "hallucination_risk": "low",
                "missing_context": [],
                "confidence": 0.9,
            }
        )
    }
    pool.evaluate.return_value = {
        "response": json.dumps(
            {
                "decision": "publish",
                "final_score": 0.88,
                "reasoning": "Convergence.",
                "revision_instructions": None,
                "verified_tier": "machine-confirmed",
                "confidence": 0.95,
            }
        )
    }

    vector = AsyncMock()
    vector.hybrid_search.return_value = [
        {"id": "d1", "score": 0.9, "payload": {"text": "Contexte utile [s1]", "source_id": "s1"}}
    ]

    lexical = AsyncMock()
    lexical.encode_to_dict.return_value = {1: 0.5, 2: 0.3}

    reranker = AsyncMock()
    reranker.rerank.return_value = [AsyncMock(index=0, score=0.95, text="Contexte utile [s1]")]

    wiki = AsyncMock()

    from src.agents.planner import PlannerAgent, PlannerOutput, SearchStrategy

    planner = PlannerAgent(pool)  # type: ignore[arg-type]
    planner.plan = AsyncMock(  # type: ignore[method-assign]
        return_value=PlannerOutput(
            intent="factual",
            sub_queries=["q"],
            search_strategy=SearchStrategy(),
            rerank_top_k=8,
        )
    )

    from src.agents.rewriter import RewriterAgent, RewriterOutput

    rewriter = RewriterAgent(pool)  # type: ignore[arg-type]
    rewriter.rewrite = AsyncMock(  # type: ignore[method-assign]
        return_value=RewriterOutput(rewritten_query="q réécrite")
    )

    from src.agents.advocate import AdvocateAgent
    from src.agents.context_assembler import ContextAssembler
    from src.agents.evaluator import EvaluatorAgent
    from src.agents.generator import GeneratorAgent
    from src.agents.judge import JudgeAgent

    return PipelineServices(
        pool=pool,
        vector=vector,
        lexical=lexical,
        reranker=reranker,
        wiki=wiki,
        planner=planner,
        rewriter=rewriter,
        assembler=ContextAssembler(),
        generator=GeneratorAgent(pool),  # type: ignore[arg-type]
        judge=JudgeAgent(pool),  # type: ignore[arg-type]
        advocate=AdvocateAgent(pool),  # type: ignore[arg-type]
        evaluator=EvaluatorAgent(pool),  # type: ignore[arg-type]
    )


def test_build_graph_returns_compilable_graph() -> None:
    graph = build_graph(PipelineServices())
    compiled = graph.compile()
    assert compiled is not None


async def test_run_pipeline_full_path() -> None:
    services = _full_services()
    state = await run_pipeline("Question ?", services)
    assert state.plan is not None
    assert state.rewritten_query == "q réécrite"
    assert len(state.search_results) == 1
    assert state.assembled is not None
    assert state.generated is not None
    assert "Réponse générée" in state.generated.answer
    assert state.wiki_note == "synthesis/question.md"
    services.wiki.write_page.assert_awaited()


async def test_run_pipeline_without_evaluation_skips_judge() -> None:
    services = _full_services()
    state = await run_pipeline("Question ?", services, evaluation_enabled=False)
    assert state.judge is None
    assert state.advocate is None
    assert state.evaluator is None
    services.pool.judge.assert_not_awaited()
    services.pool.advocate.assert_not_awaited()
    services.pool.evaluate.assert_not_awaited()


async def test_run_pipeline_with_evaluation() -> None:
    services = _full_services()
    state = await run_pipeline("Question ?", services, evaluation_enabled=True)
    assert state.judge is not None
    assert state.advocate is not None
    assert state.evaluator is not None
    assert state.evaluator["decision"] == "publish"
    services.pool.judge.assert_awaited_once()
    services.pool.advocate.assert_awaited_once()
    services.pool.evaluate.assert_awaited_once()
    services.wiki.update_index.assert_awaited()


async def test_run_pipeline_with_minimal_services() -> None:
    # Aucun service : le pipeline doit rebondir proprement (pas d'exception)
    state = await run_pipeline("Question ?", PipelineServices())
    assert state.rewritten_query == "Question ?"
    assert state.search_results == []
    assert state.generated is None


async def test_run_pipeline_planner_fallback() -> None:
    services = _full_services()
    services.planner = None  # type: ignore[assignment]
    state = await run_pipeline("Question ?", services)
    assert state.plan is not None
    assert state.plan.sub_queries == ["Question ?"]


async def test_run_pipeline_with_conversation_history() -> None:
    services = _full_services()
    rewrite_mock = services.rewriter.rewrite
    from src.agents.generator import GeneratorOutput

    services.generator.generate = AsyncMock(  # type: ignore[method-assign]
        return_value=GeneratorOutput(
            answer="Réponse générée [s1].",
            citations=[],
            confidence=0.9,
            reasoning_trace=None,
        )
    )
    generate_mock = services.generator.generate
    history = [
        {"role": "user", "content": f"msg {i}"} for i in range(10)
    ]
    await run_pipeline(
        "Question ?", services, conversation_history=history,
    )
    # ChatMemory avec 10 entrées (< 20 max) → historique complet
    from src.services.chat_memory import ChatMemory
    expected_window = ChatMemory(history).get_window()
    rewrite_mock.assert_awaited_with("Question ?", expected_window)
    generate_mock.assert_awaited()
    _, kwargs = generate_mock.await_args
    assert kwargs.get("conversation_history") == expected_window


async def test_run_pipeline_with_conversation_history_truncated() -> None:
    """Plus de 20 messages (chat_history_max*2) → troncature par ChatMemory."""
    services = _full_services()
    rewrite_mock = services.rewriter.rewrite
    from src.agents.generator import GeneratorOutput

    services.generator.generate = AsyncMock(  # type: ignore[method-assign]
        return_value=GeneratorOutput(
            answer="Réponse générée [s1].",
            citations=[],
            confidence=0.9,
            reasoning_trace=None,
        )
    )
    generate_mock = services.generator.generate
    history = [
        {"role": "user", "content": f"msg {i}"} for i in range(25)
    ]
    await run_pipeline(
        "Question ?", services, conversation_history=history,
    )
    from src.services.chat_memory import ChatMemory
    expected_window = ChatMemory(history).get_window()
    assert len(expected_window) == 20  # 1 ancre + 19 recent
    rewrite_mock.assert_awaited_with("Question ?", expected_window)
    _, kwargs = generate_mock.await_args
    assert kwargs.get("conversation_history") == expected_window


async def test_run_pipeline_without_conversation_history() -> None:
    services = _full_services()
    rewrite_mock = services.rewriter.rewrite
    from src.agents.generator import GeneratorOutput

    services.generator.generate = AsyncMock(  # type: ignore[method-assign]
        return_value=GeneratorOutput(
            answer="Réponse générée [s1].",
            citations=[],
            confidence=0.9,
            reasoning_trace=None,
        )
    )
    generate_mock = services.generator.generate
    await run_pipeline("Question ?", services, conversation_history=None)
    rewrite_mock.assert_awaited_with("Question ?", [])
    _, kwargs = generate_mock.await_args
    assert kwargs.get("conversation_history") == []


async def test_process_job_returns_serializable_result() -> None:
    """Worker C1 : un job de la file Redis produit un résultat JSON publiable."""
    services = _full_services()
    result = await process_job(
        {"job_id": "job-1", "query": "Question ?", "evaluation_enabled": False},
        services,
    )
    assert result["job_id"] == "job-1"
    assert result["query"] == "Question ?"
    assert "Réponse générée" in result["answer"]
    assert result["sources"] == [{"source_id": "s1", "score": 0.9}]
    assert result["wiki_note"] == "synthesis/question.md"
    json.dumps(result, ensure_ascii=False)  # sérialisable pour LPUSH


async def test_process_job_with_minimal_services() -> None:
    """Worker sans services : pas d'exception, résultat vide mais publiable."""
    result = await process_job({"job_id": "job-2", "query": "Question ?"}, PipelineServices())
    assert result["job_id"] == "job-2"
    assert result["answer"] is None
    assert result["sources"] == []
    json.dumps(result, ensure_ascii=False)


def test_job_result_drops_non_json_fields() -> None:
    """_job_result réduit l'état final (objets Python) à un dict JSON-safe."""
    from src.agents.langgraph_orchestrator import PipelineState

    state = PipelineState(
        query="Question ?",
        search_results=[{"payload": {"source_id": "s1"}, "score": 0.9}],
    )
    payload = _job_result(state, job_id="job-3")
    assert set(payload) == {"job_id", "query", "answer", "sources", "wiki_note"}
    assert payload["sources"] == [{"source_id": "s1", "score": 0.9}]
    json.dumps(payload, ensure_ascii=False)
