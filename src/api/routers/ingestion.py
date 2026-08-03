"""Routes ingestion — texte et fichier → chunks → embeddings → Qdrant."""

import json

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from src.api.schemas import IngestRequest, IngestResponse
from src.services.ingestion import IngestionService

router = APIRouter(tags=["Ingestion"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest, http_request: Request) -> IngestResponse:
    """Ingestion d'une source (texte) → chunks → embeddings → Qdrant."""
    state = http_request.app.state
    if not hasattr(state, "ingestion_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    service: IngestionService = state.ingestion_service

    result = await service.ingest(
        text=request.text,
        source_type=request.source_type,
        source_id=request.source_id,
        metadata=request.metadata,
        context=request.context,
    )

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
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
    state = http_request.app.state
    if not hasattr(state, "ingestion_service"):
        raise HTTPException(status_code=503, detail="Services not initialized - server starting up")

    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    meta = json.loads(metadata) if metadata else {}
    meta["filename"] = file.filename
    meta["content_type"] = file.content_type

    service: IngestionService = state.ingestion_service

    result = await service.ingest(
        text=text,
        source_type=source_type,
        source_id=None,
        metadata=meta,
        context=None,
    )

    return IngestResponse(
        source_id=result.source_id,
        chunks_created=result.chunks_created,
        chunks_indexed=result.chunks_indexed,
        errors=result.errors,
    )
