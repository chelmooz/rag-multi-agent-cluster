"""Point d'entrée API du cluster RAG multi-agents.

Architecture :
- FastAPI + LangGraph pour l'orchestration
- Configuration centralisée via src.core.settings
- Health/Readiness probes (consultation via curl/Glances — pas de Prometheus, cf. D9)
- Dashboard CTOS : GET / (SPA), /partials/* (fragments HTML), /api/v1/chat (SSE),
  /api/v1/monitoring (JSON poll)
"""
import asyncio
import json as jsonlib
import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, cast

import asyncpg
import httpx
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from src.agents.advocate import AdvocateAgent
from src.agents.evaluator import EvaluatorAgent
from src.agents.generator import GeneratorAgent
from src.agents.judge import JudgeAgent
from src.agents.langgraph_orchestrator import PipelineServices, run_pipeline
from src.agents.planner import PlannerAgent
from src.agents.rewriter import RewriterAgent
from src.agents.wiki_agent import WikiAgent
from src.core.settings import get_settings
from src.services.ingestion import IngestionService
from src.services.lexical import LexicalSearch
from src.services.monitoring import MonitoringService
from src.services.ollama import OllamaClientPool
from src.services.reranker import RerankerService
from src.services.vector import VectorService

settings = get_settings()

logger = logging.getLogger(__name__)

_TIMEOUT = 3.0


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)
    timestamp: str | None = None
    sources: list[str] = []
    elapsed_ms: int | None = None


class QueryRequest(BaseModel):
    question: str
    context: str | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    use_reranker: bool = True
    evaluation_enabled: bool | None = None  # Override settings
    messages: list[ChatMessage] | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[str] = []
    confidence: float | None = None
    chunks_used: int = 0


class IngestRequest(BaseModel):
    text: str
    source_type: str = "text"
    source_id: str | None = None
    metadata: dict[str, Any] | None = None
    context: str | None = None


class IngestResponse(BaseModel):
    source_id: str
    chunks_created: int
    chunks_indexed: int
    errors: list[str] = []


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=100)
    return_sparse: bool = True


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    sparse_vectors: list[dict[int, float]] | None = None
    model: str
    dimensions: int


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0-dev"
    environment: str = settings.log_level.lower()


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None


class OkfValidateRequest(BaseModel):
    path: str = Field(..., min_length=1)


async def _check_ollama(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"{url.rstrip('/')}/api/tags")
            return {"status": "ok" if r.status_code == 200 else "error", "detail": r.status_code}
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}


async def _check_qdrant(url: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"{url.rstrip('/')}/health")
            return {"status": "ok" if r.status_code == 200 else "error", "detail": r.status_code}
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}


async def _check_postgres(dsn: str) -> dict[str, Any]:
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=_TIMEOUT)
        await conn.close()
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}
    else:
        return {"status": "ok"}


async def _check_redis(url: str) -> dict[str, Any]:
    try:
        r = Redis.from_url(url, socket_connect_timeout=_TIMEOUT)
        await asyncio.wait_for(cast(Awaitable[bool], r.ping()), timeout=_TIMEOUT)
        await r.aclose()
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}
    else:
        return {"status": "ok"}


