"""Point d'entrée API du cluster RAG multi-agents.

STATUT : squelette non implémenté — voir ROADMAP.md.
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="rag-multi-agent-cluster")


class QueryRequest(BaseModel):
    question: str
    context: str | None = None


class QueryResponse(BaseModel):
    # TODO: aligner sur le format compatible OpenAI décrit dans le README
    # une fois le pipeline agents/RAG implémenté.
    answer: str


@app.post("/api/v1/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    # TODO: brancher le pipeline réel (planificateur -> recherche hybride
    # -> reranking -> génération -> Juge/Avocat du diable -> évaluateur).
    raise NotImplementedError("Pipeline RAG multi-agents pas encore implémenté")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
