"""Generator Agent — inférence sur Machine 3 BC-250 (Vulkan ONLY).

Modèle : hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M (~9GB) ou hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K (~11.3GB)
Contrainte : 16 GB RAM unifiée, CPU au repos pendant inference (règle d'or BC-250)

Contrat de sortie : generator_output_v1 (voir docs/prompts-agents.md §4).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GeneratorOutput(BaseModel):
    """Réponse générée avec citations (generator_output_v1)."""

    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_trace: str | None = None


class GeneratorAgent:
    """Génère la réponse brute sur BC-250, écrit dans relay.json pour Judge/Avocat."""

    async def generate(self, query: str, context: list[dict]) -> GeneratorOutput:
        raise NotImplementedError
