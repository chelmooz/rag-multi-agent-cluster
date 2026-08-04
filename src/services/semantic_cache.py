"""Cache sémantique Redis — cosinus numpy, OFF par défaut (R5).

Le cache compare l'embedding de la requête aux embeddings des réponses
précédentes (similarité cosinus réelle, pas un hash exact) : une question
reformulée mais sémantiquement identique retombe sur la réponse mise en cache.

Contrat :
- ``enabled=False`` (défaut) → ``get``/``put`` sont des no-ops, aucun I/O.
- Clés Redis ``rag:cache:<sha256(embedding)>`` avec TTL.
- Entrées JSON : ``{query, answer, confidence, sources, vector, created_at}``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

import numpy as np
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_PREFIX = "rag:cache:"

Embedder = Callable[[str], Awaitable[list[float] | None]]


def _embedding_key(vector: list[float]) -> str:
    """Clé Redis déterministe d'un embedding (doublons écrasés)."""
    digest = hashlib.sha256(json.dumps(vector).encode()).hexdigest()[:16]
    return f"{_PREFIX}{digest}"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosinus numpy de deux vecteurs (0.0 si l'un est vide)."""
    va, vb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if va.size == 0 or vb.size == 0:
        return 0.0
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(va.dot(vb) / (na * nb))


class SemanticCache:
    """Cache de réponses par similarité cosinus de l'embedding de la requête."""

    def __init__(
        self,
        embed: Embedder,
        redis: Redis | None = None,
        enabled: bool = False,
        threshold: float = 0.95,
        ttl_seconds: int = 3600,
    ) -> None:
        self._embed = embed
        self._redis = redis
        self.enabled = enabled
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds

    async def get(self, query: str) -> dict[str, Any] | None:
        """Retourne l'entrée cache la plus proche si cosinus ≥ seuil, sinon None."""
        if not self.enabled or self._redis is None:
            return None
        vector = await self._embed(query)
        if not vector:
            return None

        best: tuple[float, dict[str, Any]] | None = None
        async for key in self._redis.scan_iter(match=f"{_PREFIX}*"):
            raw = await self._redis.get(key)
            if raw is None:
                continue
            try:
                entry = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                logger.warning("Entrée cache illisible ignorée : %s", key)
                continue
            score = cosine_similarity(vector, entry.get("vector", []))
            if best is None or score > best[0]:
                best = (score, entry)

        if best is None or best[0] < self.threshold:
            return None
        payload = dict(best[1])
        payload["similarity"] = round(best[0], 4)
        return payload

    async def put(
        self,
        query: str,
        answer: str,
        confidence: float | None = None,
        sources: list[str] | None = None,
    ) -> None:
        """Stocke la réponse associée à l'embedding de la requête (TTL)."""
        if not self.enabled or self._redis is None:
            return
        vector = await self._embed(query)
        if not vector:
            return
        entry = {
            "query": query,
            "answer": answer,
            "confidence": confidence,
            "sources": sources or [],
            "vector": vector,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await cast(
            Awaitable[Any],
            self._redis.set(
                _embedding_key(vector),
                json.dumps(entry, ensure_ascii=False),
                ex=self.ttl_seconds,
            ),
        )

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
