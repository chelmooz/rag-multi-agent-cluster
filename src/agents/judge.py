"""Judge Agent — évalue la qualité de la réponse sur Machine 2 RTX 4000.

Modèle : hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M (~5GB)
Pipeline : séquentiel après Generator, avant Avocat.
           1. Charge hf.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF:Q4_K_M
           2. Lit relay.json (réponse du Generator)
           3. Évalue qualité, précision, hallucinations
           4. Écrit judge.score + judge.critique → relay.json
           5. Unload modèle (libère VRAM pour Avocat)

Contrat de sortie : judge_output_v1 (voir docs/prompts-agents.md §1)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_CheckName = Literal["factualite", "coherence", "couverture", "style"]
_FlagName = Literal[
    "hallucination_suspect",
    "omission_source",
    "contradiction_interne",
]


class JudgeOutput(BaseModel):
    """Sortie structurée du Juge (judge_output_v1)."""

    score: float = Field(ge=0.0, le=1.0)
    critique: str = Field(min_length=1)
    checks_passed: list[_CheckName] = Field(default_factory=list)
    flags: list[_FlagName] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class JudgeAgent:
    """Évalue la qualité de la réponse (score 0.0-1.0 + critique textuelle)."""

    async def evaluate(self, query: str, response: str, context: list[dict]) -> JudgeOutput:
        raise NotImplementedError

    async def unload(self) -> None:
        """Décharge le modèle de la VRAM RTX 4000 (essentiel pour le pipeline séquentiel)."""
        raise NotImplementedError
