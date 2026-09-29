"""Health and service-metadata endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.rag.chunking.chunker import RecursiveChunker
from app.rag.embeddings.service import embedding_service
from app.rag.generation.llm import provider_factory
from app.rag.vector_store.qdrant_store import vector_store
from app.schemas import HealthComponent, HealthResponse

router = APIRouter(tags=["health"])


def _check_database(db: Session) -> HealthComponent:
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        return HealthComponent(
            status="ok",
            detail="reachable",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=str(exc)[:200])


def _check_vector_store() -> HealthComponent:
    result = vector_store.healthcheck()
    if result.get("status") == "ok":
        detail = (
            f"{result.get('mode')} · collection "
            f"{result.get('collection')} "
            f"({'ready' if result.get('collection_exists') else 'not created'})"
        )
        return HealthComponent(
            status="ok", detail=detail, latency_ms=result.get("latency_ms")
        )
    return HealthComponent(status="error", detail=str(result.get("error", "unavailable"))[:200])


def _check_embeddings() -> HealthComponent:
    started = time.perf_counter()
    try:
        dimension = embedding_service.dimension
        return HealthComponent(
            status="ok",
            detail=f"{embedding_service.model_name} · dim {dimension}",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=str(exc)[:200])


def _check_llm() -> HealthComponent:
    try:
        provider = provider_factory()
        return HealthComponent(status="ok", detail=f"{provider.name} · {settings.LLM_MODEL}")
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=str(exc)[:200])


def _check_rag() -> HealthComponent:
    try:
        chunker = RecursiveChunker(settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        return HealthComponent(
            status="ok",
            detail=f"chunk_size={chunker.chunk_size} overlap={chunker.chunk_overlap}",
        )
    except Exception as exc:  # noqa: BLE001
        return HealthComponent(status="error", detail=str(exc)[:200])


@router.get("/health", response_model=HealthResponse, summary="Full dependency health report")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    """Reports the live state of every dependency the RAG pipeline relies on."""
    components = {
        "database": _check_database(db),
        "vector_store": _check_vector_store(),
        "embeddings": _check_embeddings(),
        "llm": _check_llm(),
        "rag": _check_rag(),
    }
    overall = "ok" if all(c.status == "ok" for c in components.values()) else "degraded"
    return HealthResponse(
        status=overall,
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        components=components,
    )


@router.get("/health/live", summary="Liveness probe (no dependencies touched)")
def liveness() -> dict[str, Any]:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/health/ready", summary="Readiness probe (vector store must be reachable)")
def readiness() -> dict[str, Any]:
    vector = vector_store.healthcheck()
    ready = vector.get("status") == "ok"
    return {
        "status": "ready" if ready else "not_ready",
        "vector_store": vector,
    }
