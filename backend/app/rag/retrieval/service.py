"""Semantic + hybrid retrieval with thresholding, diversification and context assembly."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from qdrant_client import models

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.retrieval.scorer import (
    LexicalMatch,
    corpus_coverage,
    distinctive_terms,
    hybrid_score,
    lexical_match,
)
from app.rag.vector_store.qdrant_store import (
    PAYLOAD_CHUNK_INDEX,
    PAYLOAD_DOCUMENT_ID,
    PAYLOAD_DOCUMENT_TYPE,
    PAYLOAD_FILENAME,
    PAYLOAD_PAGE,
    PAYLOAD_TEXT,
    vector_store,
)

logger = get_logger(__name__)

SNIPPET_CHARS = 420


@dataclass
class RetrievedChunk:
    """A single search hit with its provenance metadata and relevance score."""

    chunk_id: str
    document_id: str
    filename: str
    page: int
    chunk_index: int
    document_type: str
    text: str
    cosine: float
    score: float
    lexical: LexicalMatch = field(default_factory=lambda: LexicalMatch(0.0, 0, 0))

    @property
    def citation(self) -> str:
        return f"{self.filename} · page {self.page}"

    def source_ref(self) -> dict:
        """Serialisable citation payload returned to the client."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "page": self.page,
            "chunk_index": self.chunk_index,
            "document_type": self.document_type,
            "score": round(self.score, 4),
            "cosine_similarity": round(self.cosine, 4),
            "citation": self.citation,
            "snippet": self.text.strip()[:SNIPPET_CHARS],
        }


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk] = field(default_factory=list)
    latency_ms: float = 0.0
    query: str = ""
    candidates: int = 0
    rejected_no_lexical_overlap: int = 0
    rejected_below_threshold: int = 0
    threshold: float = 0.0
    top_k: int = 0
    corpus_coverage: float = 1.0

    @property
    def has_results(self) -> bool:
        return len(self.chunks) > 0

    @property
    def top_score(self) -> float:
        return self.chunks[0].score if self.chunks else 0.0

    def trace(self) -> dict:
        return {
            "retrieval_candidates": self.candidates,
            "retrieval_hits": len(self.chunks),
            "retrieval_top_score": round(self.top_score, 4),
            "retrieval_scores": [round(c.score, 4) for c in self.chunks],
            "retrieval_latency_ms": self.latency_ms,
            "retrieval_top_k": self.top_k,
            "retrieval_score_threshold": self.threshold,
            "retrieval_corpus_coverage": round(self.corpus_coverage, 4),
            "retrieval_rejected_no_overlap": self.rejected_no_lexical_overlap,
            "retrieval_rejected_below_threshold": self.rejected_below_threshold,
        }


def _to_chunk(
    point: models.ScoredPoint, question_terms: list[str], alpha: float
) -> RetrievedChunk:
    payload = point.payload or {}
    text = str(payload.get(PAYLOAD_TEXT, ""))
    cosine = float(point.score)
    lexical = lexical_match(question_terms, text)
    score = 0.0 if lexical.has_no_signal else hybrid_score(cosine, lexical.coverage, alpha)
    return RetrievedChunk(
        chunk_id=str(point.id),
        document_id=str(payload.get(PAYLOAD_DOCUMENT_ID, "")),
        filename=str(payload.get(PAYLOAD_FILENAME, "unknown")),
        page=int(payload.get(PAYLOAD_PAGE, 1) or 1),
        chunk_index=int(payload.get(PAYLOAD_CHUNK_INDEX, 0) or 0),
        document_type=str(payload.get(PAYLOAD_DOCUMENT_TYPE, "")),
        text=text,
        cosine=cosine,
        score=score,
        lexical=lexical,
    )


