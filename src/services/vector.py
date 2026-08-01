"""Service vectoriel (Qdrant) — hybrid search natif dense + sparse (BM25).

Aligné sur le choix d'architecture : Qdrant (pas Chroma) pour le search hybride natif.
"""
from __future__ import annotations

from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from src.core.settings import get_settings


class VectorServiceError(Exception):
    """Erreur générique du service vectoriel."""


class VectorService:
    """Client Qdrant async avec support hybrid search (dense + sparse).

    Collections :
    - rag-wiki : pages du vault Obsidian (embeddings nomic-embed-text-v2-moe 768d)
    """

    def __init__(self) -> None:
        s = get_settings()

        self._client = AsyncQdrantClient(
            url=str(s.qdrant_url),
            api_key=s.qdrant_api_key,
            prefer_grpc=True,
        )
        self.collection = s.qdrant_collection
        self._vector_size = 768  # nomic-embed-text-v2-moe dimension

    # ── Lifecycle ────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> VectorService:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── Collection management ────────────────────────────────────

    async def create_collection(self, vector_size: int = 768) -> None:
        """Crée la collection Qdrant avec config hybrid search (dense + sparse BM25)."""
        self._vector_size = vector_size

        # Vérifier si la collection existe déjà
        try:
            await self._client.get_collection(self.collection)
        except UnexpectedResponse:
            pass  # N'existe pas, on la crée
        else:
            return  # Déjà existante

        # Configuration hybrid search : dense vector + sparse BM25
        await self._client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
                on_disk=True,  # Économise RAM pour gros index
            ),
            sparse_vectors_config={
                "bm25": models.SparseVectorParams(
                    index=models.SparseIndexParams(
                        on_disk=True,
                    )
                )
            },
            optimizers_config=models.OptimizersConfigDiff(
                default_segment_number=2,
                indexing_threshold=0,  # Index immédiat pour dev
            ),
        )

    # ── Core operations ──────────────────────────────────────────

    async def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Indexation batch de points dans Qdrant.

        Args:
            points: Liste de dicts avec clés:
                - id: str | int (UUID ou hash)
                - vector: list[float] (dense 768d)
                - sparse_vector: dict | models.SparseVector (BM25 sparse)
                - payload: dict (métadonnées : text, source, type, etc.)

        Returns:
            Nombre de points insérés/mis à jour.
        """
        if not points:
            return 0

        qdrant_points = []
        for p in points:
            sparse_vec = p.get("sparse_vector")
            if isinstance(sparse_vec, dict):
                # Convertir dict {index: value} -> SparseVector
                sparse_vec = models.SparseVector(
                    indices=list(sparse_vec.keys()),
                    values=list(sparse_vec.values()),
                )

            # Construire le dict vector pour named vectors (dense + sparse)
            vector_dict: dict[str, Any] = {"": p["vector"]}  # "" = vecteur dense par défaut
            if sparse_vec:
                vector_dict["bm25"] = sparse_vec

            qdrant_points.append(
                models.PointStruct(
                    id=p["id"],
                    vector=vector_dict,
                    payload=p.get("payload", {}),
                )
            )

        result = await self._client.upsert(
            collection_name=self.collection,
            points=qdrant_points,
            wait=True,
        )
        if result and result.operation_id is not None:
            return result.operation_id
        return len(qdrant_points)

    async def hybrid_search(
        self,
        query_vector: list[float],
        query_sparse: dict[int, float] | models.SparseVector | None,
        top_k: int = 20,
        score_threshold: float | None = None,
        filter_: models.Filter | None = None,
    ) -> list[dict[str, Any]]:
        """Recherche hybride : vecteur dense (sémantique) + sparse (BM25 lexical).

        Utilise la fusion RRF (Reciprocal Rank Fusion) native de Qdrant.

        Args:
            query_vector: Embedding dense de la requête (768d)
            query_sparse: Vecteur sparse BM25 de la requête (dict index->value ou SparseVector)
            top_k: Nombre de résultats à retourner
            score_threshold: Seuil de score minimum (optionnel)
            filter_: Filtre Qdrant (ex: par type, source, etc.)

        Returns:
            Liste de résultats avec payload, score, id.
        """
        # Préparer le vecteur sparse
        sparse_vector: models.SparseVector | None = None
        if query_sparse:
            if isinstance(query_sparse, dict):
                sparse_vector = models.SparseVector(
                    indices=list(query_sparse.keys()),
                    values=list(query_sparse.values()),
                )
            else:
                sparse_vector = query_sparse

        # Recherche hybride via Query API (Qdrant 1.9+)
        prefetch = []
        # Dense vector search
        prefetch.append(
            models.Prefetch(
                query=query_vector,
                using="",  # vecteur dense par défaut
                limit=top_k * 2,  # Large candidate set pour RRF
            )
        )
        # Sparse BM25 search
        if sparse_vector:
            prefetch.append(
                models.Prefetch(
                    query=sparse_vector,
                    using="bm25",
                    limit=top_k * 2,
                )
            )

        # Fusion RRF
        results = await self._client.query_points(
            collection_name=self.collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=filter_,
            with_payload=True,
            with_vectors=False,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results.points
        ]

    # ── Health & Backup ──────────────────────────────────────────

    async def health(self) -> bool:
        """Vérification disponibilité Qdrant."""
        try:
            return await self._client.collection_exists(self.collection)
        except Exception:
            return False

    async def snapshot_create(self) -> str:
        """Snapshot atomique Qdrant pour backup (cron quotidien).

        Returns:
            Nom du snapshot créé (utilisé comme chemin relatif).
        """
        snapshot = await self._client.create_snapshot(self.collection)
        if snapshot is None:
            raise VectorServiceError("Échec création snapshot Qdrant")
        return snapshot.name
