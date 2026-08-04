"""Contrôle d'accès retrieval — AccessPolicy protocol + NoAuthPolicy + ScopePolicy (R6).

Le pipeline reçoit un ``Filter`` Qdrant par requête (construit depuis les champs
``user``/``access_scope`` du payload) : seuls les chunks dont le payload match
sont renvoyés par ``hybrid_search`` (filtre côté VectorDB, pas de filtre post-hoc).

Défaut : ``NoAuthPolicy`` (aucun filtre) — LAN de confiance.
"""
from __future__ import annotations

from typing import Protocol

from qdrant_client import models


class AccessPolicy(Protocol):
    """Construit le filtre Qdrant d'une requête (ou None si aucun filtre)."""

    def build_filter(self, user: str | None, scope: str | None) -> models.Filter | None: ...


class NoAuthPolicy:
    """Aucune restriction : pas de filtre payload (défaut LAN de confiance)."""

    def build_filter(self, user: str | None, scope: str | None) -> models.Filter | None:
        del user, scope
        return None


class ScopePolicy:
    """Filtre payload stricte : portée d'accès + propriétaire quand fournis."""

    def build_filter(self, user: str | None, scope: str | None) -> models.Filter | None:
        conditions: list[models.FieldCondition] = []
        if scope:
            conditions.append(
                models.FieldCondition(
                    key="access_scope",
                    match=models.MatchValue(value=scope),
                )
            )
        if user:
            conditions.append(
                models.FieldCondition(
                    key="owner",
                    match=models.MatchValue(value=user),
                )
            )
        if not conditions:
            return None
        return models.Filter(must=conditions)


def build_policy(scope: str | None) -> AccessPolicy:
    """Sélectionne la politique par requête : ScopePolicy si une portée est donnée."""
    return ScopePolicy() if scope else NoAuthPolicy()
