"""Planner Agent — analyse d'intention + stratégie de recherche hybride.

Modèle : petit modèle rapide (granite-4.0-h-tiny ou équivalent, M3/M1)
Rôle : Phrase 1 du pipeline — décompose la requête en sous-requêtes et
choisit la pondération vectorielle/BM25 (voir docs/prompts-agents.md §5).

Contrat de sortie : planner_output_v1.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.agents.parsing import parse_model
from src.agents.skills.loader import load_skill
from src.services.ollama import OllamaClientPool

_SKILL_ROLE = "planner"

_Intent = Literal["factual", "comparative", "procedural", "analytical", "creative"]


class SearchStrategy(BaseModel):
    """Pondération des stratégies de recherche."""

    vector_weight: float = Field(ge=0.0, le=1.0, default=0.7)
    bm25_weight: float = Field(ge=0.0, le=1.0, default=0.3)
    use_sql: bool = False
    use_vision: bool = False

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> SearchStrategy:
        if abs(self.vector_weight + self.bm25_weight - 1.0) > 1e-6:
            raise ValueError("vector+bm25 doivent sommer a 1.0")
        return self


class PlannerOutput(BaseModel):
    """Plan de recherche (planner_output_v1)."""

    intent: _Intent
    sub_queries: list[str] = Field(default_factory=list, min_length=1, max_length=3)
    search_strategy: SearchStrategy = Field(default_factory=SearchStrategy)
    rerank_top_k: int = Field(ge=1, le=20, default=8)


def default_plan(query: str) -> PlannerOutput:
    """Plan de repli déterministe quand le LLM est indisponible ou illisible."""
    return PlannerOutput(
        intent="factual",
        sub_queries=[query],
        search_strategy=SearchStrategy(),
        rerank_top_k=8,
    )


class PlannerAgent:
    """Analyse l'intention et planifie la stratégie de recherche."""

    def __init__(self, pool: OllamaClientPool) -> None:
        self._pool = pool

    def build_prompt(
        self, query: str, conversation_context: str | None = None
    ) -> str:
        """Assemble le SKILL.md Planner + la requête en prompt système."""
        skill = load_skill(_SKILL_ROLE)
        payload: dict[str, Any] = {
            "query": query,
            "conversation_context": conversation_context or "",
        }
        return f"{skill}\n\n---\n\n{json.dumps(payload, ensure_ascii=False)}"

    async def plan(
        self, query: str, conversation_context: str | None = None
    ) -> PlannerOutput:
        prompt = self.build_prompt(query, conversation_context)
        try:
            data = await self._pool.fastcheck(prompt, format="json")
        except Exception:
            return default_plan(query)
        output = parse_model(PlannerOutput, data.get("response", ""))
        return output if output is not None else default_plan(query)
