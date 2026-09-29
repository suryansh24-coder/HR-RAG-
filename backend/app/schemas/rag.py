"""RAG statistics, retrieval-debug and query-history schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CollectionInfo(BaseModel):
    name: str
    exists: bool = False
    status: str = "missing"
    points_count: int = 0
    vectors_count: int = 0
    indexed_vectors_count: int = 0
    dimension: int | None = None
    distance: str | None = None


class RagConfigOut(BaseModel):
    embedding_model: str
    embedding_dimension: int | None = None
    llm_provider: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    score_threshold: float
    max_chunks_per_document: int
    max_context_chunks: int
    history_turns: int
    qdrant_mode: str
    qdrant_collection: str
    allowed_extensions: list[str]
    max_upload_size_mb: int


class RagStatsResponse(BaseModel):
    """Every value is measured from live state — nothing here is fabricated."""

    documents_total: int = 0
    documents_indexed: int = 0
    documents_processing: int = 0
    documents_failed: int = 0
    total_chunks: int = 0
    #: Chunks actually stored for documents that finished indexing.
    chunks_indexed: int = 0
    qdrant_status: str = "unknown"
    collection: CollectionInfo = Field(default_factory=CollectionInfo)
    last_indexed_at: datetime | None = None
    queries_total: int = 0
    queries_grounded: int = 0
    queries_no_context: int = 0
    conversations_total: int = 0
    messages_total: int = 0
    last_query_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    config: RagConfigOut
    debug_mode: bool = False


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    page: int
    chunk_index: int
    document_type: str
    score: float
    citation: str
    text: str


class SearchResponse(BaseModel):
    question: str
    hits: list[SearchHit]
    trace: dict[str, Any] = Field(default_factory=dict)


class QueryLogOut(BaseModel):
    id: str
    question_preview: str
    grounded: bool
    chunks_retrieved: int
    top_score: float | None = None
    total_latency_ms: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QueryLogListResponse(BaseModel):
    entries: list[QueryLogOut]
    total: int

