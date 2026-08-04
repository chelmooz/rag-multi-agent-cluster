"""Route /query — pipeline RAG multi-agents LangGraph.

`PipelineServices` et `run_pipeline` sont résolus via le module src.api.main
au moment de l'appel : les tests les patchent via "src.api.main.*".
"""

import logging

from fastapi import APIRouter, HTTPException, Request

import src.api.main as api_main
from src.agents.advocate import AdvocateAgent
from src.agents.evaluator import EvaluatorAgent
from src.agents.generator import GeneratorAgent
from src.agents.judge import JudgeAgent
from src.agents.planner import PlannerAgent
from src.agents.rewriter import RewriterAgent
from src.api.routers.okf import _wiki_agent
from src.api.schemas import QueryRequest, QueryResponse
from src.core.settings import get_settings
from src.services.access_policy import build_policy
from src.services.lexical import LexicalSearch
from src.services.ollama import OllamaClientPool
from src.services.reranker import RerankerService
from src.services.semantic_cache import SemanticCache
from src.services.vector import VectorService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["RAG"])

settings = get_settings()


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest, http_request: Request) -> QueryResponse:
    """Endpoint principal de requête RAG — pipeline multi-agents LangGraph.

    Pipeline (Phase B) :
    1. Embedding de la requête (dense + sparse)
    2. Hybrid Search Qdrant (RRF fusion dense + BM25)
    3. Reranker (bge-reranker-v2-m3 sur RTX 4000)
    4. Assemblage contexte + Génération (M3) via build_graph
    5. Évaluation optionnelle (Judge → Advocate → Evaluator, B6)
    """
    state = http_request.app.state
    if not hasattr(state, "ollama_pool") or not hasattr(state, "vector_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    pool: OllamaClientPool = state.ollama_pool
    vector: VectorService = state.vector_service
    lexical: LexicalSearch = state.lexical_search
    reranker: RerankerService = state.reranker_service

    services = api_main.PipelineServices(
        pool=pool,
        vector=vector,
        lexical=lexical,
        reranker=reranker,
        wiki=_wiki_agent(http_request.app),
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

    # R5 : cache sémantique (OFF par défaut) — hors boucle d'évaluation et user scope
    cache: SemanticCache | None = None
    if settings.semantic_cache_enabled and not evaluation and not request.access_scope:

        async def _embed_one(value: str) -> list[float] | None:
            rows = await pool.embed([value])
            return rows[0] if rows else None

        cache = SemanticCache(
            embed=_embed_one,
            redis=api_main._cache_redis(),
            enabled=True,
            threshold=settings.semantic_cache_threshold,
            ttl_seconds=settings.semantic_cache_ttl_seconds,
        )

    try:
        if cache is not None:
            cached = await cache.get(request.question)
            if cached is not None:
                return QueryResponse(
                    answer=str(cached.get("answer", "")),
                    sources=[str(s) for s in cached.get("sources", [])],
                    confidence=(
                        float(cached["confidence"])
                        if cached.get("confidence") is not None
                        else None
                    ),
                    chunks_used=0,
                    cache_hit=True,
                )

        # R6 : filtre d'accès par requête (NoAuthPolicy par défaut)
        user_filter = build_policy(request.access_scope).build_filter(
            request.user, request.access_scope
        )

        pipeline_state = await api_main.run_pipeline(
            query=request.question,
            conversation_history=history,
            services=services,
            evaluation_enabled=evaluation,
            top_k=request.top_k,
            use_reranker=request.use_reranker,
            score_threshold=settings.similarity_threshold,
            user_filter=user_filter,
        )

        # Sources formatées pour la réponse
        sources: list[str] = []
        for result in pipeline_state.search_results:
            payload = result.get("payload", {})
            source_id = payload.get("source_id", "doc")
            score = result.get("rerank_score", result.get("score", 0.0))
            sources.append(f"{source_id} (score: {score:.3f})")

        if pipeline_state.generated is None:
            return QueryResponse(
                answer="Aucun document pertinent trouvé dans la base de connaissances.",
                sources=sources,
                confidence=0.0,
                chunks_used=len(pipeline_state.assembled.chunks) if pipeline_state.assembled else 0,
            )

        confidence = pipeline_state.generated.confidence
        if (
            pipeline_state.evaluator is not None
            and pipeline_state.evaluator.get("final_score") is not None
        ):
            confidence = pipeline_state.evaluator["final_score"]

        if cache is not None:
            await cache.put(
                request.question,
                pipeline_state.generated.answer,
                confidence=confidence,
                sources=sources,
            )
        return QueryResponse(
            answer=pipeline_state.generated.answer,
            sources=sources,
            confidence=confidence,
            chunks_used=len(pipeline_state.assembled.chunks) if pipeline_state.assembled else 0,
        )
    finally:
        if cache is not None:
            await cache.close()
