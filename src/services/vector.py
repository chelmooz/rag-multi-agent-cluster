"""Service vectoriel (Qdrant) — hybrid search natif dense + full-text BM25.

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
    """Client Qdrant async avec support hybrid search (dense + full-text BM25).

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
        """Crée la collection Qdrant avec config hybrid search (dense + full-text BM25).

        Le full-text index est créé sur le champ payload "text" pour un vrai BM25
        avec IDF calculé nativement par Qdrant à la requête.
        """
        self._vector_size = vector_size

        # Vérifier si la collection existe déjà
        try:
            await self._client.get_collection(self.collection)
        except UnexpectedResponse:
            pass  # N'existe pas, on la crée
        else:
            return  # Déjà existante

        # Configuration hybrid search : dense vector + full-text index sur payload.text
        await self._client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
                on_disk=True,  # Économise RAM pour gros index
            ),
            # Full-text index pour BM25 natif (remplace l'ancien sparse vector "bm25")
            # Le champ payload "text" doit exister sur les points
            optimizers_config=models.OptimizersConfigDiff(
                default_segment_number=2,
                indexing_threshold=0,  # Index immédiat pour dev
            ),
        )

        # Créer l'index full-text sur le champ "text" du payload
        await self._client.create_payload_index(
            collection_name=self.collection,
            field_name="text",
            field_schema=models.TextIndexParams(
                type="text",
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
                min_token_len=2,
                max_token_len=20,
            ),
        )

    # ── Core operations ──────────────────────────────────────────

    async def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Indexation batch de points dans Qdrant.

        Args:
            points: Liste de dicts avec clés:
                - id: str | int (UUID ou hash)
                - vector: list[float] (dense 768d)
                - payload: dict (métadonnées : text, source, type, etc.)

        Returns:
            Nombre de points insérés/mis à jour.
        """
        if not points:
            return 0

        qdrant_points = []
        for p in points:
            # Seul le vecteur dense est stocké ; le full-text utilise le payload "text"
            qdrant_points.append(
                models.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
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
        query_text: str | None = None,
        top_k: int = 20,
        score_threshold: float | None = None,
        filter_: models.Filter | None = None,
    ) -> list[dict[str, Any]]:
        """Recherche hybride : vecteur dense (sémantique) + full-text BM25 (lexical).

        Utilise la fusion RRF (Reciprocal Rank Fusion) native de Qdrant.

        Args:
            query_vector: Embedding dense de la requête (768d)
            query_text: Texte brut pour le full-text search BM25 (optionnel)
            top_k: Nombre de résultats à retourner
            score_threshold: Seuil de score minimum (optionnel)
            filter_: Filtre Qdrant (ex: par type, source, etc.)

        Returns:
            Liste de résultats avec payload, score, id.
        """
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
        # Full-text BM25 search (Qdrant accepte une chaîne brute comme requête full-text)
        if query_text:
            prefetch.append(
                models.Prefetch(
                    query=query_text,
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

    # ── Lifecycle des sources ────────────────────────────────────

    async def delete_source(self, source_id: str) -> int:
        """Supprime tous les chunks d'une source donnée.

        Args:
            source_id: Identifiant de la source à supprimer

        Returns:
            Nombre de points supprimés.
        """
        # Scroll pour récupérer tous les IDs des points de cette source
        ids_to_delete: list[models.ExtendedPointId] = []
        offset: models.ExtendedPointId | None = None
        while True:
            result = await self._client.scroll(
                collection_name=self.collection,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_id",
                            match=models.MatchValue(value=source_id),
                        )
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            points, next_offset = result
            ids_to_delete.extend(p.id for p in points)
            if next_offset is None:
                break
            offset = next_offset

        if not ids_to_delete:
            return 0

        # Suppression par IDs
        await self._client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=ids_to_delete),
            wait=True,
        )
        return len(ids_to_delete)

    async def scroll_source_chunks(
        self, source_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Liste les chunks d'une source (payloads sans vecteurs).

        Args:
            source_id: Identifiant de la source
            limit: Nombre maximum de chunks à retourner

        Returns:
            Liste de dicts {id, payload} des chunks de la source.
        """
        result = await self._client.scroll(
            collection_name=self.collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchValue(value=source_id),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        points, _ = result
        return [{"id": p.id, "payload": p.payload} for p in points]

    # ── Health & Backup ──────────────────────────────────────────

    async def get_collection_stats(self) -> dict[str, int]:
        """Statistiques collection : nombre de points (pour estimation RAM Qdrant)."""
        try:
            info = await self._client.get_collection(self.collection)
        except Exception:
            return {"points_count": 0}
        return {"points_count": int(info.points_count or 0)}

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
