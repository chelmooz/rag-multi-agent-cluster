"""Point d'entrée API du cluster RAG multi-agents.

Architecture :
- FastAPI + LangGraph pour l'orchestration
- Configuration centralisée via src.core.settings
- Health/Readiness probes pour Prometheus/K8s
"""
import asyncio
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis

from src.core.settings import get_settings

settings = get_settings()

_TIMEOUT = 3.0


class QueryRequest(BaseModel):
    question: str
    context: str | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[str] = []
    confidence: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0-dev"
    environment: str = settings.log_level.lower()


async def _check_ollama(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"{url.rstrip('/')}/api/tags")
            return {"status": "ok" if r.status_code == 200 else "error", "detail": r.status_code}
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}


async def _check_qdrant(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.get(f"{url.rstrip('/')}/health")
            return {"status": "ok" if r.status_code == 200 else "error", "detail": r.status_code}
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}


async def _check_postgres(dsn: str) -> dict:
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=_TIMEOUT)
        await conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}


async def _check_redis(url: str) -> dict:
    try:
        r = Redis.from_url(url, socket_connect_timeout=_TIMEOUT)
        await asyncio.wait_for(r.ping(), timeout=_TIMEOUT)
        await r.aclose()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": type(e).__name__}


async def _run_checks() -> dict:
    checks = {
        "qdrant": _check_qdrant(str(settings.qdrant_url)),
        "ollama_m1": _check_ollama(str(settings.ollama_m1_url)),
        "ollama_m2": _check_ollama(str(settings.ollama_m2_url)),
        "ollama_m3": _check_ollama(str(settings.ollama_m3_url)),
        "postgresql": _check_postgres(settings.postgres_dsn),
        "redis": _check_redis(settings.redis_url),
    }
    results = {}
    for name, coro in checks.items():
        try:
            results[name] = await asyncio.wait_for(coro, timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            results[name] = {"status": "error", "detail": "timeout"}
        except Exception as e:
            results[name] = {"status": "error", "detail": type(e).__name__}
    return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


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
async def not_implemented_handler(request: Request, exc: NotImplementedError):
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


@app.post(f"{settings.api_prefix}/query", response_model=QueryResponse, tags=["RAG"])
async def query(request: QueryRequest) -> QueryResponse:
    """Endpoint principal de requête RAG multi-agents.

    Pipeline :
    1. Planner → intention + stratégie
    2. QueryRewriter → réécriture conversationnelle
    3. Hybrid Search (BM25 + Vectoriel) → rerank
    4. ContextAssembler → chunks + savoir interne
    5. Generator (BC250) → réponse brute
    6. Judge (RTX 4000) → évaluation qualité
    7. Avocat du diable (RTX 4000) → recherche failles
    8. Évaluateur (CPU M1) → synthèse finale + décision
    9. Wiki Agent → MAJ vault Obsidian (index.md, log.md, pages)
    """
    # TODO: brancher le pipeline réel (Phase 2-3)
    raise NotImplementedError("Pipeline RAG multi-agents pas encore implémenté")


@app.post(f"{settings.api_prefix}/ingest", tags=["Ingestion"])
async def ingest() -> dict[str, str]:
    """Ingestion d'une source (fichier, URL, texte) → pages wiki + index Qdrant."""
    # TODO: implémenter (Phase 1.1, 4.4)
    raise NotImplementedError("Ingestion pas encore implémentée")


@app.get(f"{settings.api_prefix}/embed", tags=["Embedding"])
async def embed() -> dict[str, str]:
    """Embedding texte → vecteur dense + sparse (bge-m3) + fallback histogramme."""
    # TODO: implémenter (Phase 1.6)
    raise NotImplementedError("Endpoint /embed pas encore implémenté")


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
