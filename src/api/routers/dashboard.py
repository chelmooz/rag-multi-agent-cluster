"""Dashboard CTOS — SPA (chat SSE + monitoring) et helpers associés.

Les helpers `_sse`, `_elapsed_ms`, `_chunk_text`, `_render_card` sont
ré-exportés par src.api.main (imports directs des tests).
"""

import asyncio
import json as jsonlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from src.api.schemas import ChatRequest
from src.core.settings import get_settings
from src.services.lexical import LexicalSearch
from src.services.monitoring import MonitoringService
from src.services.ollama import OllamaClientPool
from src.services.reranker import RerankerService
from src.services.vector import VectorService

logger = logging.getLogger(__name__)

router = APIRouter()
api_router = APIRouter(tags=["Dashboard"])

settings = get_settings()

_STATIC_DIR = str(Path(__file__).resolve().parents[3] / "static")


def _render_card(card: Any) -> str:
    """Rend une carte monitoring en HTML (fragment htmx/partial)."""
    if not isinstance(card, dict):
        card = card.to_dict()
    status_cls = card["status"] if card["status"] in {"ok", "warn", "crit", "n/a"} else "ok"
    rows = "".join(
        f'<div class="m-row"><span class="m-label">{m["label"]}</span>'
        f'<span class="m-value {m["status"]}">{m["value"]}</span></div>'
        for m in card["metrics"]
    )
    return (
        f'<div class="metric-card {status_cls}" data-machine="{card["machine"]}">'
        f'<div class="card-header"><span class="machine-label">{card["title"]}</span>'
        f'<span class="status-dot {status_cls}" title="status: {status_cls}"></span></div>'
        f'<div class="metrics-grid">{rows}</div></div>'
    )


@router.get("/", include_in_schema=False)
async def dashboard_index() -> FileResponse:
    """Page unique du dashboard CTOS (chat + monitoring)."""
    return FileResponse(f"{_STATIC_DIR}/index.html")


@router.get("/partials/chat", include_in_schema=False)
async def partial_chat() -> FileResponse:
    """Fragment HTML : zone messages (vide au premier chargement) + input."""
    return FileResponse(f"{_STATIC_DIR}/partials/chat.html")


@router.get("/partials/monitoring", include_in_schema=False)
async def partial_monitoring(request: Request) -> JSONResponse:
    """Fragment HTML : 4 cartes monitoring (poll JS 10s)."""
    state = request.app.state
    if not hasattr(state, "monitoring_service"):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"},
        )
    service: MonitoringService = state.monitoring_service
    data = await service.summary()
    html = (
        _render_card(data["cards"]["m1"])
        + _render_card(data["cards"]["m2"])
        + _render_card(data["cards"]["m3"])
        + _render_card(data["cluster"])
    )
    return JSONResponse(content={"html": html, "alerts": data["alerts"]})


@api_router.get("/monitoring")
async def monitoring_json(request: Request) -> JSONResponse:
    """JSON agrégé pour le dashboard (poll JS 10s)."""
    state = request.app.state
    if not hasattr(state, "monitoring_service"):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"},
        )
    service: MonitoringService = state.monitoring_service
    data = await service.summary()
    return JSONResponse(content=data)


async def _retrieve(
    pool: OllamaClientPool,
    vector: VectorService,
    lexical: LexicalSearch,
    question: str,
) -> list[dict[str, Any]] | None:
    """Recherche hybride (dense + full-text BM25 natif) ; None si l'embedding échoue."""
    query_embeddings = await pool.embed([question])
    if not query_embeddings:
        return None
    query_text = lexical.build_query(question)
    return await vector.hybrid_search(
        query_vector=query_embeddings[0],
        query_text=query_text,
        top_k=settings.top_k_retrieval * 3,
        score_threshold=settings.similarity_threshold,
    )


