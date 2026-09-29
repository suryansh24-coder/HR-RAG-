"""API router aggregation.

All endpoints live under ``settings.API_PREFIX`` (``/api`` by default) so the
public surface is easy to reason about:

* ``/api/health``   — liveness, readiness and dependency health
* ``/api/meta``     — app info and capability flags for the frontend
* ``/api/auth``     — management-token status
* ``/api/chat``     — grounded answers (buffered + SSE streaming)
* ``/api/documents``— upload / list / inspect / download / re-index / delete
* ``/api/conversations`` — chat history
* ``/api/rag``      — statistics, configuration, retrieval debug, query log
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, chat, conversations, documents, health, rag
from app.core.config import settings
from app.schemas import MetaResponse

api_router = APIRouter()

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/meta", response_model=MetaResponse, summary="API metadata")
def api_meta() -> dict:
    """Capability flags so the frontend never has to hard-code backend behaviour."""
    return {
        "detail": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "api_prefix": settings.API_PREFIX,
        "features": {
            "streaming": True,
            "auth_required": settings.auth_enforced,
            "debug": settings.RAG_DEBUG,
            "database": settings.DATABASE_URL.split("://", 1)[0],
            "qdrant_mode": "local" if settings.qdrant_is_local else "server",
        },
    }


api_router.include_router(meta_router, prefix=settings.API_PREFIX)
api_router.include_router(health.router, prefix=settings.API_PREFIX)
api_router.include_router(auth.router, prefix=settings.API_PREFIX)
api_router.include_router(rag.router, prefix=settings.API_PREFIX)
api_router.include_router(chat.router, prefix=settings.API_PREFIX)
api_router.include_router(documents.router, prefix=settings.API_PREFIX)
api_router.include_router(conversations.router, prefix=settings.API_PREFIX)
