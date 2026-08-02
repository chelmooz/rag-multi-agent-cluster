"""Tests B1 — PlannerAgent (mock-first, pool AsyncMock injecté)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.agents.planner import PlannerAgent, PlannerOutput, SearchStrategy, default_plan
from src.agents.skills.loader import load_skill


@pytest.fixture
def pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def planner(pool: AsyncMock) -> PlannerAgent:
    return PlannerAgent(pool)  # type: ignore[arg-type]


# ── build_prompt ───────────────────────────────────────────────────

def test_build_prompt_contains_skill_and_query(planner: PlannerAgent) -> None:
    prompt = planner.build_prompt("Quel modèle ?", conversation_context="ctx")
    assert load_skill("planner") in prompt
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["query"] == "Quel modèle ?"
    assert payload["conversation_context"] == "ctx"


def test_build_prompt_empty_context_defaults_to_empty(planner: PlannerAgent) -> None:
    payload = json.loads(planner.build_prompt("q").split("---\n\n", 1)[1])
    assert payload["conversation_context"] == ""


# ── plan — parsing nominal ─────────────────────────────────────────

async def test_plan_parses_valid_response(planner: PlannerAgent, pool: AsyncMock) -> None:
    raw = {
        "intent": "comparative",
        "sub_queries": ["a", "b"],
        "search_strategy": {
            "vector_weight": 0.6,
            "bm25_weight": 0.4,
            "use_sql": False,
            "use_vision": False,
        },
        "rerank_top_k": 8,
    }
    pool.fastcheck.return_value = {"response": json.dumps(raw)}
    out = await planner.plan("Différence entre A et B ?")
    assert isinstance(out, PlannerOutput)
    assert out.intent == "comparative"
    assert out.sub_queries == ["a", "b"]
    assert out.search_strategy.vector_weight == 0.6
    pool.fastcheck.assert_awaited_once()


async def test_plan_parses_json_fenced(planner: PlannerAgent, pool: AsyncMock) -> None:
    raw = json.dumps({"intent": "factual", "sub_queries": ["q1"]})
    pool.fastcheck.return_value = {"response": f"Voici:\n```json\n{raw}\n```"}
    out = await planner.plan("q")
    assert out.intent == "factual"
    assert out.sub_queries == ["q1"]


# ── plan — fallback ────────────────────────────────────────────────

async def test_plan_fallback_on_unparseable(
    planner: PlannerAgent, pool: AsyncMock
) -> None:
    pool.fastcheck.return_value = {"response": "je ne comprends pas"}
    out = await planner.plan("q")
    assert out == default_plan("q")


async def test_plan_fallback_on_pool_error(planner: PlannerAgent, pool: AsyncMock) -> None:
    pool.fastcheck.side_effect = RuntimeError("node down")
    out = await planner.plan("q")
    assert out == default_plan("q")


async def test_plan_fallback_on_invalid_schema(
    planner: PlannerAgent, pool: AsyncMock
) -> None:
    pool.fastcheck.return_value = {"response": json.dumps({"intent": "inconnu"})}
    out = await planner.plan("q")
    assert out == default_plan("q")


# ── default_plan ───────────────────────────────────────────────────

def test_default_plan_shape() -> None:
    plan = default_plan("Ma question ?")
    assert plan.intent == "factual"
    assert plan.sub_queries == ["Ma question ?"]
    assert plan.search_strategy == SearchStrategy()
    assert plan.rerank_top_k == 8
