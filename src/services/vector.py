"""Service vectoriel (Qdrant) — hybrid search natif dense + sparse (BM25).

Aligné sur le choix d'architecture : Qdrant (pas Chroma) pour le search hybride natif.
"""
from qdrant_client import QdrantClient


class VectorService:
    """Client Qdrant avec support hybrid search (dense + sparse).

    Collections :
    - rag-wiki : pages du vault Obsidian (embeddings nomic-embed-text-v2-moe 768d)
    """

    def __init__(self):
        from src.core.settings import settings

        self.client = QdrantClient(
            url=str(settings.qdrant_url),
            api_key=settings.qdrant_api_key,
            prefer_grpc=True,
        )
        self.collection = settings.qdrant_collection

    async def hybrid_search(self, query: str, top_k: int = 20) -> list[dict]:
        """Recherche hybride : vecteur dense (semantique) + sparse (BM25 lexical)."""
        raise NotImplementedError

    async def upsert_points(self, points: list[dict]) -> int:
        """Indexation batch de points dans Qdrant."""
        raise NotImplementedError

    async def create_collection(self, vector_size: int = 768) -> None:
        """Crée la collection Qdrant avec config hybrid search."""
        raise NotImplementedError

    async def health(self) -> bool:
        """Vérification disponibilité Qdrant."""
        try:
            return self.client.collection_exists(self.collection)
        except Exception:
            return False

    async def snapshot_create(self) -> str:
        """Snapshot atomique Qdrant pour backup (cron quotidien)."""
        raise NotImplementedError
