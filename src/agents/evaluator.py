"""Évaluateur Agent — synthèse finale sur Machine 1 CPU.

Modèle : hf.co/ibm-granite/granite-4.1-8b-instruct-GGUF:Q4_K_M.

Pipeline :
1. Lit relay.json complet (response + Judge + Avocat)
2. Synthétise les avis en décision finale
3. Calcule un score de confiance global
4. Écrit verified: human-reviewed dans le frontmatter OKF des pages validées

Contrat de sortie : evaluator_output_v1 (voir docs/prompts-agents.md §3).
Le frontmatter OKF v0.2 est écrit UNIQUEMENT ici (vault) — les sorties
agents elles-mêmes n'utilisent pas OKF (minimalisme pour parsing fiable).
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.skills.loader import load_skill

_SKILL_ROLE = "evaluator"


class EvaluatorOutput(BaseModel):
    """Décision finale de l'Évaluateur (evaluator_output_v1)."""

    decision: Literal["publish", "revise", "reject"]
    final_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1)
    revision_instructions: str | None = None
    verified_tier: Literal["machine-confirmed", "unverified"] = "unverified"
    confidence: float = Field(ge=0.0, le=1.0)


class EvaluatorAgent:
    """Synthèse finale : combine Judge + Avocat en réponse finale et décision de publication."""

    def build_prompt(
        self,
        query: str,
        response: str,
        judge: dict,
        advocate: dict,
    ) -> str:
        """Assemble le SKILL.md Evaluator + les avis Judge/Advocate en prompt système."""
        skill = load_skill(_SKILL_ROLE)
        payload: dict[str, Any] = {
            "query": query,
            "response": response,
            "judge": judge,
            "advocate": advocate,
        }
        return f"{skill}\n\n---\n\n{json.dumps(payload, ensure_ascii=False)}"

    async def synthesize(self, relay_data: dict) -> EvaluatorOutput:
        raise NotImplementedError

    async def update_frontmatter(self, page_path: str, trust_tier: str) -> None:
        """Met à jour le champ verified: human-reviewed dans le frontmatter OKF."""
        raise NotImplementedError
