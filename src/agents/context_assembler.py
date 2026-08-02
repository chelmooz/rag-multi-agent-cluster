"""ContextAssembler — fusionne les chunks rerankés + savoir interne + fenêtre courte.

Rôle : construire le contexte final transmis au Generator. Discipline
anti lost-in-the-middle (règle du projet : fenêtre de 12 000 caractères
maximum) : trier les chunks par score, tronquer au budget, préserver
l'ordre de pertinence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_CONTEXT_CHARS = 12_000


@dataclass(frozen=True)
class AssembledChunk:
    """Chunk normalisé prêt pour le Generator."""

    source_id: str
    text: str
    score: float = 0.0


@dataclass
class AssembledContext:
    """Contexte final assemblé."""

    query: str
    chunks: list[AssembledChunk] = field(default_factory=list)
    internal_knowledge: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def total_chars(self) -> int:
        return sum(len(c.text) for c in self.chunks) + sum(
            len(k) for k in self.internal_knowledge
        )


class ContextAssembler:
    """Assemble le contexte final à partir des chunks rerankés.

    Entrée (contrat ``hybrid_search`` + ``RerankerService.rerank``) : une
    liste de dicts avec au moins ``{"id", "score", "payload": {"text": ...}}``.
    """

    def assemble(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        internal_knowledge: list[str] | None = None,
        max_chars: int = MAX_CONTEXT_CHARS,
    ) -> AssembledContext:
        normalized: list[AssembledChunk] = []
        for c in chunks:
            payload = c.get("payload") or {}
            text = payload.get("text") or c.get("text") or ""
            source_id = str(
                c.get("source_id")
                or payload.get("source_id")
                or payload.get("source")
                or c.get("id", "s0")
            )
            score = float(c.get("score", 0.0))
            normalized.append(AssembledChunk(source_id=source_id, text=text, score=score))

        normalized.sort(key=lambda c: c.score, reverse=True)

        kept: list[AssembledChunk] = []
        budget = max_chars
        for chunk in normalized:
            if len(chunk.text) > budget:
                continue
            kept.append(chunk)
            budget -= len(chunk.text)

        knowledge = list(internal_knowledge or [])
        kept_knowledge: list[str] = []
        for item in knowledge:
            if len(item) > budget:
                continue
            kept_knowledge.append(item)
            budget -= len(item)
        knowledge = kept_knowledge

        return AssembledContext(
            query=query,
            chunks=kept,
            internal_knowledge=knowledge,
            truncated=sum(len(c.text) for c in kept) < sum(len(c.text) for c in normalized),
        )
