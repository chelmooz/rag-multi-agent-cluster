"""Évaluation du retrieval — precision@k, recall@k, MRR, nDCG (R4).

Métriques pures (aucun I/O) : binaires par document pertinent, idéales pour
un dataset de ground truths ``(relevant_ids, retrieved_ids)`` hors ligne.

Voir ``scripts/run_retrieval_eval.py`` pour l'exécution sur dataset JSON.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

_K_DEFAULTS = (5, 10, 20)


def precision_at_k(
    relevant: set[str],
    retrieved: Sequence[str],
    k: int | None = None,
) -> float:
    """Précision@k : part de résultats pertinents dans les k premiers retours."""
    top = retrieved[:k] if k is not None else retrieved
    if not top:
        return 0.0
    return sum(1 for r in top if r in relevant) / len(top)


def recall_at_k(
    relevant: set[str],
    retrieved: Sequence[str],
    k: int | None = None,
) -> float:
    """Rappel@k : part des pertinents effectivement retrouvés dans les k premiers."""
    if not relevant:
        return 0.0
    top = retrieved[:k] if k is not None else retrieved
    return sum(1 for r in top if r in relevant) / len(relevant)


def reciprocal_rank(relevant: set[str], retrieved: Sequence[str]) -> float:
    """RR : 1 / position du premier résultat pertinent (0 si aucun)."""
    for pos, doc in enumerate(retrieved, start=1):
        if doc in relevant:
            return 1.0 / pos
    return 0.0


def ndcg_at_k(
    relevant: set[str],
    retrieved: Sequence[str],
    k: int | None = None,
    *,
    log_base: float = 2.0,
) -> float:
    """nDCG@k (relevance binaire) : DCG normalisé par IDCG, dans [0, 1]."""
    top = retrieved[:k] if k is not None else retrieved
    dcg = sum(
        1.0 / math.log(pos + 1, log_base)
        for pos, doc in enumerate(top, start=1)
        if doc in relevant
    )
    ideal = sum(
        1.0 / math.log(pos + 1, log_base)
        for pos in range(1, min(len(relevant), len(top)) + 1)
    )
    return dcg / ideal if ideal else 0.0


def evaluate_retrieval(
    cases: Sequence[tuple[set[str], Sequence[str]]],
    ks: Sequence[int] = _K_DEFAULTS,
) -> dict[str, float]:
    """Moyennes des métriques sur un dataset de requêtes.

    Args:
        cases: séquence de ``(ensembles pertinents, liste des IDs retrouvés)``.
        ks: valeurs de ``k`` pour précision/rappel/nDCG.

    Returns:
        Dictionnaire ``{metrique: moyenne}`` (+ ``queries`` = taille du dataset).
    """
    if not cases:
        return {"queries": 0.0}
    count = len(cases)
    out: dict[str, float] = {"queries": float(count)}
    for k in ks:
        out[f"precision@{k}"] = sum(precision_at_k(r, ret, k) for r, ret in cases) / count
        out[f"recall@{k}"] = sum(recall_at_k(r, ret, k) for r, ret in cases) / count
        out[f"ndcg@{k}"] = sum(ndcg_at_k(r, ret, k) for r, ret in cases) / count
    out["mrr"] = sum(reciprocal_rank(r, ret) for r, ret in cases) / count
    return out


def from_search_results(case: dict[str, Any]) -> tuple[set[str], list[str]]:
    """Normalise un cas brut ``{relevant: [...], retrieved: [...]}``."""
    relevant = {str(item) for item in case.get("relevant", [])}
    retrieved = [str(item) for item in case.get("retrieved", [])]
    return relevant, retrieved