async def _run_checks() -> dict[str, Any]:
    checks = {
        "qdrant": _check_qdrant(str(settings.qdrant_url)),
        "ollama_m1": _check_ollama(str(settings.ollama_m1_url)),
        "ollama_m2": _check_ollama(str(settings.ollama_m2_url)),
        "ollama_m3": _check_ollama(str(settings.ollama_m3_url)),
        "postgresql": _check_postgres(settings.postgres_dsn),
        "redis": _check_redis(settings.redis_url),
    }
    results: dict[str, Any] = {}
    for name, coro in checks.items():
        try:
            results[name] = await asyncio.wait_for(coro, timeout=_TIMEOUT)
        except TimeoutError:
            results[name] = {"status": "error", "detail": "timeout"}
        except Exception as e:
            results[name] = {"status": "error", "detail": type(e).__name__}
    return results


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialiser les services partagés
    app.state.ollama_pool = OllamaClientPool()
    app.state.vector_service = VectorService()
    app.state.lexical_search = LexicalSearch()
    app.state.ingestion_service = IngestionService(
        ollama_pool=app.state.ollama_pool,
        vector_service=app.state.vector_service,
    )
    app.state.reranker_service = RerankerService(ollama_pool=app.state.ollama_pool)
    app.state.monitoring_service = MonitoringService(ollama_pool=app.state.ollama_pool)

    # Créer la collection Qdrant si nécessaire
    with suppress(Exception):
        await app.state.vector_service.create_collection()

    yield

    # Cleanup
    await app.state.ollama_pool.close()
    await app.state.vector_service.close()
    await app.state.ingestion_service.close()
    await app.state.reranker_service.close()
    await app.state.monitoring_service.close()


app = FastAPI(
    title="rag-multi-agent-cluster",
    description=(
        "Cluster RAG 100% Offline avec évaluation multi-agents "
        "(Juge + Avocat du diable + Évaluateur)"
    ),
    version="0.1.0-dev",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = str(Path(__file__).resolve().parents[2] / "static")
if settings.dashboard_enabled:
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(f"{settings.api_prefix}/health/memory", tags=["Health"])
async def health_memory() -> JSONResponse:
    """Snapshot mémoire du cluster (M1 Qdrant, M2 RTX4000, M3 BC-250).

    V1 lecture seule : renvoie l'état + alertes seuils, sans bloquer.
    """
    if not settings.memory_manager_enabled:
        return JSONResponse(
            status_code=200,
            content={"status": "disabled", "detail": "MEMORY_MANAGER_ENABLED=false"},
        )

    if not hasattr(app.state, "ollama_pool") or not hasattr(app.state, "vector_service"):
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Services not initialized - server starting up"},
        )

    from src.services.memory_manager import MemoryManager

    memory_manager = MemoryManager(
        ollama_pool=app.state.ollama_pool,
        vector_service=app.state.vector_service,
    )
    try:
        snapshot = await memory_manager.cluster_snapshot()
    finally:
        await memory_manager.close()

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok" if not snapshot.alerts else "degraded",
            "timestamp": snapshot.timestamp.isoformat(),
            "m1": {
                "qdrant_ram_mb": snapshot.m1.qdrant_ram_mb,
                "qdrant_points_count": snapshot.m1.qdrant_points_count,
                "loaded_models": snapshot.m1.loaded_models,
            },
            "m2": {
                "rtx4000_vram_mb": snapshot.m2.rtx4000_vram_mb,
                "judge_vram_mb": snapshot.m2.judge_vram_mb,
                "advocate_vram_mb": snapshot.m2.advocate_vram_mb,
                "reranker_vram_mb": snapshot.m2.reranker_vram_mb,
                "loaded_models": snapshot.m2.loaded_models,
            },
            "m3": {
                "bc250_unified_mb": snapshot.m3.bc250_unified_mb,
                "bc250_unified_percent": snapshot.m3.bc250_unified_percent,
                "bc250_cpu_load": snapshot.m3.bc250_cpu_load,
                "loaded_models": snapshot.m3.loaded_models,
            },
            "alerts": [
                {
                    "level": a.level,
                    "machine": a.machine,
                    "metric": a.metric,
                    "current": a.current,
                    "threshold": a.threshold,
                    "message": a.message,
                }
                for a in snapshot.alerts
            ],
        },
    )


