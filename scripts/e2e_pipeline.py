"""E2E pipeline réel sur le cluster (R7.1) — à exécuter post-déploiement.

Lance ``run_pipeline`` avec les services réels (Ollama M1/M2/M3 + Qdrant) et
affiche la réponse, les sources et le temps de bout-en-bout.

Usage :
    python scripts/e2e_pipeline.py --query "comment configurer le MTU 9000 ?"
    python scripts/e2e_pipeline.py --query "..." --evaluation --top-k 10

Code de sortie : 0 si une réponse est produite, 1 sinon (cluster indispo).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.agents.langgraph_orchestrator import (
    build_pipeline_services,
    run_pipeline,
)


async def _run(query: str, evaluation: bool, top_k: int) -> int:
    print(f"Pipeline E2E — requête : {query!r} (évaluation={evaluation}, top_k={top_k})")
    services = build_pipeline_services()
    started = time.monotonic()
    try:
        state = await run_pipeline(
            query=query,
            services=services,
            evaluation_enabled=evaluation,
            top_k=top_k,
        )
    except Exception as exc:  # pragma: no cover - dépend du cluster
        print(f"ÉCHEC : {type(exc).__name__}: {exc}")
        return 1
    finally:
        await services.pool.close()

    elapsed = time.monotonic() - started
    if state.generated is None:
        print("Aucune réponse générée (aucun document pertinent ?).")
        return 1

    print(f"Réponse : {state.generated.answer[:300]}")
    print(f"Sources  : {len(state.search_results)} chunk(s)")
    for result in state.search_results:
        payload = result.get("payload", {})
        print(f"  - {payload.get('source_id', 'doc')} (score: {result.get('score', 0.0):.3f})")
    print(f"Confiance : {state.generated.confidence:.2f} — temps : {elapsed:.1f}s")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E pipeline RAG sur cluster")
    parser.add_argument("--query", default="résume l'architecture du cluster", help="Requête")
    parser.add_argument(
        "--evaluation", action="store_true", help="Active la boucle Judge→Advocate→Evaluator"
    )
    parser.add_argument("--top-k", type=int, default=8, help="Nombre de chunks récupérés")
    args = parser.parse_args()

    sys.exit(asyncio.run(_run(args.query, args.evaluation, args.top_k)))


if __name__ == "__main__":
    main()
