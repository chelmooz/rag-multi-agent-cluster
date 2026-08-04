"""Point d'assemblage API du cluster RAG multi-agents.

Architecture :
- FastAPI + LangGraph pour l'orchestration
- Configuration centralisée via src.core.settings
- Health/Readiness probes (consultation via curl/Glances — pas de Prometheus, cf. D9)
- Dashboard CTOS : GET / (SPA), /partials/* (fragments HTML), /api/v1/chat (SSE),
  /api/v1/monitoring (JSON poll)

Ce module reste le namespace public du paquet : les tests importent et
patchent des symboles via `src.api.main.*` (helpers, run_pipeline, services),
ils sont donc ré-exportés ici sans autre usage.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from src.agents.langgraph_orchestrator import PipelineServices, run_pipeline
from src.core.settings import get_settings
from src.services.ingestion import IngestionService
from src.services.lexical import LexicalSearch
from src.services.monitoring import MonitoringService
from src.services.ollama import OllamaClientPool
from src.services.reranker import RerankerService
from src.services.vector import VectorService

from .routers import dashboard, embedding, health, ingestion, okf, rag
from .routers.dashboard import _STATIC_DIR, _chunk_text, _elapsed_ms, _render_card, _sse
from .routers.health import (
    _check_ollama,
    _check_postgres,
    _check_qdrant,
    _check_redis,
    _run_checks,
)

__all__ = [
    # Ré-exports compatibilité tests (imports directs + patches src.api.main.*)
    "_STATIC_DIR",
    "PipelineServices",
    "Redis",
    "_cache_redis",
    "_check_ollama",
    "_check_postgres",
    "_check_qdrant",
    "_check_redis",
    "_chunk_text",
    "_elapsed_ms",
    "_render_card",
    "_run_checks",
    "_sse",
    "app",
    "asyncpg",
    "httpx",
    "not_implemented_handler",
    "run_pipeline",
]

settings = get_settings()

logger = logging.getLogger(__name__)


def _cache_redis() -> Redis:
    """Client Redis du cache sémantique (R5) — jetable, fermé par l'appelant."""
    return Redis.from_url(settings.redis.url, decode_responses=True)


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

if settings.dashboard_enabled:
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(embedding.router, prefix=settings.api_prefix)
app.include_router(ingestion.router, prefix=settings.api_prefix)
app.include_router(rag.router, prefix=settings.api_prefix)
app.include_router(okf.router, prefix=settings.api_prefix)
app.include_router(dashboard.router)
app.include_router(dashboard.api_router, prefix=settings.api_prefix)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
