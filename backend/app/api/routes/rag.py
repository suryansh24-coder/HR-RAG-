"""RAG observability endpoints: real statistics, retrieval debug and query log."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.rag.embeddings.service import embedding_service
from app.rag.generation.llm import provider_factory
from app.rag.metrics import rag_metrics
from app.rag.pipeline import pipeline
from app.rag.vector_store.qdrant_store import vector_store
from app.schemas import (
    CollectionInfo,
    QueryLogListResponse,
    QueryLogOut,
    RagConfigOut,
    RagStatsResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.services.chat_service import stats_service

router = APIRouter(prefix="/rag", tags=["rag"])


def _document_service():
    """Local import keeps the route module import-light and avoids a cycle."""
    from app.services.document_service import document_service

    return document_service


def _embedding_dimension() -> int | None:
    try:
        return embedding_service.dimension
    except Exception:  # noqa: BLE001
        return None


def _collection_info() -> CollectionInfo:
    return CollectionInfo.model_validate(vector_store.collection_info())


def _config_out() -> RagConfigOut:
    """The effective RAG configuration (never hard-coded in the frontend)."""
    try:
        llm_provider = provider_factory().name
    except Exception:  # noqa: BLE001
        llm_provider = settings.LLM_PROVIDER

    return RagConfigOut(
        embedding_model=embedding_service.model_name,
        embedding_dimension=_embedding_dimension(),
        llm_provider=llm_provider,
        llm_model=settings.LLM_MODEL,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        top_k=settings.TOP_K,
        score_threshold=settings.SCORE_THRESHOLD,
        max_chunks_per_document=settings.MAX_CHUNKS_PER_DOCUMENT,
        max_context_chunks=settings.MAX_CONTEXT_CHUNKS,
        history_turns=settings.HISTORY_TURNS,
        qdrant_mode=vector_store.mode,
        qdrant_collection=vector_store.collection,
        allowed_extensions=list(settings.ALLOWED_EXTENSIONS),
        max_upload_size_mb=settings.MAX_UPLOAD_SIZE_MB,
    )


@router.get(
    "/stats",
    response_model=RagStatsResponse,
    summary="Live knowledge-base and pipeline statistics",
)
def rag_stats(db: Session = Depends(get_db)) -> RagStatsResponse:
    """Every number is measured from live state (database, Qdrant, in-process metrics)."""
    counts = stats_service.document_counts(db)
    queries = stats_service.query_counts(db)
    vector_health = vector_store.healthcheck()
    document_service = _document_service()

    collection = _collection_info()
    indexed_chunks = (
        sum(vector_store.chunk_counts_by_document().values()) if counts["ready"] else 0
    )

    return RagStatsResponse(
        documents_total=counts["total"],
        documents_indexed=counts["ready"],
        documents_processing=counts["pending"] + counts["processing"],
        documents_failed=counts["failed"],
        total_chunks=vector_store.count_vectors(),
        chunks_indexed=indexed_chunks,
        qdrant_status=str(vector_health.get("status", "unknown")),
        collection=collection,
        last_indexed_at=document_service.last_indexed_at(db),
        queries_total=queries["total"],
        queries_grounded=queries["grounded"],
        queries_no_context=queries["no_context"],
        conversations_total=stats_service.conversation_count(db),
        messages_total=stats_service.message_count(db),
        last_query_at=stats_service.last_query_at(db),
        metrics=rag_metrics.snapshot(),
        config=_config_out(),
        debug_mode=settings.RAG_DEBUG,
    )


@router.get(
    "/queries",
    response_model=QueryLogListResponse,
    summary="Recent question telemetry (truncated previews only)",
)
def recent_queries(
    db: Session = Depends(get_db), limit: int = Query(default=25, ge=1, le=200)
) -> QueryLogListResponse:
    entries = stats_service.recent_queries(db, limit=limit)
    return QueryLogListResponse(
        entries=[QueryLogOut.model_validate(entry) for entry in entries], total=len(entries)
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Retrieval only — shows exactly which chunks a question matches",
)
async def retrieval_debug(payload: SearchRequest) -> SearchResponse:
    """Runs embedding + vector search + thresholding without calling the LLM.

    This is the endpoint used by the retrieval evaluation harness and by the
    "Knowledge" view when ``RAG_DEBUG`` is enabled.
    """
    chunks, result = await pipeline.search_only(
        payload.question, top_k=payload.top_k, score_threshold=payload.score_threshold
    )
    return SearchResponse(
        question=payload.question,
        hits=[
            SearchHit(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                filename=chunk.filename,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                document_type=chunk.document_type,
                score=round(chunk.score, 4),
                citation=chunk.citation,
                text=chunk.text,
            )
            for chunk in chunks
        ],
        trace=result.trace() if settings.RAG_DEBUG else {"hits": len(chunks)},
    )


@router.get("/config", response_model=RagConfigOut, summary="Active RAG configuration")
def rag_config() -> RagConfigOut:
    return _config_out()
