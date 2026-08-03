"""Routes santé : /health, /health/memory, /ready + checks sous-jacents.

Les helpers `_check_*` et `_run_checks` sont ré-exportés par src.api.main
(imports directs + patches des tests) — ils résolvent donc leurs dépendances
via le module `main` au moment de l'appel.
"""

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any, cast

import asyncpg
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

import src.api.main as api_main
from src.api.schemas import HealthResponse
from src.core.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

_TIMEOUT = 3.0
settings = get_settings()


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
        "qdrant": api_main._check_qdrant(str(settings.qdrant_url)),
        "ollama_m1": api_main._check_ollama(str(settings.ollama_m1_url)),
        "ollama_m2": api_main._check_ollama(str(settings.ollama_m2_url)),
        "ollama_m3": api_main._check_ollama(str(settings.ollama_m3_url)),
        "postgresql": api_main._check_postgres(settings.postgres_dsn),
        "redis": api_main._check_redis(settings.redis_url),
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


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.log_level.lower())


@router.get("/health/memory")
async def health_memory(request: Request) -> JSONResponse:
    """Snapshot mémoire du cluster (M1 Qdrant, M2 RTX4000, M3 BC-250).

    V1 lecture seule : renvoie l'état + alertes seuils, sans bloquer.
    """
    if not settings.memory_manager_enabled:
        return JSONResponse(
            status_code=200,
            content={"status": "disabled", "detail": "MEMORY_MANAGER_ENABLED=false"},
        )

    state = request.app.state
    if not hasattr(state, "ollama_pool") or not hasattr(state, "vector_service"):
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Services not initialized - server starting up"},
        )

    from src.services.memory_manager import MemoryManager

    memory_manager = MemoryManager(
        ollama_pool=state.ollama_pool,
        vector_service=state.vector_service,
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


@router.get("/ready")
async def ready() -> JSONResponse:
    checks = await _run_checks()
    all_ok = all(c["status"] == "ok" for c in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )
