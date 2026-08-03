"""Route /embed — embedding dense (nomic-embed-text-v2-moe)."""

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import EmbedRequest, EmbedResponse
from src.core.settings import get_settings
from src.services.ollama import OllamaClientPool

router = APIRouter(tags=["Embedding"])

settings = get_settings()


@router.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest, http_request: Request) -> EmbedResponse:
    """Embedding texte → vecteur dense (nomic-embed-text-v2-moe).

    Note : le sparse BM25 natif Qdrant est calculé à la requête (full-text),
    pas à l'embedding. Le champ `sparse_vectors` est conservé pour
    compatibilité mais renvoie toujours None.
    """
    state = http_request.app.state
    if not hasattr(state, "ollama_pool"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    pool: OllamaClientPool = state.ollama_pool

    # Embedding dense via Ollama M1 (fallback M2)
    dense_embeddings = await pool.embed(request.texts)

    # Sparse vectors BM25 natif Qdrant : calculé à la requête, pas ici
    sparse_vectors = None

    return EmbedResponse(
        embeddings=dense_embeddings,
        sparse_vectors=sparse_vectors,
        model=settings.embedding_model,
        dimensions=len(dense_embeddings[0]) if dense_embeddings else 768,
    )
