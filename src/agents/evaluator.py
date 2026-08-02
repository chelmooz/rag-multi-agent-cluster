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

from src.agents.parsing import parse_model
from src.agents.skills.loader import load_skill
from src.services.ollama import OllamaClientPool

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

    def __init__(self, pool: OllamaClientPool) -> None:
        self._pool = pool

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
        query = relay_data.get("query", "")
        response = relay_data.get("response", "")
        judge = relay_data.get("judge", {})
        advocate = relay_data.get("advocate", {})
        prompt = self.build_prompt(query, response, judge, advocate)
        try:
            data = await self._pool.evaluate(prompt, format="json")
        except Exception:
            return self._fallback()
        output = parse_model(EvaluatorOutput, data.get("response", ""))
        return output if output is not None else self._fallback()

    def _fallback(self) -> EvaluatorOutput:
        """Décision de repli : refuse la publication (prudence)."""
        return EvaluatorOutput(
            decision="reject",
            final_score=0.0,
            reasoning="Évaluation indisponible (modèle injoignable ou réponse illisible).",
            revision_instructions=None,
            verified_tier="unverified",
            confidence=0.0,
        )

    async def update_frontmatter(self, page_path: str, trust_tier: str) -> None:
        """Met à jour le champ verified du frontmatter OKF d'une page du vault.

        ``trust_tier`` : ``machine-confirmed`` ou ``human-reviewed`` (jamais
        automatique, cf. SKILL Evaluator). La page est relue puis réécrite
        avec ``verified`` mis à jour — le reste du frontmatter est préservé.
        """
        from src.agents.wiki_agent import WikiAgent, WikiAgentError

        if trust_tier not in ("unverified", "machine-confirmed", "human-reviewed"):
            raise ValueError(f"trust_tier invalide: {trust_tier!r}")

        wiki = WikiAgent()
        target = wiki._resolve(page_path)
        if not target.is_file():
            raise WikiAgentError(f"Page introuvable: {page_path!r}")

        text = target.read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise WikiAgentError(f"Page sans frontmatter OKF: {page_path!r}")
        end = text.find("\n---", 3)
        if end == -1:
            raise WikiAgentError(f"Frontmatter non fermé: {page_path!r}")

        import yaml

        fm = yaml.safe_load(text[3:end])
        if not isinstance(fm, dict):
            raise WikiAgentError(f"Frontmatter invalide: {page_path!r}")
        fm["verified"] = trust_tier
        body = text[end + 1 :]
        new_text = f"---\n{yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)}---{body}"
        target.write_text(new_text, encoding="utf-8")
