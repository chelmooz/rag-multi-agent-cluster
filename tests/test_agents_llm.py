"""Tests B5.2 — câblage LLM des agents Generator/Judge/Advocate/Evaluator.

Mock-first : pool AsyncMock injecté, fallback vérifié sur erreur/JSON
invalide, parsing nominal vérifié sur réponses conformes.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.agents.advocate import AdvocateAgent, AdvocateOutput
from src.agents.evaluator import EvaluatorAgent, EvaluatorOutput
from src.agents.generator import GeneratorAgent, GeneratorOutput
from src.agents.judge import JudgeAgent, JudgeOutput


@pytest.fixture
def pool() -> AsyncMock:
    return AsyncMock()


# ── GeneratorAgent ─────────────────────────────────────────────────

@pytest.fixture
def generator(pool: AsyncMock) -> GeneratorAgent:
    return GeneratorAgent(pool)  # type: ignore[arg-type]


async def test_generate_parses_valid_response(generator: GeneratorAgent, pool: AsyncMock) -> None:
    raw = {
        "answer": "Le modèle par défaut est **Qwen3-14B** [s1].",
        "citations": ["s1"],
        "confidence": 0.93,
        "reasoning_trace": "tiré de s1",
    }
    pool.generate.return_value = {"response": json.dumps(raw)}
    out = await generator.generate("q", [{"source_id": "s1", "text": "t"}])
    assert isinstance(out, GeneratorOutput)
    assert "Qwen3-14B" in out.answer
    assert out.citations == ["s1"]
    assert out.confidence == 0.93
    pool.generate.assert_awaited_once()


async def test_generate_fallback_on_pool_error(generator: GeneratorAgent, pool: AsyncMock) -> None:
    pool.generate.side_effect = RuntimeError("node down")
    out = await generator.generate("q", [])
    assert "n'est pas disponible" in out.answer
    assert out.citations == []
    assert out.confidence == 0.0


async def test_generate_fallback_on_unparseable(generator: GeneratorAgent, pool: AsyncMock) -> None:
    pool.generate.return_value = {"response": "réponse brouillon, pas JSON"}
    out = await generator.generate("q", [])
    assert "n'est pas disponible" in out.answer


# ── JudgeAgent ─────────────────────────────────────────────────────

@pytest.fixture
def judge(pool: AsyncMock) -> JudgeAgent:
    return JudgeAgent(pool)  # type: ignore[arg-type]


async def test_judge_parses_valid_response(judge: JudgeAgent, pool: AsyncMock) -> None:
    raw = {
        "score": 0.85,
        "critique": "Précise et fidèle.",
        "checks_passed": ["factualite", "coherence"],
        "flags": ["omission_source"],
        "confidence": 0.9,
    }
    pool.judge.return_value = {"response": json.dumps(raw)}
    out = await judge.evaluate("q", "réponse", [{"source_id": "s1", "text": "t"}])
    assert isinstance(out, JudgeOutput)
    assert out.score == 0.85
    assert out.checks_passed == ["factualite", "coherence"]
    assert out.flags == ["omission_source"]
    pool.judge.assert_awaited_once()


async def test_judge_fallback_on_pool_error(judge: JudgeAgent, pool: AsyncMock) -> None:
    pool.judge.side_effect = RuntimeError("m2 down")
    out = await judge.evaluate("q", "r", [])
    assert out.score == 0.0
    assert out.confidence == 0.0


async def test_judge_fallback_on_invalid_score(judge: JudgeAgent, pool: AsyncMock) -> None:
    pool.judge.return_value = {"response": json.dumps({"score": 99, "critique": "x"})}
    out = await judge.evaluate("q", "r", [])
    assert out.score == 0.0


async def test_judge_unload_calls_pool(judge: JudgeAgent, pool: AsyncMock) -> None:
    await judge.unload()
    pool.m2.unload_model.assert_awaited_once()


# ── AdvocateAgent ──────────────────────────────────────────────────

@pytest.fixture
def advocate(pool: AsyncMock) -> AdvocateAgent:
    return AdvocateAgent(pool)  # type: ignore[arg-type]


async def test_advocate_parses_valid_response(advocate: AdvocateAgent, pool: AsyncMock) -> None:
    raw = {
        "score": 0.3,
        "faille": "Risque OOM non qualifié.",
        "claims_contested": ["adapté à toutes les requêtes"],
        "hallucination_risk": "medium",
        "missing_context": ["marge VRAM"],
        "confidence": 0.93,
    }
    pool.advocate.return_value = {"response": json.dumps(raw)}
    out = await advocate.challenge("q", "r", [], {"score": 0.7})
    assert isinstance(out, AdvocateOutput)
    assert out.score == 0.3
    assert out.hallucination_risk == "medium"
    assert out.claims_contested == ["adapté à toutes les requêtes"]


async def test_advocate_fallback_on_pool_error(advocate: AdvocateAgent, pool: AsyncMock) -> None:
    pool.advocate.side_effect = RuntimeError("m2 down")
    out = await advocate.challenge("q", "r", [], {})
    assert out.score == 0.0
    assert out.hallucination_risk == "high"


async def test_advocate_fallback_on_invalid_risk(advocate: AdvocateAgent, pool: AsyncMock) -> None:
    raw = {"score": 0.5, "faille": "x", "hallucination_risk": "extreme"}
    pool.advocate.return_value = {"response": json.dumps(raw)}
    out = await advocate.challenge("q", "r", [], {})
    assert out.hallucination_risk == "high"


async def test_advocate_unload_calls_pool(advocate: AdvocateAgent, pool: AsyncMock) -> None:
    await advocate.unload()
    pool.m2.unload_model.assert_awaited_once()


# ── EvaluatorAgent ─────────────────────────────────────────────────

@pytest.fixture
def evaluator(pool: AsyncMock) -> EvaluatorAgent:
    return EvaluatorAgent(pool)  # type: ignore[arg-type]


async def test_synthesize_parses_valid_response(evaluator: EvaluatorAgent, pool: AsyncMock) -> None:
    raw = {
        "decision": "publish",
        "final_score": 0.91,
        "reasoning": "Convergence Judge/Avocat.",
        "revision_instructions": None,
        "verified_tier": "machine-confirmed",
        "confidence": 0.95,
    }
    pool.evaluate.return_value = {"response": json.dumps(raw)}
    relay = {
        "query": "q",
        "response": "r",
        "judge": {"score": 0.92},
        "advocate": {"score": 0.9, "hallucination_risk": "low"},
    }
    out = await evaluator.synthesize(relay)
    assert isinstance(out, EvaluatorOutput)
    assert out.decision == "publish"
    assert out.verified_tier == "machine-confirmed"
    assert out.revision_instructions is None


async def test_synthesize_fallback_on_pool_error(
    evaluator: EvaluatorAgent, pool: AsyncMock
) -> None:
    pool.evaluate.side_effect = RuntimeError("m1 down")
    relay = {"query": "q", "response": "r", "judge": {}, "advocate": {}}
    out = await evaluator.synthesize(relay)
    assert out.decision == "reject"
    assert out.final_score == 0.0


async def test_synthesize_fallback_on_invalid_decision(
    evaluator: EvaluatorAgent, pool: AsyncMock
) -> None:
    raw = {"decision": "bof", "final_score": 0.5, "reasoning": "x"}
    pool.evaluate.return_value = {"response": json.dumps(raw)}
    relay = {"query": "q", "response": "r", "judge": {}, "advocate": {}}
    out = await evaluator.synthesize(relay)
    assert out.decision == "reject"


# ── update_frontmatter ─────────────────────────────────────────────

async def test_update_frontmatter_sets_verified(
    evaluator: EvaluatorAgent, tmp_path, monkeypatch
) -> None:
    from src.agents import wiki_agent as wa

    vault = tmp_path / "vault"
    page = vault / "concepts" / "ok.md"
    page.parent.mkdir(parents=True)
    fm_text = "---\ntype: concept\ntitle: OK\nstatus: draft\n"
    fm_text += "verified: unverified\ncreated: 2026-08-02\n---\ncontenu\n"
    page.write_text(fm_text, encoding="utf-8")
    original_cls = wa.WikiAgent
    monkeypatch.setattr(wa, "WikiAgent", lambda vault_path=None: original_cls(vault))
    await evaluator.update_frontmatter("concepts/ok.md", "machine-confirmed")
    updated = page.read_text(encoding="utf-8")
    assert "verified: machine-confirmed" in updated
    assert "title: OK" in updated
    assert "contenu" in updated


async def test_update_frontmatter_rejects_bad_tier(evaluator: EvaluatorAgent) -> None:
    with pytest.raises(ValueError, match="trust_tier"):
        await evaluator.update_frontmatter("page.md", "inconnu")


async def test_update_frontmatter_missing_page(
    evaluator: EvaluatorAgent, tmp_path, monkeypatch
) -> None:
    from src.agents import wiki_agent as wa

    original_cls = wa.WikiAgent
    monkeypatch.setattr(wa, "WikiAgent", lambda vault_path=None: original_cls(tmp_path / "vault"))
    with pytest.raises(Exception, match="introuvable"):
        await evaluator.update_frontmatter("nope.md", "machine-confirmed")
