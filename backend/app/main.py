"""FastAPI application factory, lifespan, middleware and error handling."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger
from app.core.security import configure_cors
from app.database.session import init_db
from app.rag.generation.llm import provider_factory
from app.rag.pipeline import pipeline

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.LOG_LEVEL)
    init_db()
    logger.info(
        "Starting %s v%s (env=%s, llm=%s, qdrant=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
        settings.LLM_PROVIDER,
        settings.QDRANT_COLLECTION,
    )

    # Validate the LLM provider early so misconfiguration is visible immediately.
    try:
        provider = provider_factory()
        logger.info("LLM provider ready: %s (%s)", provider.name, settings.LLM_MODEL)
    except AppError as exc:
        logger.warning("LLM provider not ready: %s", exc.detail)

    # Load the embedding model and validate the collection once, not per request.
    try:
        await pipeline.warmup()
        logger.info("Vector store ready (collection validated against the embedding model)")
    except AppError as exc:
        logger.warning("Vector store not ready: %s", exc.detail)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector store warm-up failed: %s", exc)

    if settings.auth_enforced and not settings.API_AUTH_TOKEN:
        logger.warning(
            "AUTH_REQUIRED is enabled but API_AUTH_TOKEN is empty: write endpoints "
            "(upload, re-index, delete) will return 503 until a token is configured."
        )

    if settings.LLM_PROVIDER == "extractive" and settings.APP_ENV == "production":
        # Not fatal: extractive mode is a legitimate, fully offline configuration
        # and it never invents anything. It must simply never be mistaken for a
        # generated answer, so say so loudly at boot.
        logger.warning(
            "LLM_PROVIDER=extractive in production: answers are verbatim quotes from "
            "the retrieved chunks and no language model is called. Set LLM_PROVIDER "
            "and LLM_API_KEY if you intended generated answers."
        )

    yield

    from app.rag.vector_store.qdrant_store import vector_store

    vector_store.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description=(
        "HR Nexus — Intelligent HR Knowledge Assistant.\n\n"
        "Answers are grounded in the uploaded HR knowledge base: documents are "
        "extracted, chunked, embedded and stored in Qdrant, and every answer "
        "returns the real chunks it was generated from. When retrieval finds "
        "nothing relevant the API refuses to answer instead of guessing."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

configure_cors(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id and measure end-to-end latency."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers[REQUEST_ID_HEADER] = request_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
    if elapsed_ms > 2000:
        logger.warning(
            "Slow request %s %s took %.0fms (request_id=%s)",
            request.method,
            request.url.path,
            elapsed_ms,
            request_id,
        )
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "API error %s %s -> %s (%s) request_id=%s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
        getattr(request.state, "request_id", "-"),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace to the client."""
    logger.exception(
        "Unhandled error on %s %s (request_id=%s)",
        request.method,
        request.url.path,
        getattr(request.state, "request_id", "-"),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected server error occurred. Please try again.",
            "code": "internal_error",
        },
    )


@app.get("/", tags=["meta"], summary="Service banner")
def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "subtitle": "Intelligent HR Knowledge Assistant",
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "docs": "/docs",
        "api": settings.API_PREFIX,
        "health": f"{settings.API_PREFIX}/health",
    }


app.include_router(api_router)
