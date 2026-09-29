"""Chat, source-citation and streaming schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

MAX_QUESTION_CHARS = 2000


class SourceOut(BaseModel):
    """A real citation pointing at a chunk that was actually retrieved."""

    chunk_id: str
    document_id: str
    filename: str
    page: int
    chunk_index: int = 0
    document_type: str = ""
    score: float
    citation: str = ""
    snippet: str = ""


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: str | None = None
    include_suggestions: bool = True

    @field_validator("question")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question must not be empty.")
        return cleaned


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    context_used: bool = False
    no_context: bool = False
    conversation_id: str | None = None
    message_id: str | None = None
    retrieval_hits: int = 0
    trace: dict[str, Any] = Field(default_factory=dict)
    total_latency_ms: float | None = None


class FollowUpRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: str | None = None
    limit: int = Field(default=3, ge=1, le=5)


class FollowUpResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)
    grounded: bool = False


class StreamStage(BaseModel):
    stage: Literal["retrieving", "sources", "generating", "complete", "error"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
