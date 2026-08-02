"""Generator Agent — inférence sur Machine 3 BC-250 (Vulkan ONLY).

Modèle : hf.co/Qwen/Qwen3-14B-GGUF:Q4_K_M (~9GB) ou hf.co/Qwen/Qwen3-30B-A3B-GGUF:Q2_K (~11.3GB)
Contrainte : 16 GB RAM unifiée, CPU au repos pendant inference (règle d'or BC-250)

Contrat de sortie : generator_output_v1 (voir docs/prompts-agents.md §4).
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from src.agents.parsing import parse_model
from src.agents.skills.loader import load_skill
from src.services.ollama import OllamaClientPool

_SKILL_ROLE = "generator"


class GeneratorOutput(BaseModel):
    """Réponse générée avec citations (generator_output_v1)."""

    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning_trace: str | None = None


class GeneratorAgent:
    """Génère la réponse brute sur BC-250, écrit dans relay.json pour Judge/Avocat."""

    def __init__(self, pool: OllamaClientPool) -> None:
        self._pool = pool

    def build_prompt(
        self,
        query: str,
        context: list[dict],
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Assemble le SKILL.md Generator + les données du relay en prompt système."""
        skill = load_skill(_SKILL_ROLE)
        payload: dict[str, Any] = {
            "query": query,
            "assembled_context": context,
            "conversation_history": conversation_history or [],
        }
        return f"{skill}\n\n---\n\n{json.dumps(payload, ensure_ascii=False)}"

    async def generate(
        self, query: str, context: list[dict], conversation_history: list[dict] | None = None
    ) -> GeneratorOutput:
        prompt = self.build_prompt(query, context, conversation_history)
        try:
            data = await self._pool.generate(prompt, format="json")
        except Exception:
            return GeneratorOutput(
                answer="L'information n'est pas disponible dans les sources fournies.",
                citations=[],
                confidence=0.0,
            )
        output = parse_model(GeneratorOutput, data.get("response", ""))
        if output is not None:
            return output
        return GeneratorOutput(
            answer="L'information n'est pas disponible dans les sources fournies.",
            citations=[],
            confidence=0.0,
        )
