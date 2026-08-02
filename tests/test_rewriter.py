"""Tests B2 — RewriterAgent (mock-first, pool AsyncMock injecté)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.agents.rewriter import RewriterAgent, RewriterOutput
from src.agents.skills.loader import load_skill


@pytest.fixture
def pool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def rewriter(pool: AsyncMock) -> RewriterAgent:
    return RewriterAgent(pool)  # type: ignore[arg-type]


def test_build_prompt_contains_skill_and_history(rewriter: RewriterAgent) -> None:
    history = [{"role": "user", "content": "On parle du BC-250."}]
    prompt = rewriter.build_prompt("Et il supporte le Vulkan ?", history)
    assert load_skill("rewriter") in prompt
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["original_query"] == "Et il supporte le Vulkan ?"
    assert payload["conversation_history"] == history


def test_build_prompt_without_history(rewriter: RewriterAgent) -> None:
    payload = json.loads(rewriter.build_prompt("q").split("---\n\n", 1)[1])
    assert payload["conversation_history"] == []


async def test_rewrite_parses_valid_response(
    rewriter: RewriterAgent, pool: AsyncMock
) -> None:
    raw = {
        "rewritten_query": "Le BC-250 supporte-t-il Vulkan ?",
        "expanded_terms": ["Vulkan", "Mesa"],
        "resolved_references": {"il": "le BC-250"},
    }
    pool.fastcheck.return_value = {"response": json.dumps(raw)}
    out = await rewriter.rewrite("Et il supporte le Vulkan ?")
    assert isinstance(out, RewriterOutput)
    assert out.rewritten_query == "Le BC-250 supporte-t-il Vulkan ?"
    assert out.expanded_terms == ["Vulkan", "Mesa"]
    assert out.resolved_references == {"il": "le BC-250"}


async def test_rewrite_fallback_on_unparseable(
    rewriter: RewriterAgent, pool: AsyncMock
) -> None:
    pool.fastcheck.return_value = {"response": "???"}
    out = await rewriter.rewrite("Question originale ?")
    assert out.rewritten_query == "Question originale ?"


async def test_rewrite_fallback_on_pool_error(
    rewriter: RewriterAgent, pool: AsyncMock
) -> None:
    pool.fastcheck.side_effect = RuntimeError("node down")
    out = await rewriter.rewrite("Q")
    assert out.rewritten_query == "Q"
