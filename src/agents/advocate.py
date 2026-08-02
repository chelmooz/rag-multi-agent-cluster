"""Avocat du diable Agent — cherche activement les failles/contradictions/hallucinations.

Modèle : hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M (~5GB)
Pipeline : séquentiel après Judge.
           1. Charge hf.co/bartowski/Ministral-8B-Instruct-2410-GGUF:Q4_K_M
           2. Lit relay.json complet (query + response + critique Judge)
           3. Cherche activement les failles, biais, hallucinations
           4. Écrit advocate.score + advocate.faille → relay.json
           5. Unload modèle (libère VRAM)

L'information qualité du Juge passe via relay.json (NFS M1↔M2) : l'Avocat
reçoit judge_critique en entrée et va PLUS LOIN que la critique (pas de
partage KV cache — modèles différents, cf. docs/prompts-agents.md §2).

Contrat de sortie : advocate_output_v1 (voir docs/prompts-agents.md §2).
Score INVERSÉ : 0.0 = faille critique bloquante, 1.0 = aucune faille.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.parsing import parse_model
from src.agents.skills.loader import load_skill
from src.services.ollama import OllamaClientPool

_SKILL_ROLE = "advocate"


class AdvocateOutput(BaseModel):
    """Sortie structurée de l'Avocat du diable (advocate_output_v1)."""

    score: float = Field(ge=0.0, le=1.0)
    faille: str
    claims_contested: list[str] = Field(default_factory=list)
    hallucination_risk: Literal["low", "medium", "high"] = "low"
    missing_context: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class AdvocateAgent:
    """Avocat du diable : cherche failles/hallucinations dans la réponse."""

    def __init__(self, pool: OllamaClientPool) -> None:
        self._pool = pool

    def build_prompt(
        self,
        query: str,
        response: str,
        context: list[dict],
        judge_critique: dict,
    ) -> str:
        """Assemble le SKILL.md Advocate + les données du relay en prompt système."""
        skill = load_skill(_SKILL_ROLE)
        payload: dict[str, Any] = {
            "query": query,
            "response": response,
            "context_chunks": context,
            "judge_critique": judge_critique,
        }
        return f"{skill}\n\n---\n\n{json.dumps(payload, ensure_ascii=False)}"

    async def challenge(
        self, query: str, response: str, context: list[dict], judge_critique: dict
    ) -> AdvocateOutput:
        prompt = self.build_prompt(query, response, context, judge_critique)
        try:
            data = await self._pool.advocate(prompt, format="json")
        except Exception:
            return self._fallback()
        output = parse_model(AdvocateOutput, data.get("response", ""))
        return output if output is not None else self._fallback()

    def _fallback(self) -> AdvocateOutput:
        """Avis de repli : échec signalé comme faille bloquante (prudence)."""
        return AdvocateOutput(
            score=0.0,
            faille="Évaluation indisponible (modèle injoignable ou réponse illisible).",
            claims_contested=[],
            hallucination_risk="high",
            missing_context=[],
            confidence=0.0,
        )

    async def unload(self) -> None:
        """Décharge le modèle de la VRAM RTX 4000 (séquentiel avant retour)."""
        await self._pool.m2.unload_model(self._pool._settings.advocate_model)
