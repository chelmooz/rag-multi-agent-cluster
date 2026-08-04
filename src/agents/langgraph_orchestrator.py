"""LangGraph Orchestrator — graphe d'état explicite du pipeline multi-agents.

Workflow :
1. Planifier (intention + stratégie)
2. Réécrire la requête (conversationnel)
3. Recherche hybride (BM25 + vectoriel) + rerank
4. Assembler le contexte (chunks + savoir interne)
5. Générer réponse (BC250)
6. Évaluer (Judge → Avocat → Évaluateur) — si `evaluation_enabled` (D12)
7. Mettre à jour le wiki (pages, index, log)
8. Retourner la réponse utilisateur

Le graphe est construit par ``build_graph`` et exécuté par ``run_pipeline``
(mock-first : services injectés, aucun appel réseau en test).
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, cast

from langgraph.graph import END, StateGraph
from redis.asyncio import Redis

from src.agents.advocate import AdvocateAgent
from src.agents.context_assembler import AssembledContext, ContextAssembler
from src.agents.evaluator import EvaluatorAgent
from src.agents.generator import GeneratorAgent, GeneratorOutput
from src.agents.judge import JudgeAgent
from src.agents.planner import PlannerAgent, PlannerOutput, default_plan
from src.agents.rewriter import RewriterAgent
from src.agents.wiki_agent import WikiAgent
from src.services.chat_memory import ChatMemory
from src.services.lexical import LexicalSearch
from src.services.ollama import OllamaClientPool
from src.services.reranker import RerankerService
from src.services.vector import VectorService

logger = logging.getLogger(__name__)

_QUEUE_NAME = "rag:pipeline:queue"
_RESULTS_NAME = "rag:pipeline:results"


@dataclass
class PipelineState:
    """État partagé entre les nœuds du graphe."""

    query: str
    conversation_history: list[dict] = field(default_factory=list)
    evaluation_enabled: bool = False
    top_k: int = 8
    use_reranker: bool = True
    score_threshold: float | None = None

    # Sorties des nœuds
    plan: PlannerOutput | None = None
    rewritten_query: str = ""
    search_results: list[dict[str, Any]] = field(default_factory=list)
    assembled: AssembledContext | None = None
    generated: GeneratorOutput | None = None
    judge: dict[str, Any] | None = None
    advocate: dict[str, Any] | None = None
    evaluator: dict[str, Any] | None = None
    wiki_note: str | None = None


class PipelineServices:
    """Conteneur des services injectables du pipeline (mock-first)."""

    def __init__(
        self,
        pool: OllamaClientPool | None = None,
        vector: VectorService | None = None,
        lexical: LexicalSearch | None = None,
        reranker: RerankerService | None = None,
        wiki: WikiAgent | None = None,
        planner: PlannerAgent | None = None,
        rewriter: RewriterAgent | None = None,
        assembler: ContextAssembler | None = None,
        generator: GeneratorAgent | None = None,
        judge: JudgeAgent | None = None,
        advocate: AdvocateAgent | None = None,
        evaluator: EvaluatorAgent | None = None,
    ) -> None:
        self.pool = pool
        self.vector = vector
        self.lexical = lexical
        self.reranker = reranker
        self.wiki = wiki
        self.planner = planner
        self.rewriter = rewriter
        self.assembler = assembler
        self.generator = generator
        self.judge = judge
        self.advocate = advocate
        self.evaluator = evaluator


# ── Nœuds du graphe ────────────────────────────────────────────────

async def node_plan(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.planner is None:
        return {"plan": default_plan(state.query)}
    context = ChatMemory(state.conversation_history).get_context_string()
    plan = await services.planner.plan(state.query, conversation_context=context)
    return {"plan": plan}


async def node_rewrite(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.rewriter is None:
        return {"rewritten_query": state.query}
    history = ChatMemory(state.conversation_history).get_window()
    out = await services.rewriter.rewrite(state.query, history)
    return {"rewritten_query": out.rewritten_query or state.query}


async def node_retrieve(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.vector is None or services.lexical is None or services.pool is None:
        return {"search_results": []}

    query = state.rewritten_query or state.query
    embeddings = await services.pool.embed([query])
    if not embeddings:
        return {"search_results": []}
    query_dense = embeddings[0]
    query_text = query
    top_k = state.top_k if state.top_k else (state.plan.rerank_top_k if state.plan else 8)
    use_reranker = state.use_reranker and services.reranker is not None

    results = await services.vector.hybrid_search(
        query_vector=query_dense,
        query_text=query_text,
        top_k=top_k * 3 if use_reranker else top_k,
        score_threshold=state.score_threshold,
    )
    reranker = services.reranker
    if use_reranker and reranker is not None and len(results) > 1:
        docs_texts = [r["payload"].get("text", "") for r in results]
        reranked = await reranker.rerank(query, docs_texts, top_k=top_k)
        results = [
            {**results[rr.index], "rerank_score": rr.score} for rr in reranked
        ]
    return {"search_results": results[:top_k]}


async def node_assemble(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    assembler = services.assembler or ContextAssembler()
    assembled = assembler.assemble(state.query, state.search_results)
    return {"assembled": assembled}


async def node_generate(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.generator is None:
        return {"generated": None}
    chunks = [
        {
            "source_id": c.source_id,
            "text": c.text,
            "score": c.score,
        }
        for c in (state.assembled.chunks if state.assembled else [])
    ]
    generated = await services.generator.generate(
        state.query, chunks,
        conversation_history=ChatMemory(state.conversation_history).get_window(),
    )
    return {"generated": generated}


async def node_judge(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.judge is None or state.generated is None:
        return {"judge": None}
    chunks = [
        {"source_id": c.source_id, "text": c.text}
        for c in (state.assembled.chunks if state.assembled else [])
    ]
    out = await services.judge.evaluate(state.query, state.generated.answer, chunks)
    return {"judge": out.model_dump()}


async def node_advocate(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.advocate is None or state.generated is None:
        return {"advocate": None}
    chunks = [
        {"source_id": c.source_id, "text": c.text}
        for c in (state.assembled.chunks if state.assembled else [])
    ]
    out = await services.advocate.challenge(
        state.query, state.generated.answer, chunks, state.judge or {}
    )
    return {"advocate": out.model_dump()}


async def node_evaluate(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.evaluator is None or state.generated is None:
        return {"evaluator": None}
    relay = {
        "query": state.query,
        "response": state.generated.answer,
        "judge": state.judge or {},
        "advocate": state.advocate or {},
    }
    out = await services.evaluator.synthesize(relay)
    return {"evaluator": out.model_dump()}


async def node_wiki(state: PipelineState, services: PipelineServices) -> dict[str, Any]:
    if services.wiki is None:
        return {}
    note: str | None = None
    if state.generated is not None:
        page = f"synthesis/{_slug(state.query)}.md"
        await services.wiki.write_page(
            page,
            state.generated.answer,
            {"type": "synthesis", "title": state.query[:60]},
        )
        note = page
    if state.evaluator is not None and state.evaluator.get("decision") == "publish":
        await services.wiki.update_index()
        note = note or "index updated"
    await services.wiki.append_log({
        "query": state.query,
        "agent": "generator",
        "decision": (
            "publish"
            if state.evaluator and state.evaluator.get("decision") == "publish"
            else "generated"
        ),
        "final_score": state.evaluator.get("score") if state.evaluator else None,
    })
    return {"wiki_note": note} if note else {}


def _slug(text: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in " _-" else " " for c in text.lower())
    return "-".join(cleaned.split())[:60]


# ── Construction du graphe ─────────────────────────────────────────

def build_graph(services: PipelineServices | None = None) -> StateGraph:
    """Construit le graphe LangGraph du pipeline (B7)."""
    services = services or PipelineServices()
    sg = StateGraph(PipelineState)

    async def _plan(state: PipelineState) -> dict[str, Any]:
        return await node_plan(state, services)

    async def _rewrite(state: PipelineState) -> dict[str, Any]:
        return await node_rewrite(state, services)

    async def _retrieve(state: PipelineState) -> dict[str, Any]:
        return await node_retrieve(state, services)

    async def _assemble(state: PipelineState) -> dict[str, Any]:
        return await node_assemble(state, services)

    async def _generate(state: PipelineState) -> dict[str, Any]:
        return await node_generate(state, services)

    async def _judge(state: PipelineState) -> dict[str, Any]:
        return await node_judge(state, services)

    async def _advocate(state: PipelineState) -> dict[str, Any]:
        return await node_advocate(state, services)

    async def _evaluate(state: PipelineState) -> dict[str, Any]:
        return await node_evaluate(state, services)

    async def _wiki(state: PipelineState) -> dict[str, Any]:
        return await node_wiki(state, services)

    sg.add_node("plan", _plan)
    sg.add_node("rewrite", _rewrite)
    sg.add_node("retrieve", _retrieve)
    sg.add_node("assemble", _assemble)
    sg.add_node("generate", _generate)
    sg.add_node("judge", _judge)
    sg.add_node("advocate", _advocate)
    sg.add_node("evaluate", _evaluate)
    sg.add_node("wiki", _wiki)

    sg.set_entry_point("plan")
    sg.add_edge("plan", "rewrite")
    sg.add_edge("rewrite", "retrieve")
    sg.add_edge("retrieve", "assemble")
    sg.add_edge("assemble", "generate")
    sg.add_conditional_edges(
        "generate",
        lambda s: "eval" if s.evaluation_enabled else "wiki",
        {"eval": "judge", "wiki": "wiki"},
    )
    sg.add_edge("judge", "advocate")
    sg.add_edge("advocate", "evaluate")
    sg.add_edge("evaluate", "wiki")
    sg.add_edge("wiki", END)

    return sg


async def run_pipeline(
    query: str,
    services: PipelineServices,
    conversation_history: list[dict] | None = None,
    evaluation_enabled: bool = False,
    top_k: int = 8,
    use_reranker: bool = True,
    score_threshold: float | None = None,
) -> PipelineState:
    """Exécute le pipeline complet (B7) et retourne l'état final.

    ``evaluation_enabled`` active la boucle Judge → Avocat → Évaluateur
    (D12 : défaut OFF, 1 itération max).
    """
    graph = build_graph(services)
    app = graph.compile()
    state = PipelineState(
        query=query,
        conversation_history=list(conversation_history or []),
        evaluation_enabled=evaluation_enabled,
        top_k=top_k,
        use_reranker=use_reranker,
        score_threshold=score_threshold,
    )
    result = await app.ainvoke(state)
    if isinstance(result, PipelineState):
        return result
    if isinstance(result, dict):
        fields = PipelineState.__dataclass_fields__
        return PipelineState(**{k: v for k, v in result.items() if k in fields})
    return state


def build_pipeline_services() -> PipelineServices:
    """Construit les services réels du pipeline (worker Docker, hors API).

    Miroir de ``src.api.routers.rag.query`` — évite de dépendre du state
    FastAPI quand le conteneur tourne comme worker autonome.
    """
    pool = OllamaClientPool()
    return PipelineServices(
        pool=pool,
        vector=VectorService(),
        lexical=LexicalSearch(),
        reranker=RerankerService(ollama_pool=pool),
        wiki=WikiAgent(),
        planner=PlannerAgent(pool),
        rewriter=RewriterAgent(pool),
        generator=GeneratorAgent(pool),
        judge=JudgeAgent(pool),
        advocate=AdvocateAgent(pool),
        evaluator=EvaluatorAgent(pool),
    )


def _job_result(state: PipelineState, job_id: str | None) -> dict[str, Any]:
    """Réduit un état final en payload JSON publiable (résultat du worker)."""
    sources = [
        {
            "source_id": r.get("payload", {}).get("source_id", "doc"),
            "score": r.get("rerank_score", r.get("score", 0.0)),
        }
        for r in state.search_results
    ]
    return {
        "job_id": job_id,
        "query": state.query,
        "answer": state.generated.answer if state.generated else None,
        "sources": sources,
        "wiki_note": state.wiki_note,
    }


async def process_job(job: dict[str, Any], services: PipelineServices) -> dict[str, Any]:
    """Exécute un job de la file Redis → retourne le résultat du pipeline."""
    state = await run_pipeline(
        query=str(job.get("query", "")),
        services=services,
        conversation_history=job.get("conversation_history"),
        evaluation_enabled=bool(job.get("evaluation_enabled", False)),
        top_k=int(job.get("top_k", 8)),
        use_reranker=bool(job.get("use_reranker", True)),
        score_threshold=job.get("score_threshold"),
    )
    return _job_result(state, job.get("job_id"))


async def run_worker(redis_url: str) -> None:
    """Consommateur de la file ``rag:pipeline:queue`` (boucle long-running).

    Ni stub, ni exit immédiat : le conteneur reste vivant tant que la file
    est consommée — résout le crash-loop C1 de la ROADMAP.
    """
    services = build_pipeline_services()
    client = Redis.from_url(redis_url)
    logger.info("Worker orchestrateur démarré (queue=%s)", _QUEUE_NAME)
    try:
        while True:
            item = await cast(Awaitable[list[str] | None], client.brpop(_QUEUE_NAME, timeout=5))
            if item is None:
                continue
            _queue, raw = item
            try:
                job = json.loads(raw)
                result = await process_job(job, services)
                result["ok"] = True
            except Exception as exc:
                logger.exception("Job en échec")
                result = {"ok": False, "error": str(exc), "job_id": None}
            payload = json.dumps(result, ensure_ascii=False)
            await cast(Awaitable[int], client.lpush(_RESULTS_NAME, payload))
    finally:
        await client.aclose()


def main() -> None:
    """Point d'entrée pour le conteneur Docker langgraph-orchestrator.

    Consomme la file Redis des pipelines : service long-running idempotent
    (fin du crash-loop C1).
    """
    from src.core.settings import get_settings

    try:
        asyncio.run(run_worker(get_settings().redis.url))
    except KeyboardInterrupt:
        logger.info("Worker orchestrateur arrêté (signal).")


if __name__ == "__main__":
    main()
