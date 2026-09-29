"""Document management endpoints.

Read operations are public so employees can browse the knowledge base. Write
operations (upload / delete / re-index) require the configured bearer token when
``API_AUTH_TOKEN`` is set, and are disabled entirely in production if no token is
configured (``AUTH_REQUIRED``).

Indexing runs as a FastAPI background task, so the upload response returns
immediately with ``status="pending"`` and the client polls the document resource
for the real ``processing → ready | failed`` transition.
"""

from __future__ import annotations

import asyncio

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.security import require_auth, upload_rate_limit_dependency
from app.database.session import get_db
from app.schemas import (
    DocumentChunkOut,
    DocumentDetail,
    DocumentListResponse,
    DocumentOut,
    ReindexResponse,
    UploadResponse,
)
from app.services.document_service import document_service

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

VALID_STATUSES = ("pending", "processing", "ready", "failed")


def _run_indexing(document_id: str) -> None:
    """Background task: extract -> chunk -> embed -> index, using its own session.

    ``process_in_background`` is already a synchronous entry point that manages its
    own event loop; wrapping it in another ``asyncio.run`` here raises
    ``RuntimeError: asyncio.run() cannot be called from a running event loop``.
    """
    document_service.process_in_background(document_id)


def _run_reindex(document_id: str) -> None:
    document_service.reindex_in_background(document_id)


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_auth), Depends(upload_rate_limit_dependency)],
    summary="Upload an HR document (PDF / TXT / Markdown)",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF, TXT or Markdown HR document"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    content = await file.read()
    record = document_service.persist_upload(db, file.filename or "", content)
    background_tasks.add_task(_run_indexing, record.id)
    return UploadResponse(
        document=DocumentOut.model_validate(record),
        message="Document uploaded. Indexing has started.",
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents with their real processing state",
)
def list_documents(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    if status_filter and status_filter not in VALID_STATUSES:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown status '{status_filter}'. Expected one of: "
            f"{', '.join(VALID_STATUSES)}.",
            code="invalid_status",
        )

    documents = document_service.list(
        db, status=status_filter, search=search, limit=limit, offset=offset
    )
    counts = document_service.counts(db)
    return DocumentListResponse(
        documents=[DocumentOut.model_validate(document) for document in documents],
        total=counts["total"],
        indexed=counts["ready"],
        failed=counts["failed"],
        processing=counts["pending"] + counts["processing"],
    )


@router.get("/limits/file", summary="Upload constraints enforced by the server")
def upload_limits() -> dict:
    return {
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
        "max_upload_size_bytes": settings.upload_size_limit_bytes,
        "allowed_extensions": list(settings.ALLOWED_EXTENSIONS),
        "allowed_content_types": list(settings.ALLOWED_CONTENT_TYPES),
        "auth_required": settings.auth_enforced,
    }


@router.get(
    "/{document_id}",
    response_model=DocumentDetail,
    summary="Document metadata plus its stored chunks",
)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentDetail:
    record, chunks, collection_chunks = document_service.detail(db, document_id)
    detail = DocumentDetail.model_validate(record)
    detail.chunks = [DocumentChunkOut(**chunk) for chunk in chunks]
    detail.collection_chunks = collection_chunks
    return detail


@router.get(
    "/{document_id}/file",
    dependencies=[Depends(require_auth)],
    summary="Download the original uploaded file",
)
def download_document(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    record, path = document_service.resolve_file(db, document_id)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=record.filename,
    )


@router.post(
    "/{document_id}/reindex",
    response_model=ReindexResponse,
    dependencies=[Depends(require_auth)],
    summary="Re-extract and re-index a document",
)
def reindex_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ReindexResponse:
    record = document_service.get(db, document_id)
    background_tasks.add_task(_run_reindex, record.id)
    return ReindexResponse(
        document=DocumentOut.model_validate(record),
        message="Re-indexing has started.",
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_auth)],
    summary="Delete a document and its vectors",
)
async def delete_document(document_id: str, db: Session = Depends(get_db)) -> None:
    await document_service.delete(db, document_id)
    logger.info("Document %s deleted", document_id)
