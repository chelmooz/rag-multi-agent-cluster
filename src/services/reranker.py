"""Service de reranking — bge-reranker-v2-m3 via Ollama M2 (RTX 4000)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.services.ollama import OllamaClientPool, OllamaError


class RerankerError(Exception):
    """Erreur du service de reranking."""


@dataclass(frozen=True)
class RerankResult:
    """Résultat de reranking pour un document."""
    index: int
    score: float
    text: str


class RerankerService:
    """Service de reranking utilisant bge-reranker-v2-m3 sur Machine 2 (RTX 4000).

    Prend une requête et une liste de documents, retourne les scores de pertinence
    ordonnés. Utilise l'endpoint /api/rerank d'Ollama.
    """

    def __init__(
        self,
        ollama_pool: OllamaClientPool | None = None,
        model: str | None = None,
    ) -> None:
        self._ollama_pool = ollama_pool
        self._model = model

    @classmethod
    def from_settings(cls) -> RerankerService:
        """Factory depuis la config centrale."""
        from src.core.settings import get_settings
        from src.services.ollama import OllamaClientPool

        s = get_settings()
        return cls(
            ollama_pool=OllamaClientPool(),
            model=s.reranker_model,
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Rerank les documents par pertinence par rapport à la requête.

        Args:
            query: Requête utilisateur
            documents: Liste des textes à reranker
            top_k: Nombre de résultats à retourner (None = tous)

        Returns:
            Liste de RerankResult triée par score décroissant.
        """
        if not documents:
            return []

        if self._ollama_pool is None:
            raise RerankerError("OllamaClientPool non initialisé")

        if self._model is None:
            raise RerankerError("Modèle de reranking non configuré")

        try:
            # Appel via OllamaClientPool qui route vers M2
            scores = await self._ollama_pool.rerank(query, documents)

            # Créer résultats avec index et score
            results = [
                RerankResult(index=i, score=score, text=documents[i])
                for i, score in enumerate(scores)
            ]

            # Trier par score décroissant
            results.sort(key=lambda r: r.score, reverse=True)

            if top_k is not None:
                results = results[:top_k]

        except OllamaError as e:
            raise RerankerError(f"Échec reranking: {e}") from e
        else:
            return results

    async def rerank_with_payload(
        self,
        query: str,
        documents: list[dict[str, Any]],
        text_key: str = "text",
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Rerank des documents avec payload (ex: résultats Qdrant).

        Args:
            query: Requête utilisateur
            documents: Liste de dicts contenant au moins `text_key`
            text_key: Clé du texte dans chaque document
            top_k: Nombre de résultats à retourner

        Returns:
            Liste des documents originaux avec `rerank_score` ajouté, triés.
        """
        if not documents:
            return []

        texts = [doc.get(text_key, "") for doc in documents]
        results = await self.rerank(query, texts, top_k=None)  # Rerank all

        # Ajouter scores aux documents originaux
        scored_docs = []
        for result in results:
            doc = dict(documents[result.index])
            doc["rerank_score"] = result.score
            scored_docs.append(doc)

        # Trier par rerank_score décroissant
        scored_docs.sort(key=lambda d: d.get("rerank_score", 0.0), reverse=True)

        if top_k is not None:
            scored_docs = scored_docs[:top_k]

        return scored_docs

    async def close(self) -> None:
        if self._ollama_pool:
            await self._ollama_pool.close()

    async def __aenter__(self) -> RerankerService:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
