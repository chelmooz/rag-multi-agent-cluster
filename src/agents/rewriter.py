"""Rewriter Agent — réécriture contextuelle de la requête utilisateur.

Modèle : petit modèle rapide (granite-4.0-h-tiny ou équivalent)
Rôle : résoudre coréférences ("il", "ça"), disambiguiser, produire une
requête autonome pour la recherche (voir docs/prompts-agents.md §6).

Contrat de sortie : rewriter_output_v1.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from src.agents.parsing import parse_model
from src.agents.skills.loader import load_skill
from src.services.ollama import OllamaClientPool

_SKILL_ROLE = "rewriter"


class RewriterOutput(BaseModel):
    """Requête réécrite (rewriter_output_v1)."""

    rewritten_query: str = Field(min_length=1)
    expanded_terms: list[str] = Field(default_factory=list)
    resolved_references: dict[str, str] = Field(default_factory=dict)


class RewriterAgent:
    """Réécrit la requête en résolvant coréférences et ambiguïtés."""

    def __init__(self, pool: OllamaClientPool) -> None:
        self._pool = pool

    def build_prompt(
        self, original_query: str, conversation_history: list[dict] | None = None
    ) -> str:
        """Assemble le SKILL.md Rewriter + la requête et l'historique en prompt."""
        skill = load_skill(_SKILL_ROLE)
        payload: dict[str, Any] = {
            "original_query": original_query,
            "conversation_history": conversation_history or [],
        }
        return f"{skill}\n\n---\n\n{json.dumps(payload, ensure_ascii=False)}"

    async def rewrite(
        self, original_query: str, conversation_history: list[dict] | None = None
    ) -> RewriterOutput:
        prompt = self.build_prompt(original_query, conversation_history)
        try:
            data = await self._pool.fastcheck(prompt, format="json")
        except Exception:
            return RewriterOutput(rewritten_query=original_query)
        output = parse_model(RewriterOutput, data.get("response", ""))
        return output if output is not None else RewriterOutput(rewritten_query=original_query)
