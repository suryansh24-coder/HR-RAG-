"""Chat orchestration: conversation persistence + RAG execution + telemetry."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models import Conversation, Message, QueryLog
from app.rag.pipeline import ChatResult, pipeline
from app.schemas.chat import SourceOut
from app.services.document_service import document_service

logger = get_logger(__name__)

MAX_TITLE_CHARS = 60
ELLIPSIS = "\u2026"

_STOPWORDS = frozenset(
    """a an the and or but if of to in on for with is are was were do does did have has
    had i you it we they what which who how why when where can could should would my our your
    their this that these those about from by as at be been will shall may might much many
    """.split()
)
_WORD = re.compile(r"[a-z0-9']+")
_TOPIC = re.compile(
    r"^\s*(?:\d+[.)]\s*)?(?P<topic>[A-Z][\w&/\- ]{4,60}?)\s*(?:\n|:)"
)


def _make_title(question: str) -> str:
    """Derive a short, readable conversation title from the first question."""
    title = " ".join(question.split())
    if not title:
        return "New conversation"
    if len(title) > MAX_TITLE_CHARS:
        return title[:MAX_TITLE_CHARS].rstrip() + ELLIPSIS
    return title


def _preview(text: str, limit: int = 90) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1] + ELLIPSIS


class ChatService:
    # ------------------------------------------------------------------ #
    # Conversations
    # ------------------------------------------------------------------ #
    def resolve_conversation(
        self, db: Session, conversation_id: str | None, question: str
    ) -> Conversation:
        if conversation_id:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None:
                raise NotFoundError("Conversation not found.")
            return conversation
        conversation = Conversation(title=_make_title(question))
        db.add(conversation)
        db.flush()
        return conversation

    def list_conversations(self, db: Session, limit: int = 50, offset: int = 0) -> list[Conversation]:
        return list(
            db.scalars(
                select(Conversation)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )

    def get_conversation(self, db: Session, conversation_id: str) -> Conversation:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        return conversation

    def delete_conversation(self, db: Session, conversation_id: str) -> None:
        conversation = self.get_conversation(db, conversation_id)
        db.delete(conversation)
        db.commit()

    def rename_conversation(self, db: Session, conversation_id: str, title: str) -> Conversation:
        conversation = self.get_conversation(db, conversation_id)
        conversation.title = " ".join(title.split())[:255] or "New conversation"
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(conversation)
        return conversation

    def clear_conversation(self, db: Session, conversation_id: str) -> Conversation:
        conversation = self.get_conversation(db, conversation_id)
        for message in list(conversation.messages):
            db.delete(message)
        db.flush()
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(conversation)
        return conversation

    def message_count(self, db: Session, conversation_id: str) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == conversation_id)
            )
            or 0
        )

    def messages(self, db: Session, conversation_id: str, limit: int = 200) -> list[Message]:
        return list(
            db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
                .limit(limit)
            )
        )

    def recent_history(self, db: Session, conversation_id: str) -> list[dict[str, str]]:
        """Recent turns used to resolve elliptical follow-up questions."""
        if settings.HISTORY_TURNS <= 0:
            return []
        rows = self.messages(db, conversation_id, limit=settings.HISTORY_TURNS * 4)
        history: list[dict[str, str]] = []
        for message in rows:
            if message.role == "user":
                history.append({"role": "user", "content": message.content})
        return history[-settings.HISTORY_TURNS * 2 :]

    # ------------------------------------------------------------------ #
    # Messaging
    # ------------------------------------------------------------------ #
    @staticmethod
    def _add_message(
        db: Session,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        no_context: bool = False,
        latency_ms: float | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
            no_context=no_context,
            latency_ms=latency_ms,
        )
        db.add(message)
        return message

    def persist_turn(
        self,
        db: Session,
        conversation: Conversation,
        question: str,
        result: ChatResult,
    ) -> Message:
        sources = [SourceOut(**source) for source in result.sources]
        self._add_message(db, conversation.id, "user", question)
        assistant = self._add_message(
            db,
            conversation.id,
            "assistant",
            result.answer,
            sources=[source.model_dump() for source in sources],
            no_context=result.no_context,
            latency_ms=result.trace.get("total_latency_ms") if result.trace else None,
        )
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(assistant)
        return assistant

    def log_query(
        self,
        db: Session,
        question: str,
        result: ChatResult,
        error: str | None = None,
    ) -> None:
        if not settings.QUERY_LOG_ENABLED:
            return
        trace = result.trace or {}
        db.add(
            QueryLog(
                question_preview=_preview(question, 150),
                grounded=result.context_used and not result.no_context,
                chunks_retrieved=result.retrieval_hits,
                top_score=(trace.get("retrieval_scores") or [None])[0],
                retrieval_latency_ms=trace.get("retrieval_latency_ms"),
                total_latency_ms=trace.get("total_latency_ms"),
                provider=settings.LLM_PROVIDER,
                error=(error or "")[:255] or None,
            )
        )
        db.commit()

    async def chat(
        self,
        db: Session,
        question: str,
        conversation_id: str | None = None,
        include_suggestions: bool = True,
    ) -> tuple[Conversation, Message, ChatResult, list[str]]:
        conversation = self.resolve_conversation(db, conversation_id, question)
        history = self.recent_history(db, conversation.id)

        try:
            result = await pipeline.query(question, history)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            self.log_query(db, question, ChatResult(answer=""), error=str(exc))
            raise

        assistant = self.persist_turn(db, conversation, question, result)
        self.log_query(db, question, result)
        suggestions = (
            self.suggest_follow_ups(question, result) if include_suggestions else []
        )
        return conversation, assistant, result, suggestions

    # ------------------------------------------------------------------ #
    # Follow-up suggestions (derived from retrieved context, never invented)
    # ------------------------------------------------------------------ #
    def suggest_follow_ups(
        self, question: str, result: ChatResult, limit: int = 3
    ) -> list[str]:
        """Build follow-up questions from the sources that were actually used.

        The suggestions are derived from headings and topic phrases inside the
        retrieved snippets (other policy areas in the same documents), so they
        always point at real knowledge the assistant can answer.
        """
        if not result.sources:
            return []

        asked = set(_WORD.findall(question.lower()))
        candidates: list[tuple[str, str]] = []  # (topic, filename)
        seen: set[str] = set()

        for source in result.sources:
            filename = str(source.get("filename", ""))
            snippet = str(source.get("snippet", ""))
            for match in _TOPIC.finditer(snippet):
                topic = " ".join(match.group("topic").split())
                key = topic.lower()
                if key in seen or len(topic) < 6:
                    continue
                overlap = asked & set(_WORD.findall(key))
                if len(overlap) >= max(1, len(asked) // 2):
                    continue
                seen.add(key)
                candidates.append((topic, filename))

        suggestions: list[str] = []
        for topic, filename in candidates:
            if len(suggestions) >= limit:
                break
            suggestions.append(f"What does the policy say about {topic.lower()}?")
        return suggestions


chat_service = ChatService()


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
class StatsService:
    """Aggregates real state for the dashboard and the knowledge view."""

    def document_counts(self, db: Session) -> dict[str, int]:
        return document_service.counts(db)

    def conversation_count(self, db: Session) -> int:
        return db.scalar(select(func.count()).select_from(Conversation)) or 0

    def message_count(self, db: Session) -> int:
        return db.scalar(select(func.count()).select_from(Message)) or 0

    def query_counts(self, db: Session) -> dict[str, int]:
        total = db.scalar(select(func.count()).select_from(QueryLog)) or 0
        grounded = (
            db.scalar(
                select(func.count())
                .select_from(QueryLog)
                .where(QueryLog.grounded.is_(True))
            )
            or 0
        )
        return {
            "total": total,
            "grounded": grounded,
            "no_context": total - grounded,
        }

    def last_query_at(self, db: Session) -> datetime | None:
        return db.scalar(select(func.max(QueryLog.created_at)))

    def recent_queries(self, db: Session, limit: int | None = None) -> list[QueryLog]:
        cap = min(limit or settings.QUERY_LOG_LIMIT, settings.QUERY_LOG_LIMIT)
        return list(
            db.scalars(
                select(QueryLog).order_by(QueryLog.created_at.desc()).limit(cap)
            )
        )


stats_service = StatsService()
