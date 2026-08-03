"""Route /embed — embedding dense (nomic-embed-text-v2-moe) + sparse (BM25)."""

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import EmbedRequest, EmbedResponse
from src.core.settings import get_settings
from src.services.lexical import LexicalSearch
from src.services.ollama import OllamaClientPool

router = APIRouter(tags=["Embedding"])

settings = get_settings()


@router.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest, http_request: Request) -> EmbedResponse:
    """Embedding texte → vecteur dense (nomic-embed-text-v2-moe) + sparse (BM25)."""
    state = http_request.app.state
    if not hasattr(state, "ollama_pool") or not hasattr(state, "lexical_search"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    pool: OllamaClientPool = state.ollama_pool
    lexical: LexicalSearch = state.lexical_search

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
