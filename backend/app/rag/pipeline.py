"""RAG pipeline orchestrator.

This is the single place where the RAG stages are wired together:

``ingest``   loaders → cleaning → chunking → embeddings → Qdrant
``query``    question → embedding → Qdrant → thresholding → context → prompt → LLM

It exposes both a buffered API (``query``) and a streaming API (``stream_query``)
used by the SSE endpoint. Both paths share the same retrieval and generation
code, so streaming never changes the answer.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.concurrency import run_in_threadpool
from qdrant_client import models

from app.core.config import settings
from app.core.exceptions import InternalError, ValidationError
from app.core.logging import get_logger
from app.rag.chunking.chunker import RecursiveChunker
from app.rag.embeddings.service import embedding_service
from app.rag.generation.llm import LLMProvider, provider_factory
from app.rag.loaders.base import ExtractedDocument
from app.rag.metrics import rag_metrics
from app.rag.prompting.builder import build_prompt
from app.rag.retrieval.service import (
    RetrievedChunk,
    RetrievalResult,
    assemble_context,
    retrieve,
)
from app.rag.vector_store.qdrant_store import (
    build_payload,
    build_point_id,
    vector_store,
)

logger = get_logger(__name__)

Stage = Literal["retrieving", "sources", "generating", "complete"]

MAX_QUESTION_CHARS = 2000


# --------------------------------------------------------------------------- #
# Result types
# --------------------------------------------------------------------------- #
@dataclass
class IndexResult:
    document_id: str
    chunks: int
    dimension: int
    pages: int = 0


@dataclass
class ChatResult:
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    context_used: bool = False
    no_context: bool = False
    retrieval_hits: int = 0
    trace: dict[str, Any] = field(default_factory=dict)
    # Measured end to end, reported whether or not RAG_DEBUG exposes the trace.
    latency_ms: float | None = None


@dataclass
class StreamEvent:
    stage: Stage
    message: str
    data: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class RAGPipeline:
    def __init__(self) -> None:
        self._chunker = RecursiveChunker(settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        self._llm: LLMProvider | None = None
        self._collection_ready = False
        self._lock = asyncio.Lock()

    # -- infrastructure --------------------------------------------------
    @property
    def provider(self) -> LLMProvider:
        if self._llm is None:
            self._llm = provider_factory()
        return self._llm

    def ensure_collection(self, recreate: bool = False) -> int:
        """Idempotently ensure the collection matches the embedding dimension."""
        dimension = embedding_service.dimension
        vector_store.ensure_collection(dimension, recreate=recreate)
        self._collection_ready = True
        return dimension

    async def warmup(self) -> None:
        """Load the embedding model and validate the collection at startup."""
        await run_in_threadpool(self.ensure_collection)

    def chunk_document(self, document: ExtractedDocument) -> list[tuple[int, str]]:
        """Chunk every page of an extracted document into ``(page, text)`` pairs."""
        pairs: list[tuple[int, str]] = []
        for page in document.pages:
            text = (page.text or "").strip()
            if not text:
                continue
            for chunk in self._chunker.chunk_text(text):
                chunk = chunk.strip()
                if chunk:
                    pairs.append((page.page, chunk))
        return pairs

    # -- ingestion -------------------------------------------------------
    async def ingest(
        self,
        document: ExtractedDocument,
        document_id: str,
        uploaded_at: str,
        filename: str,
    ) -> IndexResult:
        async with self._lock:
            dimension = await run_in_threadpool(self.ensure_collection)

        pairs = self.chunk_document(document)
        if not pairs:
            raise ValidationError(
                f"Document '{filename}' produced no indexable text. "
                "Scanned or image-only documents cannot be indexed."
            )

        vectors = await run_in_threadpool(
            embedding_service.encode, [text for _, text in pairs]
        )

        points = [
            models.PointStruct(
                id=build_point_id(document_id, index),
                vector=vector,
                payload=build_payload(
                    document_id=document_id,
                    filename=filename,
                    document_type=document.document_type,
                    uploaded_at=uploaded_at,
                    page=page,
                    chunk_index=index,
                    text=text,
                    chunks_total=len(pairs),
                ),
            )
            for index, ((page, text), vector) in enumerate(zip(pairs, vectors))
        ]

        await run_in_threadpool(vector_store.upsert_chunks, points)
        logger.info(
            "Indexed %d chunks (%d pages, dim=%d) for document %s",
            len(points),
            len({page for page, _ in pairs}),
            dimension,
            document_id,
        )
        return IndexResult(
            document_id=document_id,
            chunks=len(points),
            dimension=dimension,
            pages=len({page for page, _ in pairs}),
        )

    # -- retrieval -------------------------------------------------------
    def _embedding_query(self, question: str, history: list[dict[str, str]] | None) -> str:
        """Build the text that is embedded for retrieval.

        Follow-up questions in a conversation are frequently elliptical
        ("can I carry it forward?"). Embedding the recent user turns alongside the
        current question makes the retrieval query self-contained without
        mutating what the user actually asked.
        """
        turns = [t["content"].strip() for t in (history or []) if t.get("role") == "user"]
        turns = [t for t in turns[-settings.HISTORY_TURNS:] if t]
        if not turns:
            return question
        return " ".join([*turns[:-1], question]) if len(turns) > 1 else question

    async def _search(
        self,
        question: str,
        history: list[dict[str, str]] | None,
    ) -> tuple[RetrievalResult, str]:
        await self.warmup()
        embed_text = self._embedding_query(question, history)
        vector = await run_in_threadpool(embedding_service.encode_query, embed_text)
        result = await run_in_threadpool(retrieve, vector, embed_text)
        return result, embed_text

    # -- generation ------------------------------------------------------
    async def _generate(
        self, question: str, context: str, history: list[dict[str, str]] | None
    ) -> tuple[str, str, float]:
        provider = self.provider
        bundle = build_prompt(question, context, history)
        started = time.perf_counter()
        answer = await provider.complete(bundle.system, bundle.user)
        latency = (time.perf_counter() - started) * 1000
        answer = (answer or "").strip()
        if not answer:
            raise InternalError("The language model returned an empty response.")
        return answer, provider.name, latency

    # -- buffered query --------------------------------------------------
    async def query(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> ChatResult:
        question = (question or "").strip()
        if not question:
            raise ValidationError("Question must not be empty.")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValidationError(
                f"Question exceeds the {MAX_QUESTION_CHARS} character limit."
            )

        started = time.perf_counter()
        try:
            retrieval, embed_text = await self._search(question, history)

            if not retrieval.has_results:
                total_ms = round((time.perf_counter() - started) * 1000, 2)
                rag_metrics.record_query(
                    retrieval_latency_ms=retrieval.latency_ms,
                    generation_latency_ms=None,
                    total_latency_ms=total_ms,
                    chunks_retrieved=0,
                    top_score=0.0,
                    grounded=False,
                )
                return ChatResult(
                    answer=settings.NO_CONTEXT_RESPONSE,
                    sources=[],
                    context_used=False,
                    no_context=True,
                    retrieval_hits=0,
                    latency_ms=total_ms,
                    trace=self._trace(
                        {
                            **retrieval.trace(),
                            "llm_called": False,
                            "llm_provider": self.provider.name,
                            "llm_model": settings.LLM_MODEL,
                            "embedded_query": embed_text,
                            "total_latency_ms": total_ms,
                        }
                    ),
                )

            context = assemble_context(retrieval.chunks)
            answer, provider_name, llm_latency = await self._generate(question, context, history)
            total_ms = round((time.perf_counter() - started) * 1000, 2)

            rag_metrics.record_query(
                retrieval_latency_ms=retrieval.latency_ms,
                generation_latency_ms=round(llm_latency, 2),
                total_latency_ms=total_ms,
                chunks_retrieved=len(retrieval.chunks),
                top_score=retrieval.top_score,
                grounded=True,
            )

            return ChatResult(
                answer=answer,
                sources=[chunk.source_ref() for chunk in retrieval.chunks],
                context_used=True,
                no_context=False,
                retrieval_hits=len(retrieval.chunks),
                latency_ms=total_ms,
                trace=self._trace(
                    {
                        **retrieval.trace(),
                        "llm_called": True,
                        "llm_provider": provider_name,
                        "llm_model": settings.LLM_MODEL,
                        "llm_latency_ms": round(llm_latency, 2),
                        "embedded_query": embed_text,
                        "total_latency_ms": total_ms,
                    }
                ),
            )
        except Exception:
            rag_metrics.record_error()
            raise

    # -- streaming query -------------------------------------------------
    async def stream_query(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield real pipeline progress events, then the final answer.

        Stages are emitted by the pipeline itself, so the UI never shows a
        fabricated progress step:

        * ``retrieving`` — emitted before the embedding + vector search
        * ``sources``    — emitted with the real citations once retrieval is done
        * ``generating`` — emitted before the LLM call
        * ``complete``   — terminal event carrying the answer, sources and trace
        """
        question = (question or "").strip()
        if not question:
            raise ValidationError("Question must not be empty.")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValidationError(
                f"Question exceeds the {MAX_QUESTION_CHARS} character limit."
            )

        started = time.perf_counter()
        try:
            yield StreamEvent(
                stage="retrieving",
                message="Retrieving HR knowledge",
                data={"provider": settings.EMBEDDING_MODEL},
            )

            retrieval, embed_text = await self._search(question, history)

            if not retrieval.has_results:
                total_ms = round((time.perf_counter() - started) * 1000, 2)
                rag_metrics.record_query(
                    retrieval_latency_ms=retrieval.latency_ms,
                    generation_latency_ms=None,
                    total_latency_ms=total_ms,
                    chunks_retrieved=0,
                    top_score=0.0,
                    grounded=False,
                )
                yield StreamEvent(
                    stage="complete",
                    message=settings.NO_CONTEXT_RESPONSE,
                    data={
                        "answer": settings.NO_CONTEXT_RESPONSE,
                        "sources": [],
                        "no_context": True,
                        "context_used": False,
                        "retrieval_hits": 0,
                        "total_latency_ms": total_ms,
                        "trace": self._trace(
                            {
                                **retrieval.trace(),
                                "llm_called": False,
                                "llm_provider": self.provider.name,
                                "llm_model": settings.LLM_MODEL,
                                "embedded_query": embed_text,
                                "total_latency_ms": total_ms,
                            }
                        ),
                    },
                )
                return

            sources = [chunk.source_ref() for chunk in retrieval.chunks]
            context = assemble_context(retrieval.chunks)

            yield StreamEvent(
                stage="sources",
                message="Generating response",
                data={
                    "sources": sources,
                    "retrieval_hits": len(retrieval.chunks),
                    "retrieval_latency_ms": retrieval.latency_ms,
                    "top_score": round(retrieval.top_score, 4),
                    "context": context,
                },
            )
            yield StreamEvent(
                stage="generating",
                message="Generating response",
                data={"llm_provider": self.provider.name, "llm_model": settings.LLM_MODEL},
            )

            llm_started = time.perf_counter()
            answer, provider_name, llm_latency = await self._generate(
                question, context, history
            )
            total_ms = round((time.perf_counter() - started) * 1000, 2)

            rag_metrics.record_query(
                retrieval_latency_ms=retrieval.latency_ms,
                generation_latency_ms=round(llm_latency, 2),
                total_latency_ms=total_ms,
                chunks_retrieved=len(sources),
                top_score=retrieval.top_score,
                grounded=True,
            )

            yield StreamEvent(
                stage="complete",
                message="Complete",
                data={
                    "answer": answer,
                    "sources": sources,
                    "no_context": False,
                    "context_used": True,
                    "retrieval_hits": len(sources),
                    "total_latency_ms": total_ms,
                    "trace": self._trace(
                        {
                            **retrieval.trace(),
                            "llm_called": True,
                            "llm_provider": provider_name,
                            "llm_model": settings.LLM_MODEL,
                            "llm_latency_ms": round(llm_latency, 2),
                            "embedded_query": embed_text,
                            "total_latency_ms": total_ms,
                        }
                    ),
                },
            )
        except Exception:
            rag_metrics.record_error()
            raise

    # -- retrieval-only (debug / evaluation) ------------------------------
    async def search_only(
        self,
        question: str,
        top_k: int | None = None,
        score_threshold: float | None = None,
    ) -> tuple[list[RetrievedChunk], RetrievalResult]:
        question = (question or "").strip()
        if not question:
            raise ValidationError("Question must not be empty.")
        vector = await run_in_threadpool(embedding_service.encode_query, question)
        result = await run_in_threadpool(
            retrieve, vector, question, top_k, score_threshold
        )
        return result.chunks, result

    # -- maintenance ------------------------------------------------------
    async def delete_document(self, document_id: str) -> int:
        return await run_in_threadpool(vector_store.delete_document, document_id)

    @staticmethod
    def _trace(trace: dict[str, Any]) -> dict[str, Any]:
        """Trace details are only exposed when RAG_DEBUG is enabled."""
        return trace if settings.RAG_DEBUG else {}


pipeline = RAGPipeline()
