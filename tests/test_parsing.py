"""Tests du module partagé de parsing JSON des agents."""

from __future__ import annotations

from src.agents.parsing import extract_json, parse_model
from src.agents.planner import PlannerOutput

# ── extract_json ───────────────────────────────────────────────────

def test_extract_json_plain() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_surrounding_text() -> None:
    assert extract_json('Voici le résultat: {"a": 1} et c\'est tout.') == {"a": 1}


def test_extract_json_fenced_with_lang() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_fenced_plain() -> None:
    assert extract_json('```\n{"a": 2}\n```') == {"a": 2}


def test_extract_json_fenced_invalid_then_fallback() -> None:
    assert extract_json('```json\npas du json\n``` puis {"a": 3}') == {"a": 3}


def test_extract_json_empty_text() -> None:
    assert extract_json("") is None
    assert extract_json("   ") is None


def test_extract_json_no_braces() -> None:
    assert extract_json("aucune structure json ici") is None


def test_extract_json_invalid_payload() -> None:
    assert extract_json('{"a": ' ) is None


def test_extract_json_array_not_dict() -> None:
    assert extract_json("[1, 2, 3]") is None


def test_extract_json_fenced_array_ignored() -> None:
    assert extract_json("```json\n[1, 2]\n```") is None


# ── parse_model ────────────────────────────────────────────────────

def test_parse_model_valid() -> None:
    raw = (
        '{"intent": "factual", "sub_queries": ["q1"], '
        '"search_strategy": {"vector_weight": 0.7, "bm25_weight": 0.3}, '
        '"rerank_top_k": 8}'
    )
    out = parse_model(PlannerOutput, raw)
    assert out is not None
    assert out.intent == "factual"


def test_parse_model_invalid_json() -> None:
    assert parse_model(PlannerOutput, "nope") is None


def test_parse_model_validation_error() -> None:
    assert parse_model(PlannerOutput, '{"intent": "mystere"}') is None
