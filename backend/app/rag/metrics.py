"""Lightweight, in-process RAG observability.

Purpose
-------
Make the retrieval/generation behaviour measurable without shipping a heavy APM
stack. Everything collected here is aggregate metadata (counts, latencies,
scores, chunk counts) — **no document text, no questions, no credentials**.

Persisted query history lives in the relational database (see
``app.models.entities.QueryLog``) so the dashboard can show real numbers across
restarts; this module covers the live process.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_MAX_SAMPLES = 50


@dataclass
class RAGMetrics:
    """Thread-safe counters for the RAG pipeline."""

    queries_total: int = 0
    grounded_answers: int = 0
    no_context_answers: int = 0
    errors_total: int = 0
    chunks_retrieved_total: int = 0
    retrieval_latency_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    generation_latency_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    total_latency_ms: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    top_scores: deque[float] = field(default_factory=lambda: deque(maxlen=200))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _started_at: float = field(default_factory=time.time, repr=False)

    # -- recording ------------------------------------------------------
    def record_query(
        self,
        *,
        retrieval_latency_ms: float,
        generation_latency_ms: float | None,
        total_latency_ms: float,
        chunks_retrieved: int,
        top_score: float,
        grounded: bool,
    ) -> None:
        with self._lock:
            self.queries_total += 1
            if grounded:
                self.grounded_answers += 1
            else:
                self.no_context_answers += 1
            self.chunks_retrieved_total += chunks_retrieved
            self.retrieval_latency_ms.append(retrieval_latency_ms)
            self.total_latency_ms.append(total_latency_ms)
            self.top_scores.append(top_score)
            if generation_latency_ms is not None:
                self.generation_latency_ms.append(generation_latency_ms)

    def record_error(self) -> None:
        with self._lock:
            self.errors_total += 1

    def reset(self) -> None:
        with self._lock:
            self.queries_total = 0
            self.grounded_answers = 0
            self.no_context_answers = 0
            self.errors_total = 0
            self.chunks_retrieved_total = 0
            self.retrieval_latency_ms.clear()
            self.generation_latency_ms.clear()
            self.total_latency_ms.clear()
            self.top_scores.clear()

    # -- reporting ------------------------------------------------------
    @staticmethod
    def _p95(values: deque[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        return round(ordered[index], 2)

    @staticmethod
    def _avg(values: deque[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queries_total": self.queries_total,
                "grounded_answers": self.grounded_answers,
                "no_context_answers": self.no_context_answers,
                "errors_total": self.errors_total,
                "grounded_ratio": (
                    round(self.grounded_answers / self.queries_total, 4)
                    if self.queries_total
                    else None
                ),
                "avg_chunks_retrieved": (
                    round(self.chunks_retrieved_total / self.queries_total, 2)
                    if self.queries_total
                    else None
                ),
                "avg_retrieval_ms": self._avg(self.retrieval_latency_ms),
                "p95_retrieval_ms": self._p95(self.retrieval_latency_ms),
                "avg_generation_ms": self._avg(self.generation_latency_ms),
                "avg_total_ms": self._avg(self.total_latency_ms),
                "p95_total_ms": self._p95(self.total_latency_ms),
                "avg_top_score": self._avg(self.top_scores),
                "uptime_seconds": round(time.time() - self._started_at, 1),
            }


rag_metrics = RAGMetrics()
