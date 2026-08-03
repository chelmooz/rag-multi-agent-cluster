"""Service d'ingestion — chunking, augmentation, embedding batch → Qdrant.

Pipeline offline asynchrone (hors chemin critique requête) :
Source → Chunking → Augmentation → Embedding (Ollama M1) → Qdrant upsert
Le full-text BM256 est assuré par l'index natif Qdrant sur le champ payload "text".
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

import tiktoken

from src.services.ollama import OllamaClientPool
from src.services.vector import VectorService
from src.tools.injection_filter import InjectionRisk, scan

_MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S+")


@dataclass(frozen=True)
class Chunk:
    """Représente un chunk de texte avec métadonnées."""
    id: str
    text: str
    source_id: str
    source_type: str  # "file", "url", "text"
    chunk_index: int
    token_count: int
    metadata: dict[str, Any]
    injection_risk: InjectionRisk


@dataclass(frozen=True)
class IngestionResult:
    """Résultat d'une ingestion."""
    source_id: str
    chunks_created: int
    chunks_indexed: int
    chunks_deleted: int = 0
    errors: list[str] = field(default_factory=list)


class IngestionService:
    """Service d'ingestion complet pour le pipeline RAG."""

    def __init__(
        self,
        ollama_pool: OllamaClientPool | None = None,
        vector_service: VectorService | None = None,
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
        encoding_name: str = "cl100k_base",
    ) -> None:
        self._ollama_pool = ollama_pool
        self._vector_service = vector_service
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._encoding = tiktoken.get_encoding(encoding_name)

    @classmethod
    def from_settings(cls) -> IngestionService:
        """Factory depuis la config centrale."""
        from src.core.settings import get_settings
        from src.services.ollama import OllamaClientPool
        from src.services.vector import VectorService

        s = get_settings()
        return cls(
            ollama_pool=OllamaClientPool(),
            vector_service=VectorService(),
            chunk_size=s.chunk_size,
            chunk_overlap=s.chunk_overlap,
        )

    # ── Chunking ────────────────────────────────────────────────

    def chunk_text(
        self,
        text: str,
        source_id: str,
        source_type: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Découpe un texte en chunks avec overlap (tiktoken).

        Les sources markdown (``md``/``markdown`` ou texte ressemblant à du
        markdown) passent par le chunker structurel : frontières de sections,
        tableaux/fences entiers, chemin de section en métadonnées.
        """
        if not text or not text.strip():
            return []

        if source_type in ("md", "markdown") or _looks_like_markdown(text):
            return self._chunk_markdown(text, source_id, source_type, base_metadata)

        tokens = self._encoding.encode(text)
        if not tokens:
            return []

        chunks: list[Chunk] = []
        start = 0
        chunk_index = 0

        while start < len(tokens):
            end = min(start + self._chunk_size, len(tokens))
            chunk_text = self._encoding.decode(tokens[start:end])

            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "chunk_index": chunk_index,
                "token_count": len(tokens[start:end]),
            }
            if base_metadata:
                metadata.update(base_metadata)

            chunks.append(
                self._make_chunk(chunk_text, source_id, source_type, chunk_index, metadata)
            )

            chunk_index += 1
            start += self._chunk_size - self._chunk_overlap

        return chunks

    def _chunk_markdown(
        self,
        text: str,
        source_id: str,
        source_type: str,
        base_metadata: dict[str, Any] | None,
    ) -> list[Chunk]:
        """Découpe structurelle markdown → Chunk (chemin de section en métadonnées)."""
        from src.services.structural_chunker import MarkdownChunker

        chunker = MarkdownChunker(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        chunks: list[Chunk] = []
        for chunk_index, sc in enumerate(chunker.chunk(text)):
            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "chunk_index": chunk_index,
                "token_count": sc.token_count,
            }
            if sc.heading_path:
                metadata["section_title"] = sc.heading_path[-1]
                metadata["heading_path"] = sc.heading_path
            if sc.heading_level:
                metadata["heading_level"] = sc.heading_level
            if base_metadata:
                metadata.update(base_metadata)
            chunks.append(
                self._make_chunk(sc.text, source_id, source_type, chunk_index, metadata)
            )
        return chunks

    def _make_chunk(
        self,
        chunk_text: str,
        source_id: str,
        source_type: str,
        chunk_index: int,
        metadata: dict[str, Any],
    ) -> Chunk:
        """Construit un Chunk : id déterministe + scan anti-injection."""
        injection_risk = scan(chunk_text)

        chunk_id = hashlib.sha256(
            f"{source_id}:{chunk_index}:{chunk_text[:100]}".encode()
        ).hexdigest()[:16]

        return Chunk(
            id=chunk_id,
            text=chunk_text,
            source_id=source_id,
            source_type=source_type,
            chunk_index=chunk_index,
            token_count=metadata.get("token_count", 0),
            metadata=metadata,
            injection_risk=injection_risk,
        )

    # ── Augmentation ────────────────────────────────────────────

    def augment_chunks(self, chunks: list[Chunk], context: str | None = None) -> list[Chunk]:
        """Ajoute du contexte aux chunks (ex: titre doc, section, résumé)."""
        if not context:
            return chunks

        augmented = []
        for chunk in chunks:
            # Préfixer avec le contexte pour l'embedding
            augmented_text = f"[Contexte: {context}]\n{chunk.text}"
            new_metadata = dict(chunk.metadata)
            new_metadata["context"] = context

            augmented.append(
                Chunk(
                    id=chunk.id,
                    text=augmented_text,
                    source_id=chunk.source_id,
                    source_type=chunk.source_type,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                    metadata=new_metadata,
                    injection_risk=chunk.injection_risk,
                )
            )
        return augmented

    # ── Embedding + Indexation ──────────────────────────────────

    async def embed_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Génère les embeddings pour une liste de chunks via Ollama M1 (CPU)."""
        if not chunks:
            return chunks

        if self._ollama_pool is None:
            raise RuntimeError("OllamaClientPool non initialisé")

        texts = [c.text for c in chunks]
        embeddings = await self._ollama_pool.embed(texts)

        if len(embeddings) != len(chunks):
            raise ValueError(f"Nombre d'embeddings ({len(embeddings)}) != chunks ({len(chunks)})")

        embedded_chunks = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            new_metadata = dict(chunk.metadata)
            new_metadata["embedding"] = embedding
            new_metadata["injection_risk"] = chunk.injection_risk.risk.value
            new_metadata["injection_confidence"] = chunk.injection_risk.confidence

            embedded_chunks.append(
                Chunk(
                    id=chunk.id,
                    text=chunk.text,
                    source_id=chunk.source_id,
                    source_type=chunk.source_type,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                    metadata=new_metadata,
                    injection_risk=chunk.injection_risk,
                )
            )
        return embedded_chunks

    async def index_chunks(self, chunks: list[Chunk]) -> int:
        """Indexe les chunks dans Qdrant via VectorService."""
        if not chunks:
            return 0

        if self._vector_service is None:
            raise RuntimeError("VectorService non initialisé")

        points = []
        for chunk in chunks:
            embedding = chunk.metadata.get("embedding")
            if not embedding:
                continue

            points.append({
                "id": chunk.id,
                "vector": embedding,
                "payload": {
                    "text": chunk.text,
                    "source_id": chunk.source_id,
                    "source_type": chunk.source_type,
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    "injection_risk": chunk.injection_risk.risk.value,
                    "injection_confidence": chunk.injection_risk.confidence,
                    **{k: v for k, v in chunk.metadata.items() if k not in ("embedding",)},
                },
            })

        if not points:
            return 0

        return await self._vector_service.upsert_points(points)

    # ── Pipeline complet ────────────────────────────────────────

    async def ingest(
        self,
        text: str,
        source_type: str = "text",
        source_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        context: str | None = None,
        replace: bool = True,
    ) -> IngestionResult:
        """Pipeline complet d'ingestion : (résuppression) → chunk → augment → embed → index.

        ``replace=True`` : les chunks d'une source déjà ingérée sont supprimés
        avant l'upsert (ré-ingestion = mise à jour, pas de doublons).
        """
        if source_id is None:
            source_id = hashlib.sha256(text.encode()).hexdigest()[:16]

        errors: list[str] = []
        chunks_deleted = 0

        # 0. Remplacement : purge des chunks existants de la source
        if replace and self._vector_service is not None:
            try:
                chunks_deleted = await self._vector_service.delete_source(source_id)
            except Exception as e:
                errors.append(f"delete_source: {type(e).__name__}: {e}")

        try:
            # 1. Chunking
            chunks = self.chunk_text(text, source_id, source_type, metadata)
            if not chunks:
                return IngestionResult(
                    source_id=source_id,
                    chunks_created=0,
                    chunks_indexed=0,
                    chunks_deleted=chunks_deleted,
                    errors=["Aucun chunk généré (texte vide ?)"],
                )

            # 2. Augmentation
            chunks = self.augment_chunks(chunks, context)

            # 3. Embedding
            chunks = await self.embed_chunks(chunks)

            # 4. Indexation Qdrant
            indexed = await self.index_chunks(chunks)

            return IngestionResult(
                source_id=source_id,
                chunks_created=len(chunks),
                chunks_indexed=indexed,
                chunks_deleted=chunks_deleted,
                errors=errors,
            )

        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
            return IngestionResult(
                source_id=source_id,
                chunks_created=0,
                chunks_indexed=0,
                chunks_deleted=chunks_deleted,
                errors=errors,
            )

    async def delete_source(self, source_id: str) -> int:
        """Supprime tous les chunks d'une source (délégué à VectorService)."""
        if self._vector_service is None:
            raise RuntimeError("VectorService non initialisé")
        return await self._vector_service.delete_source(source_id)

    async def list_source_chunks(
        self, source_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Liste les chunks d'une source (pour l'endpoint GET)."""
        if self._vector_service is None:
            raise RuntimeError("VectorService non initialisé")
        return await self._vector_service.scroll_source_chunks(
            source_id, limit=limit
        )

    async def close(self) -> None:
        if self._ollama_pool:
            await self._ollama_pool.close()
        if self._vector_service:
            await self._vector_service.close()

    async def __aenter__(self) -> IngestionService:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()


def _looks_like_markdown(text: str) -> bool:
    """Détection heuristique d'un document markdown sur les 15 premières lignes."""
    lines = [ln.strip() for ln in text.splitlines()[:15] if ln.strip()]
    if not lines:
        return False
    return any(_MARKDOWN_HEADING_RE.match(ln) for ln in lines) or any(
        "```" in ln or "|" in ln for ln in lines[:5]
    )
