"""Routes ingestion — texte et fichier → chunks → embeddings → Qdrant + cycle de vie."""

import json

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from src.api.schemas import (
    DeleteSourceResponse,
    IngestRequest,
    IngestResponse,
    SourceChunk,
    SourceChunksResponse,
)
from src.services.ingestion import IngestionService

router = APIRouter(tags=["Ingestion"])


def _get_service(http_request: Request) -> IngestionService:
    state = http_request.app.state
    if not hasattr(state, "ingestion_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")
    return state.ingestion_service  # type: ignore[no-any-return]


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest, http_request: Request) -> IngestResponse:
    """Ingestion d'une source (texte) → chunks → embeddings → Qdrant."""
    service = _get_service(http_request)

    result = await service.ingest(
        text=request.text,
        source_type=request.source_type,
        source_id=request.source_id,
        metadata=request.metadata,
        context=request.context,
        replace=True,
    )

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
        chunks_deleted=result.chunks_deleted,
        errors=result.errors,
    )


@router.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    http_request: Request,
    file: UploadFile,
    source_type: str = Form(default="file"),
    metadata: str = Form(default="{}"),
) -> IngestResponse:
    """Ingestion d'un fichier uploadé."""
    service = _get_service(http_request)

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    meta = json.loads(metadata) if metadata else {}
    meta["filename"] = file.filename
    meta["content_type"] = file.content_type

    result = await service.ingest(
        text=text,
        source_type=source_type,
        source_id=None,
        metadata=meta,
        context=None,
        replace=True,
    )

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
        chunks_deleted=result.chunks_deleted,
        errors=result.errors,
    )


@router.delete("/sources/{source_id}", response_model=DeleteSourceResponse)
async def delete_source(source_id: str, http_request: Request) -> DeleteSourceResponse:
    """Supprime tous les chunks indexés d'une source."""
    service = _get_service(http_request)
    try:
        deleted = await service.delete_source(source_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec suppression source: {e}") from e
    return DeleteSourceResponse(source_id=source_id, chunks_deleted=deleted)


@router.get("/sources/{source_id}/chunks", response_model=SourceChunksResponse)
async def list_source_chunks(
    source_id: str, http_request: Request, limit: int = 100
) -> SourceChunksResponse:
    """Liste les chunks d'une source."""
    service = _get_service(http_request)
    try:
        chunks = await service.list_source_chunks(source_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec listing source: {e}") from e
    return SourceChunksResponse(
        source_id=source_id,
        chunks=[SourceChunk(id=c["id"], payload=c["payload"]) for c in chunks],
        count=len(chunks),
    )
