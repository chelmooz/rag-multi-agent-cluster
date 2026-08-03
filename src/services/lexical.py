"""Service de recherche lexicale — full-text BM25 natif Qdrant.

Fournit un utilitaire pour construire des requêtes full-text compatibles
avec l'index BM25 natif de Qdrant (utilisé en complément du dense pour hybrid search).
"""
from __future__ import annotations


class LexicalSearchError(Exception):
    """Erreur du service de recherche lexicale."""


class LexicalSearch:
    """Constructeur de requêtes full-text pour BM25 natif Qdrant.

    Remplace l'ancien encodeur de vecteurs sparse (hash TF normalisé L2)
    par l'API full-text de Qdrant qui calcule le vrai BM25 avec IDF
    au moment de la requête.
    """

    def __init__(
        self,
        max_query_length: int = 512,
    ) -> None:
        self._max_query_length = max_query_length

    @classmethod
    def from_settings(cls) -> LexicalSearch:
        """Factory depuis la config centrale."""
        from src.core.settings import get_settings
        _ = get_settings()
        return cls()

    # ── Construction de requête full-text ──────────────────────────

    def build_query(self, text: str) -> str | None:
        """Nettoie et valide une requête full-text pour BM25 natif.

        Args:
            text: Texte de la requête (sera tronqué si trop long)

        Returns:
            Texte nettoyé prêt pour Prefetch, ou None si texte vide.
        """
        if not text or not text.strip():
            return None

        cleaned = text.strip()[:self._max_query_length]
        if not cleaned:
            return None

        return cleaned

    @property
    def max_query_length(self) -> int:
        return self._max_query_length