async def _rerank_search_results(
    reranker: RerankerService, question: str, search_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Rerank si >1 résultat, sinon tronque au top_k_rerank."""
    if len(search_results) > 1:
        docs_texts = [r["payload"].get("text", "") for r in search_results]
        reranked = await reranker.rerank(question, docs_texts, top_k=settings.top_k_rerank)
        final_results = []
        for rr in reranked:
            orig = search_results[rr.index]
            final_results.append({**orig, "rerank_score": rr.score})
        return final_results
    return search_results[: settings.top_k_rerank]


def _select_context(
    search_results: list[dict[str, Any]], budget: int
) -> tuple[list[str], list[str]]:
    """Filtre les résultats au budget de caractères ; renvoie (sources, context_parts)."""
    sources: list[str] = []
    context_parts: list[str] = []
    used_chars = 0
    for i, result in enumerate(search_results):
        payload = result.get("payload", {})
        text = payload.get("text", "")
        source_id = payload.get("source_id", f"doc_{i}")
        score = result.get("rerank_score", result.get("score", 0.0))
        snippet = f"[Source {i + 1}] {text}"
        if used_chars + len(snippet) > budget:
            break
        context_parts.append(snippet)
        used_chars += len(snippet)
        sources.append(f"{source_id} (score: {score:.3f})")
    return sources, context_parts


async def _chat_answer(pool: OllamaClientPool, question: str, context_parts: list[str]) -> str:
    """Réponse finale : génération LLM sur le contexte, repli sur le contexte si échec."""
    if not context_parts:
        return "Pas de contexte trouvé."
    context = "\n\n".join(context_parts)
    prompt = (
        "Tu es CTOS, assistant du cluster RAG maison (M1 master / M2 GPU / M3 BC-250). "
        "Réponds en français, uniquement à partir du contexte fourni ci-dessous. "
        "Si le contexte ne contient pas la réponse, dis-le clairement.\n\n"
        f"CONTEXTE:\n{context}\n\n"
        f"QUESTION: {question}\n\n"
        "RÉPONSE:"
    )
    answer = ""
    try:
        result = await pool.generate(prompt)
        answer = str(result.get("response", "")).strip()
    except Exception as e:
        logger.warning("Génération LLM échouée (%s), repli sur contexte", e)
    return answer or context


@api_router.post("/chat")
async def chat_sse(request: ChatRequest, http_request: Request) -> StreamingResponse:
    """Chat RAG — réponse streaming (SSE) avec temps d'exécution.

    Pipeline : /query (hybrid search + rerank) puis réponse structurée.
    Événements SSE : token (texte) puis done (elapsed_ms, sources).
    """

    async def event_stream() -> AsyncIterator[str]:
        started = asyncio.get_running_loop().time()
        try:
            if settings.monitoring_offline:
                yield _sse(
                    {
                        "type": "error",
                        "detail": "Prédéploiement — aucune machine du cluster installée",
                    }
                )
                return
            state = http_request.app.state
            if not hasattr(state, "vector_service"):
                yield _sse({"type": "error", "detail": "Services not initialized"})
                return

            pool: OllamaClientPool = state.ollama_pool
            vector: VectorService = state.vector_service
            lexical: LexicalSearch = state.lexical_search
            reranker: RerankerService = state.reranker_service

            search_results = await _retrieve(pool, vector, lexical, request.question)
            if search_results is None:
                yield _sse({"type": "error", "detail": "Échec embedding requête"})
                return
            if not search_results:
                yield _sse(
                    {
                        "type": "token",
                        "token": "Aucun document pertinent trouvé dans la base de connaissances.",
                    }
                )
                yield _sse({"type": "done", "elapsed_ms": _elapsed_ms(started), "sources": []})
                return

            search_results = await _rerank_search_results(
                reranker, request.question, search_results
            )
            sources, context_parts = _select_context(
                search_results, settings.chat_max_context_chars
            )
            chunks_used = len(context_parts)

            answer = await _chat_answer(pool, request.question, context_parts)

            # Streaming par chunks (simulation naturelle de lecture)
            for chunk in _chunk_text(answer, size=24):
                yield _sse({"type": "token", "token": chunk})

            yield _sse(
                {
                    "type": "done",
                    "elapsed_ms": _elapsed_ms(started),
                    "sources": sources,
                    "chunks_used": chunks_used,
                }
            )
        except Exception as e:
            logger.exception("Chat SSE échoué (%s)", type(e).__name__)
            yield _sse({"type": "error", "detail": type(e).__name__})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {jsonlib.dumps(payload, ensure_ascii=False)}\n\n"


def _elapsed_ms(started: float) -> int:
    import time

    return int((time.monotonic() - started) * 1000)


def _chunk_text(text: str, size: int = 24) -> list[str]:
    """Découpe le texte en morceaux de ~size tokens (mots)."""
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]
