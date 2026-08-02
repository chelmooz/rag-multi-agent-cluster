"""Tests B5.3 — build_prompt()/skill_reference() sans mock LLM.

Discipline TDD : vérifie que les prompts assemblés contiennent les
sections attendues (skill + données du relay) et que le loader est
fail-fast sur rôle/fichier manquant.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from src.agents.advocate import AdvocateAgent
from src.agents.evaluator import EvaluatorAgent
from src.agents.generator import GeneratorAgent
from src.agents.judge import JudgeAgent
from src.agents.skills.loader import ROLES, clear_cache, load_skill, skill_reference
from src.agents.wiki_agent import WikiAgent


@pytest.fixture(autouse=True)
def _clear_skill_cache() -> None:
    clear_cache()


def _pool() -> AsyncMock:
    return AsyncMock()


def _generator() -> GeneratorAgent:
    return GeneratorAgent(_pool())  # type: ignore[arg-type]


def _judge() -> JudgeAgent:
    return JudgeAgent(_pool())  # type: ignore[arg-type]


def _advocate() -> AdvocateAgent:
    return AdvocateAgent(_pool())  # type: ignore[arg-type]


def _evaluator() -> EvaluatorAgent:
    return EvaluatorAgent(_pool())  # type: ignore[arg-type]


# ── Loader ──────────────────────────────────────────────────────────

def test_roles_expected_set() -> None:
    expected = {
        "generator",
        "judge",
        "advocate",
        "evaluator",
        "wiki_agent",
        "planner",
        "rewriter",
    }
    assert expected == ROLES


def test_load_skill_returns_nonempty_for_each_role() -> None:
    for role in ROLES:
        skill = load_skill(role)
        assert isinstance(skill, str)
        assert len(skill) > 100, f"{role} SKILL.md trop court"


def test_load_skill_contains_json_schema_reference() -> None:
    for role in (
        "generator",
        "judge",
        "advocate",
        "evaluator",
        "planner",
        "rewriter",
    ):
        skill = load_skill(role)
        assert "_output_v1" in skill or "Réponds UNIQUEMENT en JSON" in skill


def test_load_skill_unknown_role_raises() -> None:
    with pytest.raises(ValueError, match="Rôle inconnu"):
        load_skill("inexistant")


def test_load_skill_missing_file_raises(tmp_path, monkeypatch) -> None:
    # Rôle connu mais fichier absent → FileNotFoundError
    monkeypatch.setattr("src.agents.skills.loader._SKILLS_DIR", tmp_path)
    clear_cache()
    (tmp_path / "generator").mkdir()
    with pytest.raises(FileNotFoundError, match="introuvable"):
        load_skill("generator")


def test_load_skill_cache_hit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("src.agents.skills.loader._SKILLS_DIR", tmp_path)
    role_dir = tmp_path / "judge"
    role_dir.mkdir()
    (role_dir / "SKILL.md").write_text("v1", encoding="utf-8")
    clear_cache()
    assert load_skill("judge") == "v1"
    # Modifier le fichier ne change pas le cache
    (role_dir / "SKILL.md").write_text("v2", encoding="utf-8")
    assert load_skill("judge") == "v1"
    clear_cache()
    assert load_skill("judge") == "v2"


def test_skill_reference_alias() -> None:
    assert skill_reference("generator") == load_skill("generator")


def test_skill_reference_unknown_role_raises() -> None:
    with pytest.raises(ValueError, match="Rôle inconnu"):
        skill_reference("nope")


# ── build_prompt — GeneratorAgent ───────────────────────────────────

def test_generator_build_prompt_contains_skill_and_payload() -> None:
    agent = _generator()
    prompt = agent.build_prompt("Quelle est la question ?", [{"source_id": "s1", "text": "ctx"}])
    assert load_skill("generator") in prompt
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["query"] == "Quelle est la question ?"
    assert payload["assembled_context"] == [{"source_id": "s1", "text": "ctx"}]
    assert payload["conversation_history"] == []


def test_generator_build_prompt_with_history() -> None:
    agent = _generator()
    history = [{"role": "user", "content": "salut"}]
    prompt = agent.build_prompt(
        "q", [{"source_id": "s1", "text": "t"}], conversation_history=history
    )
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["conversation_history"] == history


# ── build_prompt — JudgeAgent ───────────────────────────────────────

def test_judge_build_prompt_contains_skill_and_payload() -> None:
    agent = _judge()
    prompt = agent.build_prompt(
        "q", "réponse du générateur", [{"source_id": "s1", "text": "ctx"}]
    )
    assert load_skill("judge") in prompt
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["response"] == "réponse du générateur"
    assert payload["context_chunks"] == [{"source_id": "s1", "text": "ctx"}]
    assert payload["response_metadata"] == {}


def test_judge_build_prompt_with_metadata() -> None:
    agent = _judge()
    prompt = agent.build_prompt(
        "q", "r", [], response_metadata={"latency_ms": 42}
    )
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["response_metadata"] == {"latency_ms": 42}


# ── build_prompt — AdvocateAgent ────────────────────────────────────

def test_advocate_build_prompt_contains_skill_and_payload() -> None:
    agent = _advocate()
    judge_critique = {"score": 0.7, "critique": "ok", "flags": []}
    prompt = agent.build_prompt("q", "r", [{"source_id": "s1", "text": "t"}], judge_critique)
    assert load_skill("advocate") in prompt
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["judge_critique"] == judge_critique
    assert payload["response"] == "r"


# ── build_prompt — EvaluatorAgent ───────────────────────────────────

def test_evaluator_build_prompt_contains_skill_and_payload() -> None:
    agent = _evaluator()
    judge = {"score": 0.9, "flags": []}
    advocate = {"score": 0.8, "hallucination_risk": "low"}
    prompt = agent.build_prompt("q", "r", judge, advocate)
    assert load_skill("evaluator") in prompt
    payload = json.loads(prompt.split("---\n\n", 1)[1])
    assert payload["judge"] == judge
    assert payload["advocate"] == advocate


def test_evaluator_prompt_mentions_publish_rules() -> None:
    agent = _evaluator()
    prompt = agent.build_prompt("q", "r", {}, {})
    assert "publish" in prompt
    assert "verified_tier" in prompt


# ── skill_reference — WikiAgent ─────────────────────────────────────

def test_wiki_agent_skill_reference_returns_rules() -> None:
    agent = WikiAgent()
    ref = agent.skill_reference()
    assert ref == load_skill("wiki_agent")
    assert "frontmatter" in ref
    assert "lint" in ref


def test_wiki_skill_mentions_okf_frontmatter() -> None:
    skill = load_skill("wiki_agent")
    assert "verified" in skill
    assert "type" in skill
