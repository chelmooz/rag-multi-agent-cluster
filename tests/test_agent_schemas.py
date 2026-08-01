"""Tests des contrats de sortie agents (schémas *_output_v1).

Valide le parsing Pydantic avant implémentation des LLM : un LLM qui
respecte le schéma (JSON) est parsé correctement ; un JSON invalide
est rejeté avec une erreur Pydantic claire.
"""
import pytest
from pydantic import ValidationError

from src.agents.advocate import AdvocateOutput
from src.agents.evaluator import EvaluatorOutput
from src.agents.generator import GeneratorOutput
from src.agents.judge import JudgeOutput
from src.agents.planner import PlannerOutput
from src.agents.rewriter import RewriterOutput


class TestJudgeOutput:
    def test_valid(self) -> None:
        out = JudgeOutput(
            score=0.85,
            critique="Précise mais omet la contrainte VRAM.",
            checks_passed=["factualite", "coherence"],
            flags=["omission_source"],
            confidence=0.9,
        )
        assert out.score == 0.85
        assert "omission_source" in out.flags

    def test_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JudgeOutput(score=1.5, critique="x", confidence=0.5)

    def test_invalid_flag_rejected(self) -> None:
        with pytest.raises(ValidationError):
            JudgeOutput(
                score=0.5, critique="x", flags=["invented_flag"], confidence=0.5
            )


class TestAdvocateOutput:
    def test_valid(self) -> None:
        out = AdvocateOutput(
            score=0.3,
            faille="Risque OOM non qualifié.",
            claims_contested=["Qwen3-30B-A3B partout"],
            hallucination_risk="low",
            missing_context=["marge VRAM"],
            confidence=0.93,
        )
        assert out.hallucination_risk == "low"

    def test_invalid_risk_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AdvocateOutput(
                score=0.5, faille="x", hallucination_risk="extreme", confidence=0.5
            )


class TestEvaluatorOutput:
    def test_valid_publish(self) -> None:
        out = EvaluatorOutput(
            decision="publish",
            final_score=0.91,
            reasoning="Convergence Judge/Avocat.",
            revision_instructions=None,
            verified_tier="machine-confirmed",
            confidence=0.95,
        )
        assert out.decision == "publish"

    def test_valid_revise_with_instructions(self) -> None:
        out = EvaluatorOutput(
            decision="revise",
            final_score=0.51,
            reasoning="Faille OOM réparable.",
            revision_instructions="Ajouter la limite ~12 Go.",
            verified_tier="unverified",
            confidence=0.9,
        )
        assert out.revision_instructions is not None

    def test_human_reviewed_not_allowed_automatic(self) -> None:
        with pytest.raises(ValidationError):
            EvaluatorOutput(
                decision="publish",
                final_score=0.9,
                reasoning="x",
                verified_tier="human-reviewed",  # jamais en automatique
                confidence=0.9,
            )


class TestGeneratorOutput:
    def test_valid(self) -> None:
        out = GeneratorOutput(
            answer="Qwen3-14B est recommandé [s1].",
            citations=["s1"],
            confidence=0.93,
        )
        assert out.citations == ["s1"]

    def test_empty_answer_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GeneratorOutput(answer="", citations=[], confidence=0.5)


class TestPlannerOutput:
    def test_valid(self) -> None:
        out = PlannerOutput(
            intent="comparative",
            sub_queries=["a", "b"],
            rerank_top_k=8,
        )
        assert out.search_strategy.vector_weight == 0.7

    def test_weights_not_summing_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PlannerOutput(
                intent="factual",
                sub_queries=["a"],
                search_strategy={"vector_weight": 0.9, "bm25_weight": 0.9},
            )


class TestRewriterOutput:
    def test_valid(self) -> None:
        out = RewriterOutput(
            rewritten_query="Le BC-250 supporte-t-il Vulkan ?",
            expanded_terms=["Vulkan", "RADV"],
            resolved_references={"il": "le BC-250"},
        )
        assert out.resolved_references["il"] == "le BC-250"
