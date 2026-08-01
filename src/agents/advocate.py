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

from typing import Literal

from pydantic import BaseModel, Field


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

    async def challenge(
        self, query: str, response: str, context: list[dict], judge_critique: dict
    ) -> AdvocateOutput:
        raise NotImplementedError

    async def unload(self) -> None:
        raise NotImplementedError
