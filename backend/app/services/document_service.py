"""Document lifecycle service.

Owns the full document state machine:

``pending → processing → ready`` (indexed)  or  ``pending/processing → failed``

Files are stored on disk under ``data/documents/<shard>/<server-generated-name>``
and their vectors in Qdrant. The relational row is the source of truth for the
status the UI renders, so the frontend never has to guess.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import InternalError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import sanitize_display_name, validate_upload
from app.database.session import session_scope
from app.models import Document
from app.rag.loaders.index import extract_and_clean
from app.rag.pipeline import pipeline
from app.rag.vector_store.qdrant_store import vector_store

logger = get_logger(__name__)

DOCUMENTS_DIR: Path = settings.DATA_DIR
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

_ERROR_MAX_CHARS = 1000


class DocumentService:
    # ------------------------------------------------------------------ #
    # Storage helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _bucket_for(document_id: str) -> Path:
        bucket = DOCUMENTS_DIR / document_id[:2]
        bucket.mkdir(parents=True, exist_ok=True)
        return bucket

    @staticmethod
    def stored_path_for(document_id: str, stored_name: str) -> Path:
        return DocumentService._bucket_for(document_id) / stored_name

    def stored_path(self, record: Document) -> Path:
        return self._bucket_for(record.id) / record.stored_name

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #
    def persist_upload(self, db: Session, filename: str, content: bytes) -> Document:
        """Validate and store the file, returning a ``pending`` document row."""
        safe_name, ext = validate_upload(filename, content)
        record = Document(
            filename=sanitize_display_name(filename),
            stored_name=safe_name,
            document_type=ext.lstrip(".").replace("markdown", "md"),
            size_bytes=len(content),
            status=STATUS_PENDING,
        )
        db.add(record)
        db.flush()
        self.stored_path(record).write_bytes(content)
        db.commit()
        db.refresh(record)
        logger.info("Stored document %s (%s, %d bytes)", record.id, record.filename, len(content))
        return record

    # ------------------------------------------------------------------ #
    # Processing
    # ------------------------------------------------------------------ #
    async def process(self, db: Session, document_id: str) -> Document:
        record = db.get(Document, document_id)
        if record is None:
            raise NotFoundError("Document not found.")
        if record.status == STATUS_PROCESSING:
            raise ValidationError("This document is already being indexed.")

        record.status = STATUS_PROCESSING
        record.error_message = None
        db.commit()

        started = time.perf_counter()
        try:
            path = self.stored_path(record)
            if not path.exists():
                raise ValidationError("The stored file for this document is missing.")

            extracted = extract_and_clean(
                str(path), record.filename, f".{record.document_type}"
            )
            record.page_count = len(extracted.pages)

            result = await pipeline.ingest(
                extracted,
                document_id=record.id,
                uploaded_at=_iso(record.uploaded_at),
                filename=record.filename,
            )

            record.chunk_count = result.chunks
            record.page_count = result.pages or record.page_count
            record.status = STATUS_READY
            record.indexed_at = datetime.now(timezone.utc)
            record.processing_time_ms = int((time.perf_counter() - started) * 1000)
            record.doc_metadata = {
                "embedding_dimension": result.dimension,
                "collection": vector_store.collection,
            }
            db.commit()
            logger.info("Document %s indexed (%d chunks)", record.id, record.chunk_count)
        except Exception as exc:  # noqa: BLE001
            record.status = STATUS_FAILED
            record.error_message = _short_error(exc)
            record.processing_time_ms = int((time.perf_counter() - started) * 1000)
            db.commit()
            logger.exception("Document %s failed to index", document_id)
            raise InternalError(record.error_message) from exc

        db.refresh(record)
        return record

    @staticmethod
    def process_in_background(document_id: str) -> None:
        """Index a document using a fresh session (used by background tasks/scripts)."""
        with session_scope() as db:
            try:
                asyncio.run(DocumentService().process(db, document_id))
            except Exception:  # noqa: BLE001 - status and error are persisted on the row
                pass

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, db: Session, document_id: str) -> Document:
        record = db.get(Document, document_id)
        if record is None:
            raise NotFoundError("Document not found.")
        return record

    def list(
        self,
        db: Session,
        status: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Document]:
        stmt = select(Document)
        if status:
            stmt = stmt.where(Document.status == status)
        if search:
            stmt = stmt.where(Document.filename.ilike(f"%{search.strip()}%"))
        stmt = stmt.order_by(Document.uploaded_at.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt))

    def counts(self, db: Session) -> dict[str, int]:
        rows = db.execute(
            select(Document.status, func.count()).group_by(Document.status)
        ).all()
        counts = {status: 0 for status in (STATUS_PENDING, STATUS_PROCESSING, STATUS_READY, STATUS_FAILED)}
        for status, count in rows:
            counts[status] = int(count)
        counts["total"] = sum(counts.values())
        return counts

    def last_indexed_at(self, db: Session) -> datetime | None:
        return db.scalar(select(func.max(Document.indexed_at)))

    def detail(self, db: Session, document_id: str) -> tuple[Document, list[dict[str, Any]], int]:
        record = self.get(db, document_id)
        payloads = vector_store.scroll_document(document_id, limit=25)
        collection_chunks = vector_store.count_for_document(document_id)
        chunks = [
            {
                "chunk_index": int(p.get("chunk_index", index)),
                "page": int(p.get("page", 1) or 1),
                "text": str(p.get("text", "")),
                "citation": str(p.get("source", record.filename)),
            }
            for index, p in enumerate(payloads)
        ]
        return record, chunks, collection_chunks

    def resolve_file(self, db: Session, document_id: str) -> tuple[Document, Path]:
        record = self.get(db, document_id)
        path = self.stored_path(record)
        if not path.exists():
            raise NotFoundError("The stored file for this document is no longer available.")
        return record, path

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #
    async def delete(self, db: Session, document_id: str) -> int:
        record = self.get(db, document_id)
        try:
            removed = await pipeline.delete_document(document_id)
        except Exception as exc:  # noqa: BLE001 - never block a delete on Qdrant
            logger.warning("Could not delete vectors for %s: %s", document_id, exc)
            removed = 0

        bucket = DOCUMENTS_DIR / record.id[:2]
        stored = self.stored_path(record)
        if stored.exists():
            stored.unlink(missing_ok=True)
        # Only prune the shard once it is genuinely empty. Removing the whole
        # directory unconditionally deletes every *other* document that happens
        # to share the same two-character id prefix.
        if bucket.exists() and not any(bucket.iterdir()):
            shutil.rmtree(bucket, ignore_errors=True)

        db.delete(record)
        db.commit()
        logger.info("Deleted document %s (%d vectors)", document_id, removed)
        return removed

    async def reindex(self, db: Session, document_id: str) -> Document:
        record = self.get(db, document_id)
        try:
            await pipeline.delete_document(document_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not clear vectors for %s: %s", document_id, exc)

        record.status = STATUS_PENDING
        record.chunk_count = 0
        record.page_count = 0
        record.indexed_at = None
        record.error_message = None
        db.commit()
        return await self.process(db, document_id)

    def reindex_in_background(self, document_id: str) -> None:
        """Re-index in a fresh session so the request never blocks on embedding."""
        with session_scope() as db:
            try:
                asyncio.run(DocumentService().reindex(db, document_id))
            except Exception:  # noqa: BLE001 - status and error are persisted on the row
                pass


def _iso(value: datetime | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.isoformat()


def _short_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:_ERROR_MAX_CHARS]


document_service = DocumentService()
