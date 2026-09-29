"""Chat endpoints: buffered answers, SSE streaming and grounded follow-ups."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.security import rate_limit_dependency
from app.database.session import get_db, session_scope
from app.rag.pipeline import StreamEvent, pipeline
from app.schemas import (
    ChatRequest,
    ChatResponse,
    FollowUpRequest,
    FollowUpResponse,
    SourceOut,
)
from app.services.chat_service import ChatResult, chat_service

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[Depends(rate_limit_dependency)],
    summary="Ask a grounded HR question",
)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    conversation, assistant, result, suggestions = await chat_service.chat(
        db,
        question=payload.question,
        conversation_id=payload.conversation_id,
        include_suggestions=payload.include_suggestions,
    )
    return ChatResponse(
        answer=result.answer,
        sources=[SourceOut(**source) for source in result.sources],
        suggestions=suggestions,
        context_used=result.context_used,
        no_context=result.no_context,
        conversation_id=conversation.id,
        message_id=assistant.id,
        retrieval_hits=result.retrieval_hits,
        trace=result.trace,
        total_latency_ms=result.trace.get("total_latency_ms") if result.trace else None,
    )


@router.post(
    "/suggestions",
    response_model=FollowUpResponse,
    dependencies=[Depends(rate_limit_dependency)],
    summary="Grounded follow-up question suggestions",
)
async def suggestions(payload: FollowUpRequest, db: Session = Depends(get_db)) -> FollowUpResponse:
    """Suggests follow-ups derived from the sources retrieved for a question."""
    history = (
        chat_service.recent_history(db, payload.conversation_id)
        if payload.conversation_id
        else []
    )
    result = await pipeline.query(payload.question, history)
    return FollowUpResponse(
        suggestions=chat_service.suggest_follow_ups(
            payload.question, result, limit=payload.limit
        ),
        grounded=result.context_used,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def persist_turn(conversation_id: str, question: str, result: ChatResult) -> None:
    """Persist a streamed turn in its own session (safe after the response)."""
    with session_scope() as db:
        try:
            conversation = chat_service.get_conversation(db, conversation_id)
            chat_service.persist_turn(db, conversation, question, result)
            chat_service.log_query(db, question, result)
        except Exception:  # noqa: BLE001 - never break the response stream
            logger.exception("Could not persist streamed conversation %s", conversation_id)


@router.post(
    "/stream",
    dependencies=[Depends(rate_limit_dependency)],
    summary="Ask a question with server-sent pipeline progress",
)
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Stream the real pipeline stages for a question.

    Emitted events (all produced by the pipeline, never simulated):

    * ``retrieving``  — embedding the question and searching the vector store
    * ``sources``     — the citations that were actually retrieved
    * ``generating``  — the LLM is producing the grounded answer
    * ``complete``    — final answer, sources and (debug) trace
    * ``error``       — a sanitised failure message
    """

    async def event_stream() -> AsyncIterator[str]:
        conversation_id: str | None = payload.conversation_id
        completed: StreamEvent | None = None

        with session_scope() as db:
            conversation = chat_service.resolve_conversation(
                db, payload.conversation_id, payload.question
            )
            history = chat_service.recent_history(db, conversation.id)
            conversation_id = conversation.id
            db.commit()

        yield _sse(
            "start",
            {"conversation_id": conversation_id, "question": payload.question},
        )

        try:
            async for event in pipeline.stream_query(payload.question, history):
                if await request.is_disconnected():
                    logger.info("Client disconnected; aborting stream")
                    break
                if event.stage == "complete":
                    completed = event
                yield _sse(event.stage, {"message": event.message, **event.data})
        except AppError as exc:
            logger.warning("Stream error: %s", exc.detail)
            yield _sse("error", {"message": str(exc.detail), "code": exc.code})
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected streaming failure")
            yield _sse(
                "error",
                {
                    "message": "The assistant could not complete this request.",
                    "code": "internal_error",
                },
            )
        finally:
            if completed is not None and conversation_id:
                await asyncio.to_thread(
                    persist_turn,
                    conversation_id,
                    payload.question,
                    ChatResult(
                        answer=str(completed.data.get("answer", "")),
                        sources=list(completed.data.get("sources", [])),
                        context_used=bool(completed.data.get("context_used")),
                        no_context=bool(completed.data.get("no_context")),
                        retrieval_hits=int(completed.data.get("retrieval_hits", 0) or 0),
                        trace=dict(completed.data.get("trace", {})),
                    ),
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/config", summary="Chat behaviour the UI needs to know about")
def chat_config() -> dict[str, Any]:
    return {
        "no_context_response": settings.NO_CONTEXT_RESPONSE,
        "max_question_chars": 2000,
        "history_turns": settings.HISTORY_TURNS,
        "streaming": True,
    }
