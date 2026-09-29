"""Conversation endpoints (chat history)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import optional_auth
from app.database.session import get_db
from app.models import Conversation
from app.schemas import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
    ConversationRenameRequest,
    MessageOut,
)
from app.services.chat_service import chat_service

router = APIRouter(prefix="/conversations", tags=["conversations"], dependencies=[Depends(optional_auth)])


def _to_out(db: Session, conversation: Conversation) -> ConversationOut:
    messages = chat_service.messages(db, conversation.id, limit=1)
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=chat_service.message_count(db, conversation.id),
        preview=messages[0].content[:120] if messages else None,
    )


@router.get("", response_model=ConversationListResponse, summary="List recent conversations")
def list_conversations(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConversationListResponse:
    conversations = chat_service.list_conversations(db, limit=limit, offset=offset)
    return ConversationListResponse(
        conversations=[_to_out(db, conversation) for conversation in conversations],
        total=len(conversations),
    )


@router.post(
    "",
    response_model=ConversationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new conversation",
)
def create_conversation(
    payload: ConversationCreateRequest, db: Session = Depends(get_db)
) -> ConversationCreateResponse:
    conversation = Conversation(title=payload.title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationCreateResponse(conversation=_to_out(db, conversation))


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Full conversation with its messages and citations",
)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationDetail:
    conversation = chat_service.get_conversation(db, conversation_id)
    messages = chat_service.messages(db, conversation_id)
    return ConversationDetail(
        conversation=_to_out(db, conversation),
        messages=[MessageOut.model_validate(message) for message in messages],
    )


@router.patch(
    "/{conversation_id}",
    response_model=ConversationOut,
    summary="Rename a conversation",
)
def rename_conversation(
    conversation_id: str, payload: ConversationRenameRequest, db: Session = Depends(get_db)
) -> ConversationOut:
    conversation = chat_service.rename_conversation(db, conversation_id, payload.title)
    return _to_out(db, conversation)


@router.delete(
    "/{conversation_id}/messages",
    response_model=ConversationOut,
    summary="Clear the messages of a conversation, keeping the thread",
)
def clear_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationOut:
    conversation = chat_service.clear_conversation(db, conversation_id)
    return _to_out(db, conversation)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and its messages",
)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> None:
    chat_service.delete_conversation(db, conversation_id)
