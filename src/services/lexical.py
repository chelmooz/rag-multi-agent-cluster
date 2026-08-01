"""Service de recherche lexicale — sparse vectors BM25 via Qdrant natif.

Fournit des utilitaires pour encoder du texte en vecteurs sparse compatibles
avec l'index BM25 de Qdrant (utilisé en complément du dense pour hybrid search).
"""
from __future__ import annotations

import math

import tiktoken
from qdrant_client.http import models as qmodels


class LexicalSearchError(Exception):
    """Erreur du service de recherche lexicale."""


class LexicalSearch:
    """Encodeur de texte vers vecteurs sparse BM25.

    Utilise tiktoken pour tokenizer et construit des vecteurs sparse
    compatibles avec l'index BM25 de Qdrant (nom de vecteur "bm25").
    """

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        sparse_dim: int = 100000,
    ) -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)
        self._sparse_dim = sparse_dim

    @classmethod
    def from_settings(cls) -> LexicalSearch:
        """Factory depuis la config centrale."""
        from src.core.settings import get_settings
        _ = get_settings()
        return cls()

    # ── Encodage ────────────────────────────────────────────────

    def encode(self, text: str) -> qmodels.SparseVector:
        """Encode un texte en SparseVector Qdrant (TF normalisé L2)."""
        tokens = self._encoding.encode(text.lower())

        # Compter fréquences avec hash dans l'espace sparse
        freq: dict[int, float] = {}
        for token in tokens:
            idx = token % self._sparse_dim
            freq[idx] = freq.get(idx, 0.0) + 1.0

        # Normalisation L2 pour BM25
        norm = math.sqrt(sum(v * v for v in freq.values()))
        if norm > 0:
            freq = {k: v / norm for k, v in freq.items()}

        return qmodels.SparseVector(
            indices=list(freq.keys()),
            values=list(freq.values()),
        )

    def encode_batch(self, texts: list[str]) -> list[qmodels.SparseVector]:
        """Encode une liste de textes en SparseVectors."""
        return [self.encode(t) for t in texts]

    def encode_to_dict(self, text: str) -> dict[int, float]:
        """Encode en dict {index: value} pour utilisation directe."""
        tokens = self._encoding.encode(text.lower())

        freq: dict[int, float] = {}
        for token in tokens:
            idx = token % self._sparse_dim
            freq[idx] = freq.get(idx, 0.0) + 1.0

        norm = math.sqrt(sum(v * v for v in freq.values()))
        if norm > 0:
            freq = {k: v / norm for k, v in freq.items()}
        return freq

    def encode_batch_to_dict(self, texts: list[str]) -> list[dict[int, float]]:
        """Encode une liste en liste de dicts."""
        return [self.encode_to_dict(t) for t in texts]

    # ── Utilitaires ─────────────────────────────────────────────

    @staticmethod
    def merge_sparse_vectors(
        vectors: list[qmodels.SparseVector],
        weights: list[float] | None = None,
    ) -> qmodels.SparseVector:
        """Fusionne plusieurs vecteurs sparse (somme pondérée)."""
        if not vectors:
            return qmodels.SparseVector(indices=[], values=[])

        if weights is None:
            weights = [1.0] * len(vectors)

        merged: dict[int, float] = {}
        for vec, weight in zip(vectors, weights, strict=True):
            for idx, val in zip(vec.indices, vec.values, strict=True):
                merged[idx] = merged.get(idx, 0.0) + val * weight

        # Renormaliser
        norm = math.sqrt(sum(v * v for v in merged.values()))
        if norm > 0:
            merged = {k: v / norm for k, v in merged.items()}

        return qmodels.SparseVector(
            indices=list(merged.keys()),
            values=list(merged.values()),
        )

    @property
    def sparse_dim(self) -> int:
        return self._sparse_dim
