"""Pydantic API schemas (request/response models).

Schemas are grouped by domain and re-exported here so route modules can use a
single stable import path: ``from app.schemas import ChatRequest, DocumentOut``.
"""

from app.schemas.auth import AuthStatusResponse, TokenRequest
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    FollowUpRequest,
    FollowUpResponse,
    SourceOut,
    StreamStage,
)
from app.schemas.common import (
    DocumentStatus,
    ErrorResponse,
    HealthComponent,
    HealthResponse,
    HealthStatus,
    MessageResponse,
    MetaResponse,
)
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
    ConversationRenameRequest,
    MessageOut,
)
from app.schemas.documents import (
    DocumentChunkOut,
    DocumentDetail,
    DocumentListResponse,
    DocumentOut,
    ReindexResponse,
    UploadResponse,
)
from app.schemas.rag import (
    CollectionInfo,
    QueryLogListResponse,
    QueryLogOut,
    RagConfigOut,
    RagStatsResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)

__all__ = [
    "AuthStatusResponse",
    "ChatRequest",
    "ChatResponse",
    "CollectionInfo",
    "ConversationCreateRequest",
    "ConversationCreateResponse",
    "ConversationDetail",
    "ConversationListResponse",
    "ConversationOut",
    "ConversationRenameRequest",
    "DocumentChunkOut",
    "DocumentDetail",
    "DocumentListResponse",
    "DocumentOut",
    "DocumentStatus",
    "ErrorResponse",
    "FollowUpRequest",
    "FollowUpResponse",
    "HealthComponent",
    "HealthResponse",
    "HealthStatus",
    "MessageOut",
    "MessageResponse",
    "MetaResponse",
    "QueryLogListResponse",
    "QueryLogOut",
    "RagConfigOut",
    "RagStatsResponse",
    "ReindexResponse",
    "SearchHit",
    "SearchRequest",
    "SearchResponse",
    "SourceOut",
    "StreamStage",
    "TokenRequest",
    "UploadResponse",
]