def _diversify(chunks: list[RetrievedChunk], max_per_document: int) -> list[RetrievedChunk]:
    """Cap how many chunks any single document may contribute.

    Without this a long policy file can crowd out every other source and the
    answer ends up citing one document repeatedly.
    """
    if max_per_document <= 0:
        return list(chunks)

    kept: list[RetrievedChunk] = []
    deferred: list[RetrievedChunk] = []
    seen: dict[str, int] = {}

    for chunk in chunks:  # already sorted by descending score
        count = seen.get(chunk.document_id, 0)
        if count < max_per_document:
            seen[chunk.document_id] = count + 1
            kept.append(chunk)
        else:
            deferred.append(chunk)

    kept.extend(deferred)
    return kept


def retrieve(
    query_vector: list[float],
    query_text: str,
    top_k: int | None = None,
    score_threshold: float | None = None,
    max_per_document: int | None = None,
) -> RetrievalResult:
    """Vector search → hybrid scoring → threshold → per-document diversification.

    ``score_threshold`` applies to the **hybrid** score (see
    :mod:`app.rag.retrieval.scorer`), which is what makes refusal reliable.
    """
    k = top_k or settings.TOP_K
    threshold = settings.SCORE_THRESHOLD if score_threshold is None else score_threshold
    per_doc = settings.MAX_CHUNKS_PER_DOCUMENT if max_per_document is None else max_per_document
    alpha = settings.HYBRID_ALPHA

    started = time.perf_counter()
    raw_points = vector_store.search(vector=query_vector, top_k=max(settings.RETRIEVAL_CANDIDATES, k))
    latency = (time.perf_counter() - started) * 1000

    terms = distinctive_terms(query_text)

    # Diagnostic only: this does *not* gate the result. Measured over the 32-case
    # evaluation set, corpus coverage does not separate answerable from
    # unanswerable questions (an out-of-scope "CEO's home address" scores 0.67,
    # above in-domain questions that score 0.50), so gating on it would trade
    # correct refusals for wrong ones. It is traced because it is the right thing
    # to watch as the corpus grows.
    corpus_cov = corpus_coverage(terms, vector_store.corpus_terms())

    candidates = [_to_chunk(point, terms, alpha) for point in raw_points]
    candidates.sort(key=lambda c: c.score, reverse=True)

    with_signal = [c for c in candidates if not c.lexical.has_no_signal]
    no_signal = len(candidates) - len(with_signal)

    passing = [c for c in with_signal if threshold <= 0 or c.score >= threshold]
    below = len(with_signal) - len(passing)
    selected = _diversify(passing, per_doc)[:k]

    logger.debug(
        "retrieval terms=%s candidates=%d kept=%d dropped(no_overlap)=%d dropped(threshold)=%d "
        "top=%.3f in %.1fms",
        terms,
        len(candidates),
        len(selected),
        no_signal,
        below,
        selected[0].score if selected else 0.0,
        latency,
    )

    return RetrievalResult(
        chunks=selected,
        latency_ms=round(latency, 2),
        query=query_text,
        candidates=len(candidates),
        rejected_no_lexical_overlap=no_signal,
        rejected_below_threshold=below,
        threshold=threshold,
        top_k=k,
        corpus_coverage=corpus_cov,
    )


def assemble_context(chunks: list[RetrievedChunk], limit: int | None = None) -> str:
    """Build the numbered context block embedded in the prompt.

    Each block starts with a machine-parseable header so the deterministic
    ``extractive`` provider can recover ``(filename, page)`` provenance. Line
    structure inside the chunk is preserved — collapsing it glues section
    headings onto the first sentence of a section ("Overtime Overtime is not
    paid.") and destroys the paragraph boundaries the reader relies on.
    """
    max_chunks = limit or settings.MAX_CONTEXT_CHUNKS
    blocks: list[str] = []
    for index, chunk in enumerate(chunks[:max_chunks], start=1):
        header = f"[{index}] source={chunk.filename}, page={chunk.page}"
        body = "\n".join(" ".join(line.split()) for line in chunk.text.splitlines() if line.strip())
        blocks.append(f"{header}\n{body}")
    return "\n\n".join(blocks)
