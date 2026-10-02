"""Chat endpoints: buffered answers, SSE streaming and grounded follow-ups."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import replace
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
        total_latency_ms=result.latency_ms,
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


def chat_result_from_event(event: StreamEvent) -> ChatResult:
    """Rebuild the pipeline result carried by a ``complete`` stream event.

    Used both to derive follow-ups for the client and to persist the turn after
    the response has finished, so the streamed and buffered paths stay identical.
    """
    return ChatResult(
        answer=str(event.data.get("answer", "")),
        sources=list(event.data.get("sources", [])),
        context_used=bool(event.data.get("context_used")),
        no_context=bool(event.data.get("no_context")),
        retrieval_hits=int(event.data.get("retrieval_hits", 0) or 0),
        trace=dict(event.data.get("trace", {})),
        latency_ms=event.data.get("total_latency_ms"),
    )


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
    * ``complete``    — final answer, sources, follow-ups and (debug) trace
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
                # Follow-ups are derived from the sources that were really
                # retrieved, so the streaming client gets the same suggestions the
                # buffered /chat endpoint returns — no second retrieval round-trip.
                if event.stage == "complete" and payload.include_suggestions:
                    suggestions = chat_service.suggest_follow_ups(
                        payload.question, chat_result_from_event(event)
                    )
                    if suggestions:
                        event = replace(
                            event, data={**event.data, "suggestions": suggestions}
                        )
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
                    chat_result_from_event(completed),
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
