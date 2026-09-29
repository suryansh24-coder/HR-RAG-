"""Document schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import DocumentStatus


class DocumentOut(BaseModel):
    id: str
    filename: str
    document_type: str
    size_bytes: int
    status: DocumentStatus
    error_message: str | None = None
    chunk_count: int
    page_count: int
    processing_time_ms: int | None = None
    uploaded_at: datetime
    indexed_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentOut]
    total: int
    indexed: int
    failed: int
    processing: int


class UploadResponse(BaseModel):
    document: DocumentOut
    message: str


class DocumentChunkOut(BaseModel):
    chunk_index: int
    page: int
    text: str
    citation: str


class DocumentDetail(DocumentOut):
    """Document metadata plus its stored chunk previews."""

    chunks: list[DocumentChunkOut] = Field(default_factory=list)
    collection_chunks: int = 0


class ReindexResponse(BaseModel):
    document: DocumentOut
    message: str
