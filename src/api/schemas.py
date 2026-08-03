"""Schémas Pydantic de l'API (modèles de requête/réponse)."""

from typing import Any

from pydantic import BaseModel, Field


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
    environment: str = "development"


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None


class OkfValidateRequest(BaseModel):
    path: str = Field(..., min_length=1)
