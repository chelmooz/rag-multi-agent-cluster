"""Point d'entrée API du cluster RAG multi-agents.

Architecture :
- FastAPI + LangGraph pour l'orchestration
- Configuration centralisée via src.core.settings
- Health/Readiness probes pour Prometheus/K8s
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.core.settings import get_settings

settings = get_settings()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestion du cycle de vie de l'application."""
    # Startup: init clients, warm pools, etc.
    # TODO: init httpx AsyncClient pool avec retry/circuit-breaker (Phase 2.5)
    # TODO: warmup Ollama clients M1/M2/M3 avec healthchecks (Phase 0.11)
    yield
    # Shutdown: close pools, flush metrics
    # TODO: close httpx client, flush Prometheus metrics


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

# Convertir les NotImplementedError en 500 JSON (les stubs de phase 0)
@app.exception_handler(NotImplementedError)
async def not_implemented_handler(request: Request, exc: NotImplementedError):
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# CORS pour Obsidian / clients locaux
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restreindre en prod via settings
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """Health check simple (liveness probe)."""
    return HealthResponse(status="ok")


@app.get(f"{settings.api_prefix}/ready", tags=["Health"])
async def ready() -> dict[str, str]:
    """Readiness check (dépendances : Qdrant, Ollama, PostgreSQL, Redis).

    Retourne 200 si toutes les dépendances sont accessibles, 503 sinon.
    Utilisé par Prometheus / Kubernetes pour le trafic.
    """
    # TODO: implémenter checks réels (Phase 0.17)
    # - Qdrant: GET /health
    # - Ollama M1/M2/M3: GET /api/tags
    # - PostgreSQL: pg_isready
    # - Redis: PING
    return {"status": "ready", "checks": "TODO"}


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
