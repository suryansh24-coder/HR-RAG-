"""Conversation and message schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import SourceOut


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    preview: str | None = None

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    conversations: list[ConversationOut]
    total: int


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    sources: list[SourceOut] | None = None
    no_context: bool = False
    created_at: datetime
    latency_ms: float | None = None

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New conversation", max_length=255, min_length=1)

    @field_validator("title")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split()) or "New conversation"


class ConversationCreateResponse(BaseModel):
    conversation: ConversationOut


class ConversationRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