@app.get(f"{settings.api_prefix}/ready", tags=["Health"])
async def ready() -> JSONResponse:
    checks = await _run_checks()
    all_ok = all(c["status"] == "ok" for c in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


@app.post(f"{settings.api_prefix}/embed", response_model=EmbedResponse, tags=["Embedding"])
async def embed(request: EmbedRequest) -> EmbedResponse:
    """Embedding texte → vecteur dense (nomic-embed-text-v2-moe) + sparse (BM25)."""
    # Vérifier que les services sont initialisés
    if not hasattr(app.state, "ollama_pool") or not hasattr(app.state, "lexical_search"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    pool: OllamaClientPool = app.state.ollama_pool
    lexical: LexicalSearch = app.state.lexical_search

    # Embedding dense via Ollama M1 (fallback M2)
    dense_embeddings = await pool.embed(request.texts)

    # Sparse vectors BM25
    sparse_vectors = None
    if request.return_sparse:
        sparse_vectors = lexical.encode_batch_to_dict(request.texts)

    return EmbedResponse(
        embeddings=dense_embeddings,
        sparse_vectors=sparse_vectors,
        model=settings.embedding_model,
        dimensions=len(dense_embeddings[0]) if dense_embeddings else 768,
    )


@app.post(f"{settings.api_prefix}/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest(request: IngestRequest) -> IngestResponse:
    """Ingestion d'une source (texte) → chunks → embeddings → Qdrant."""
    # Vérifier que les services sont initialisés
    if not hasattr(app.state, "ingestion_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    service: IngestionService = app.state.ingestion_service

    result = await service.ingest(
        text=request.text,
        source_type=request.source_type,
        source_id=request.source_id,
        metadata=request.metadata,
        context=request.context,
    )

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
        errors=result.errors,
    )


@app.post(f"{settings.api_prefix}/ingest/file", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_file(
    file: UploadFile,
    source_type: str = Form(default="file"),
    metadata: str = Form(default="{}"),
) -> IngestResponse:
    """Ingestion d'un fichier uploadé."""
    # Vérifier que les services sont initialisés
    if not hasattr(app.state, "ingestion_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    import json

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    meta = json.loads(metadata) if metadata else {}
    meta["filename"] = file.filename
    meta["content_type"] = file.content_type

    service: IngestionService = app.state.ingestion_service

    result = await service.ingest(
        text=text,
        source_type=source_type,
        source_id=None,
        metadata=meta,
        context=None,
    )

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
        errors=result.errors,
    )


@app.post(f"{settings.api_prefix}/query", response_model=QueryResponse, tags=["RAG"])
async def query(request: QueryRequest) -> QueryResponse:
    """Endpoint principal de requête RAG — pipeline multi-agents LangGraph.

    Pipeline (Phase B) :
    1. Embedding de la requête (dense + sparse)
    2. Hybrid Search Qdrant (RRF fusion dense + BM25)
    3. Reranker (bge-reranker-v2-m3 sur RTX 4000)
    4. Assemblage contexte + Génération (M3) via build_graph
    5. Évaluation optionnelle (Judge → Advocate → Evaluator, B6)
    """
    # Vérifier que les services sont initialisés
    if not hasattr(app.state, "ollama_pool") or not hasattr(app.state, "vector_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    pool: OllamaClientPool = app.state.ollama_pool
    vector: VectorService = app.state.vector_service
    lexical: LexicalSearch = app.state.lexical_search
    reranker: RerankerService = app.state.reranker_service

    services = PipelineServices(
        pool=pool,
        vector=vector,
        lexical=lexical,
        reranker=reranker,
        wiki=_wiki_agent(),
        planner=PlannerAgent(pool),
        rewriter=RewriterAgent(pool),
        generator=GeneratorAgent(pool),
        judge=JudgeAgent(pool),
        advocate=AdvocateAgent(pool),
        evaluator=EvaluatorAgent(pool),
    )

    evaluation = (
        request.evaluation_enabled
        if request.evaluation_enabled is not None
        else settings.evaluation_enabled
    )

    history = (
        [{"role": m.role, "content": m.content} for m in request.messages]
        if request.messages
        else None
    )
    state = await run_pipeline(
        query=request.question,
        conversation_history=history,
        services=services,
        evaluation_enabled=evaluation,
        top_k=request.top_k,
        use_reranker=request.use_reranker,
        score_threshold=settings.similarity_threshold,
    )

    # Sources formatées pour la réponse
    sources: list[str] = []
    for result in state.search_results:
        payload = result.get("payload", {})
        source_id = payload.get("source_id", "doc")
        score = result.get("rerank_score", result.get("score", 0.0))
        sources.append(f"{source_id} (score: {score:.3f})")

    if state.generated is None:
        return QueryResponse(
            answer="Aucun document pertinent trouvé dans la base de connaissances.",
            sources=sources,
            confidence=0.0,
            chunks_used=len(state.assembled.chunks) if state.assembled else 0,
        )

    confidence = state.generated.confidence
    if state.evaluator is not None and state.evaluator.get("final_score") is not None:
        confidence = state.evaluator["final_score"]

    return QueryResponse(
        answer=state.generated.answer,
        sources=sources,
        confidence=confidence,
        chunks_used=len(state.assembled.chunks) if state.assembled else 0,
    )


# ──────────────────────────────────────────────
# OKF Endpoints (Phase 0.8 / B8)
# ──────────────────────────────────────────────
def _wiki_agent() -> WikiAgent:
    """Retourne le WikiAgent (lazy : injecté par les tests via app.state)."""
    wiki = getattr(app.state, "wiki_agent", None)
    if wiki is None:
        wiki = WikiAgent()
        app.state.wiki_agent = wiki
    return wiki


@app.post(f"{settings.api_prefix}/okf/validate", tags=["OKF"])
async def okf_validate(request: OkfValidateRequest) -> dict[str, Any]:
    """Valide le frontmatter OKF v0.2 d'une page du vault."""
    try:
        result = await _wiki_agent().validate_frontmatter(request.path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": request.path, **result}


@app.get(f"{settings.api_prefix}/okf/list", tags=["OKF"])
async def okf_list() -> dict[str, Any]:
    """Liste les pages du vault (hors index.md/log.md)."""
    pages = await _wiki_agent().list_pages()
    return {"pages": pages, "count": len(pages)}


@app.get(f"{settings.api_prefix}/okf/show", tags=["OKF"])
async def okf_show(path: str) -> dict[str, Any]:
    """Affiche une page du vault (frontmatter + contenu markdown)."""
    try:
        return await _wiki_agent().read_page(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ──────────────────────────────────────────────
# Lint Endpoint (Phase 4.6 / B8)
# ──────────────────────────────────────────────
@app.get(f"{settings.api_prefix}/lint", tags=["Wiki"])
async def lint() -> dict[str, Any]:
    """Lint du vault : pages orphelines, stale, contradictions, gaps."""
    return await _wiki_agent().lint()


# ──────────────────────────────────────────────
# Dashboard CTOS — SPA (chat + monitoring)
# ──────────────────────────────────────────────
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


@app.get("/", include_in_schema=False)
async def dashboard_index() -> FileResponse:
    """Page unique du dashboard CTOS (chat + monitoring)."""
    return FileResponse(f"{_STATIC_DIR}/index.html")


@app.get("/partials/chat", include_in_schema=False)
async def partial_chat() -> FileResponse:
    """Fragment HTML : zone messages (vide au premier chargement) + input."""
    return FileResponse(f"{_STATIC_DIR}/partials/chat.html")


@app.get("/partials/monitoring", include_in_schema=False)
async def partial_monitoring() -> JSONResponse:
    """Fragment HTML : 4 cartes monitoring (poll JS 10s)."""
    if not hasattr(app.state, "monitoring_service"):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"},
        )
    service: MonitoringService = app.state.monitoring_service
    data = await service.summary()
    html = (
        _render_card(data["cards"]["m1"])
        + _render_card(data["cards"]["m2"])
        + _render_card(data["cards"]["m3"])
        + _render_card(data["cluster"])
    )
    return JSONResponse(content={"html": html, "alerts": data["alerts"]})


@app.get(f"{settings.api_prefix}/monitoring", tags=["Dashboard"])
async def monitoring_json() -> JSONResponse:
    """JSON agrégé pour le dashboard (poll JS 10s)."""
    if not hasattr(app.state, "monitoring_service"):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"},
        )
    service: MonitoringService = app.state.monitoring_service
    data = await service.summary()
    return JSONResponse(content=data)


@app.post(f"{settings.api_prefix}/chat", tags=["Dashboard"])
async def chat_sse(request: ChatRequest) -> StreamingResponse:
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
            if not hasattr(app.state, "vector_service"):
                yield _sse({"type": "error", "detail": "Services not initialized"})
                return

            pool: OllamaClientPool = app.state.ollama_pool
            vector: VectorService = app.state.vector_service
            lexical: LexicalSearch = app.state.lexical_search
            reranker: RerankerService = app.state.reranker_service

            query_embeddings = await pool.embed([request.question])
            if not query_embeddings:
                yield _sse({"type": "error", "detail": "Échec embedding requête"})
                return
            query_dense = query_embeddings[0]
            query_sparse = lexical.encode_to_dict(request.question)

            search_results = await vector.hybrid_search(
                query_vector=query_dense,
                query_sparse=query_sparse,
                top_k=settings.top_k_retrieval * 3,
                score_threshold=settings.similarity_threshold,
            )

            if not search_results:
                msg = "Aucun document pertinent trouvé dans la base de connaissances."
                yield _sse({"type": "token", "token": msg})
                yield _sse({"type": "done", "elapsed_ms": _elapsed_ms(started), "sources": []})
                return

            if len(search_results) > 1:
                docs_texts = [r["payload"].get("text", "") for r in search_results]
                reranked = await reranker.rerank(
                    request.question, docs_texts, top_k=settings.top_k_rerank
                )
                final_results = []
                for rr in reranked:
                    orig = search_results[rr.index]
                    final_results.append({**orig, "rerank_score": rr.score})
                search_results = final_results
            else:
                search_results = search_results[: settings.top_k_rerank]

            chunks_used = len(search_results)
            sources: list[str] = []
            context_parts: list[str] = []
            budget = settings.chat_max_context_chars

            for i, result in enumerate(search_results):
                payload = result.get("payload", {})
                text = payload.get("text", "")
                source_id = payload.get("source_id", f"doc_{i}")
                score = result.get("rerank_score", result.get("score", 0.0))
                sources.append(f"{source_id} (score: {score:.3f})")
                snippet = f"[Source {i+1}] {text}"
                if len("".join(context_parts)) + len(snippet) > budget:
                    break
                context_parts.append(snippet)

            context = (
                "\n\n".join(context_parts) if context_parts
                else "Aucun contexte pertinent trouvé."
            )
            prompt = (
                "Tu es CTOS, assistant du cluster RAG maison (M1 master / M2 GPU / M3 BC-250). "
                "Réponds en français, uniquement à partir du contexte fourni ci-dessous. "
                "Si le contexte ne contient pas la réponse, dis-le clairement.\n\n"
                f"CONTEXTE:\n{context}\n\n"
                f"QUESTION: {request.question}\n\n"
                "RÉPONSE:"
            )

            answer = ""
            if context_parts:
                try:
                    result = await pool.generate(prompt)
                    answer = str(result.get("response", "")).strip()
                except Exception as e:
                    logger.warning("Génération LLM échouée (%s), repli sur contexte", e)
                    answer = ""
            if not answer:
                answer = "\n\n".join(context_parts) if context_parts else "Pas de contexte trouvé."

            # Streaming par chunks (simulation naturelle de lecture)
            for chunk in _chunk_text(answer, size=24):
                yield _sse({"type": "token", "token": chunk})

            yield _sse({
                "type": "done",
                "elapsed_ms": _elapsed_ms(started),
                "sources": sources,
                "chunks_used": chunks_used,
            })
        except Exception as e:
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
