"""Point d'entrée API du cluster RAG multi-agents.

Architecture :
- FastAPI + LangGraph pour l'orchestration
- Configuration centralisée via src.core.settings
- Health/Readiness probes (consultation via curl/Glances — pas de Prometheus, cf. D9)
"""
import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager, suppress
from typing import Any, cast

import asyncpg
import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from src.core.settings import get_settings
from src.services.ingestion import IngestionService
from src.services.lexical import LexicalSearch
from src.services.ollama import OllamaClientPool
from src.services.reranker import RerankerService
from src.services.vector import VectorService

settings = get_settings()

_TIMEOUT = 3.0


class QueryRequest(BaseModel):
    question: str
    context: str | None = None
    top_k: int = Field(default=8, ge=1, le=50)
    use_reranker: bool = True
    evaluation_enabled: bool | None = None  # Override settings


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

    # Créer la collection Qdrant si nécessaire
    with suppress(Exception):
        await app.state.vector_service.create_collection()

    yield

    # Cleanup
    await app.state.ollama_pool.close()
    await app.state.vector_service.close()
    await app.state.ingestion_service.close()
    await app.state.reranker_service.close()


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


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


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
    if not hasattr(app.state, 'ollama_pool') or not hasattr(app.state, 'lexical_search'):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"}
        )

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
    if not hasattr(app.state, 'ingestion_service'):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"}
        )

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
    if not hasattr(app.state, 'ingestion_service'):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"}
        )

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

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
        errors=result.errors,
    )


@app.post(f"{settings.api_prefix}/query", response_model=QueryResponse, tags=["RAG"])
async def query(request: QueryRequest) -> QueryResponse:
    """Endpoint principal de requête RAG — Hybrid Search + Reranker.

    Pipeline (Phase A) :
    1. Embedding de la requête (dense + sparse)
    2. Hybrid Search Qdrant (RRF fusion dense + BM25)
    3. Reranker (bge-reranker-v2-m3 sur RTX 4000)
    4. Construction réponse (Phase B ajoutera Generator + Évaluation)
    """
    # Vérifier que les services sont initialisés
    if not hasattr(app.state, 'ollama_pool') or not hasattr(app.state, 'vector_service'):
        return JSONResponse(
            status_code=503,
            content={"detail": "Services not initialized - server starting up"}
        )

    pool: OllamaClientPool = app.state.ollama_pool
    vector: VectorService = app.state.vector_service
    lexical: LexicalSearch = app.state.lexical_search
    reranker: RerankerService = app.state.reranker_service

    # 1. Embedding requête (dense + sparse)
    query_embeddings = await pool.embed([request.question])
    if not query_embeddings:
        raise ValueError("Échec embedding requête")
    query_dense = query_embeddings[0]
    query_sparse = lexical.encode_to_dict(request.question)

    # 2. Hybrid Search Qdrant
    search_results = await vector.hybrid_search(
        query_vector=query_dense,
        query_sparse=query_sparse,
        top_k=request.top_k * 3 if request.use_reranker else request.top_k,
        score_threshold=settings.similarity_threshold,
    )

    if not search_results:
        return QueryResponse(
            answer="Aucun document pertinent trouvé dans la base de connaissances.",
            sources=[],
            confidence=0.0,
            chunks_used=0,
        )

    # 3. Reranker (optionnel)
    if request.use_reranker and len(search_results) > 1:
        docs_texts = [r["payload"].get("text", "") for r in search_results]
        reranked = await reranker.rerank(request.question, docs_texts, top_k=request.top_k)
        # Remapper les résultats rerankés
        final_results = []
        for rr in reranked:
            orig = search_results[rr.index]
            final_results.append({
                **orig,
                "rerank_score": rr.score,
            })
        search_results = final_results
    else:
        search_results = search_results[:request.top_k]

    # 4. Construire réponse (pour l'instant: concaténation des chunks top-k)
    # Phase B ajoutera: Generator → Judge → Advocate → Evaluator
    chunks_used = len(search_results)
    context_parts = []
    sources = []

    for i, result in enumerate(search_results):
        payload = result.get("payload", {})
        text = payload.get("text", "")
        source_id = payload.get("source_id", f"doc_{i}")
        score = result.get("rerank_score", result.get("score", 0.0))

        context_parts.append(f"[Source {i+1} (score: {score:.3f})] {text}")
        sources.append(f"{source_id} (score: {score:.3f})")

    answer = "\n\n".join(context_parts) if context_parts else "Pas de contexte trouvé."

    return QueryResponse(
        answer=answer,
        sources=sources,
        confidence=0.5,  # Placeholder - Phase B calculera via Évaluateur
        chunks_used=chunks_used,
    )


# ──────────────────────────────────────────────
# OKF Endpoints (Phase 0.8)
# ──────────────────────────────────────────────
@app.post(f"{settings.api_prefix}/okf/validate", tags=["OKF"])
async def okf_validate() -> dict[str, str]:
    raise NotImplementedError("OKF validate pas encore implémenté")


@app.get(f"{settings.api_prefix}/okf/list", tags=["OKF"])
async def okf_list() -> dict[str, str]:
    raise NotImplementedError("OKF list pas encore implémenté")


@app.get(f"{settings.api_prefix}/okf/show", tags=["OKF"])
async def okf_show() -> dict[str, str]:
    raise NotImplementedError("OKF show pas encore implémenté")


# ──────────────────────────────────────────────
# Lint Endpoint (Phase 4.6)
# ──────────────────────────────────────────────
@app.get(f"{settings.api_prefix}/lint", tags=["Wiki"])
async def lint() -> dict[str, str]:
    raise NotImplementedError("Lint wiki pas encore implémenté")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
