"""Planner Agent — analyse d'intention + stratégie de recherche hybride.

Modèle : petit modèle rapide (granite-4.0-h-tiny ou équivalent, M3/M1)
Rôle : Phrase 1 du pipeline — décompose la requête en sous-requêtes et
choisit la pondération vectorielle/BM25 (voir docs/prompts-agents.md §5).

Contrat de sortie : planner_output_v1.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class PlannerAgent:
    """Analyse l'intention et planifie la stratégie de recherche."""

    async def plan(self, query: str, conversation_context: str | None = None) -> PlannerOutput:
        raise NotImplementedError
