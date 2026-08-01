"""Rewriter Agent — réécriture contextuelle de la requête utilisateur.

Modèle : petit modèle rapide (granite-4.0-h-tiny ou équivalent)
Rôle : résoudre coréférences ("il", "ça"), disambiguiser, produire une
requête autonome pour la recherche (voir docs/prompts-agents.md §6).

Contrat de sortie : rewriter_output_v1.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RewriterOutput(BaseModel):
    """Requête réécrite (rewriter_output_v1)."""

    rewritten_query: str = Field(min_length=1)
    expanded_terms: list[str] = Field(default_factory=list)
    resolved_references: dict[str, str] = Field(default_factory=dict)


class RewriterAgent:
    """Réécrit la requête en résolvant coréférences et ambiguïtés."""

    async def rewrite(
        self, original_query: str, conversation_history: list[dict] | None = None
    ) -> RewriterOutput:
        raise NotImplementedError
