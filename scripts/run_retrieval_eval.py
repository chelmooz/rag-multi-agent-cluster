"""Exécute l'évaluation du retrieval sur un dataset JSON (R4).

Dataset attendu : liste de cas
``{"query": str, "relevant": [ids], "retrieved": [ids]}`` — les IDs sont
comparés en chaîne de caractères (source_id ou point id).

Exemple :
    python scripts/run_retrieval_eval.py --dataset scripts/data/retrieval_eval.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.services.retrieval_eval import (
    evaluate_retrieval,
    from_search_results,
)

_DEFAULT_DATASET = [
    {
        "query": "comment configurer MTU 9000 sur VLAN 10",
        "relevant": ["doc-bc250-net", "doc-reseau-vlan"],
        "retrieved": ["doc-bc250-net", "doc-mtls", "doc-reseau-vlan", "doc-backup"],
    },
    {
        "query": "ralentir le BC-250 en embedding ?",
        "relevant": ["decision-embedding"],
        "retrieved": ["decision-embedding", "doc-backup"],
    },
    {
        "query": "backup Qdrant quotidien",
        "relevant": ["doc-backup", "backlog-0.21"],
        "retrieved": ["doc-reseau-vlan", "backlog-0.21"],
    },
]


def load_dataset(path: str | None) -> list[dict]:
    if path is None:
        return _DEFAULT_DATASET
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Évaluation du retrieval RAG")
    parser.add_argument(
        "--dataset",
        default=None,
        help="Chemin vers un fichier JSON de cas (défaut : dataset embarqué)",
    )
    parser.add_argument(
        "--k",
        type=int,
        nargs="*",
        default=[5, 10, 20],
        help="Valeurs de k pour precision@k / recall@k / ndcg@k (defaut: 5 10 20)",
    )
    args = parser.parse_args()

    cases = [from_search_results(c) for c in load_dataset(args.dataset)]
    metrics = evaluate_retrieval(cases, ks=args.k)

    print(f"Évaluation retrieval — {int(metrics['queries'])} requêtes")
    for key, value in metrics.items():
        if key == "queries":
            continue
        print(f"  {key:<12} {value:.4f}")


if __name__ == "__main__":
    main()
