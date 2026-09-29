"""Qdrant vector store adapter.

Two connection modes are supported and selected purely by configuration:

* **Server mode** — ``QDRANT_URL`` is an ``http(s)://`` endpoint (Qdrant Cloud,
  the bundled Docker service, or a self-hosted node). ``QDRANT_API_KEY`` is sent
  when present.
* **Local mode** — ``QDRANT_URL`` is ``local`` / empty. ``qdrant-client``'s
  embedded persistence is used at ``QDRANT_PATH`` so the full vector pipeline
  runs with zero external infrastructure.

The collection is **created once and reused**. On startup the adapter validates
the stored vector dimension against the current embedding model and only
recreates the collection when the model (and therefore the dimension) changed.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.rag.retrieval.scorer import stem

logger = get_logger(__name__)

_WORD = re.compile(r"[a-z0-9]+")

# --- payload keys (single source of truth, imported everywhere) --------------
PAYLOAD_DOCUMENT_ID = "document_id"
PAYLOAD_FILENAME = "filename"
PAYLOAD_PAGE = "page"
PAYLOAD_CHUNK_INDEX = "chunk_index"
PAYLOAD_SOURCE = "source"
PAYLOAD_DOCUMENT_TYPE = "document_type"
PAYLOAD_TEXT = "text"
PAYLOAD_UPLOADED_AT = "uploaded_at"
PAYLOAD_CHUNKS_TOTAL = "chunks_total"

_UPSERT_BATCH_SIZE = 128
_SCROLL_LIMIT = 10_000


class QdrantStore:
    """Thin, well-typed wrapper around the Qdrant client used by the RAG layer."""

    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        self.url = url if url is not None else settings.QDRANT_URL
        self.collection = collection or settings.QDRANT_COLLECTION
        self._client: QdrantClient | None = None
        self._local_path: Path | None = None
        self._corpus_terms: frozenset[str] | None = None
        self._corpus_signature: int | None = None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #
    def _connect(self) -> QdrantClient:
        if self._client is not None:
            return self._client

        try:
            if settings.qdrant_is_local:
                self._local_path = Path(settings.QDRANT_PATH)
                self._local_path.mkdir(parents=True, exist_ok=True)
                client = QdrantClient(path=str(self._local_path))
                mode = f"local persistence at {self._local_path}"
            else:
                kwargs: dict[str, Any] = {
                    "url": self.url,
                    "timeout": settings.QDRANT_TIMEOUT_SECONDS,
                }
                if settings.QDRANT_API_KEY:
                    kwargs["api_key"] = settings.QDRANT_API_KEY
                if settings.QDRANT_GRPC:
                    kwargs["prefer_grpc"] = True
                client = QdrantClient(**kwargs)
                mode = f"server at {self.url}"
        except Exception as exc:  # noqa: BLE001 - surfaced as a 503 to the caller
            raise ServiceUnavailableError(
                f"Could not connect to the vector database: {exc}"
            ) from exc

        self._client = client
        logger.info("Qdrant connected (%s), collection=%s", mode, self.collection)
        return client

    @property
    def client(self) -> QdrantClient:
        return self._connect()

    @property
    def mode(self) -> str:
        return "local" if settings.qdrant_is_local else "server"

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # ------------------------------------------------------------------ #
    # Health & collection management
    # ------------------------------------------------------------------ #
    def healthcheck(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            info = self.client.get_collections()
            return {
                "status": "ok",
                "mode": self.mode,
                "collection": self.collection,
                "collection_exists": any(c.name == self.collection for c in info.collections),
                "collections": len(info.collections),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "mode": self.mode,
                "collection": self.collection,
                "collection_exists": False,
                "error": str(exc)[:200],
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

    def collection_exists(self) -> bool:
        try:
            return any(
                c.name == self.collection for c in self.client.get_collections().collections
            )
        except Exception:  # noqa: BLE001
            return False

    def _vector_params(self, dimension: int) -> models.VectorParams:
        return models.VectorParams(size=dimension, distance=models.Distance.COSINE)

    def ensure_collection(self, dimension: int, recreate: bool = False) -> None:
        """Create the collection when missing; only recreate on dimension change."""
        client = self.client

        if not self.collection_exists():
            client.create_collection(
                collection_name=self.collection,
                vectors_config=self._vector_params(dimension),
            )
            logger.info(
                "Created Qdrant collection %s (dim=%s, distance=cosine)",
                self.collection,
                dimension,
            )
            return

        info = client.get_collection(self.collection)
        current = self._collection_dimension(info)

        if current is not None and current != dimension:
            logger.warning(
                "Embedding dimension changed (%s -> %s); recreating collection %s",
                current,
                dimension,
                self.collection,
            )
            client.recreate_collection(
                collection_name=self.collection,
                vectors_config=self._vector_params(dimension),
            )
            return

        if recreate:
            client.recreate_collection(
                collection_name=self.collection,
                vectors_config=self._vector_params(dimension),
            )

    @staticmethod
    def _collection_dimension(info: Any) -> int | None:
        params = getattr(getattr(info.config, "params", None), "vectors", None)
        if isinstance(params, models.VectorParams):
            return params.size
        if isinstance(params, dict) and params:
            first = next(iter(params.values()))
            return getattr(first, "size", None)
        return None

    def collection_info(self) -> dict[str, Any]:
        if not self.collection_exists():
            return {
                "name": self.collection,
                "exists": False,
                "status": "missing",
                "points_count": 0,
                "vectors_count": 0,
                "dimension": None,
                "distance": None,
            }
        try:
            info = self.client.get_collection(self.collection)
            return {
                "name": self.collection,
                "exists": True,
                "status": str(getattr(info, "status", "green")),
                "points_count": int(getattr(info, "points_count", 0) or 0),
                "vectors_count": int(
                    getattr(info, "vectors_count", getattr(info, "points_count", 0)) or 0
                ),
                "indexed_vectors_count": int(getattr(info, "indexed_vectors_count", 0) or 0),
                "dimension": self._collection_dimension(info),
                "distance": str(
                    getattr(
                        getattr(info.config.params.vectors, "distance", None)
                        if not isinstance(info.config.params.vectors, dict)
                        else next(iter(info.config.params.vectors.values())).distance,
                        "name",
                        "",
                    )
                    or ""
                )
                or None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"name": self.collection, "exists": True, "status": "error", "error": str(exc)[:200]}

    # ------------------------------------------------------------------ #
    # Write operations
    # ------------------------------------------------------------------ #
    def upsert_chunks(self, points: list[models.PointStruct]) -> int:
        if not points:
            return 0
        client = self.client
        for start in range(0, len(points), _UPSERT_BATCH_SIZE):
            batch = points[start : start + _UPSERT_BATCH_SIZE]
            client.upsert(collection_name=self.collection, points=batch, wait=True)
        return len(points)

    def delete_document(self, document_id: str) -> int:
        """Delete every vector belonging to a document. Returns the number deleted."""
        if not self.collection_exists():
            return 0
        before = self.count_for_document(document_id)
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=_document_filter(document_id)
            ),
            wait=True,
        )
        return before

    def delete_all(self) -> None:
        if self.collection_exists():
            self.client.delete_collection(self.collection)

    # ------------------------------------------------------------------ #
    # Read operations
    # ------------------------------------------------------------------ #
    def search(
        self,
        vector: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[models.ScoredPoint]:
        """Cosine similarity search. Uses ``score_threshold=None`` so that the
        retrieval layer can apply its own threshold and report the raw scores."""
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )
        return list(response.points)

    def count_vectors(self, exact: bool = True) -> int:
        if not self.collection_exists():
            return 0
        try:
            return int(self.client.count(collection_name=self.collection, exact=exact).count)
        except Exception:  # noqa: BLE001
            return 0

    def count_for_document(self, document_id: str) -> int:
        if not self.collection_exists():
            return 0
        try:
            return int(
                self.client.count(
                    collection_name=self.collection,
                    count_filter=_document_filter(document_id),
                    exact=True,
                ).count
            )
        except Exception:  # noqa: BLE001
            return 0

    def scroll_document(self, document_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return stored chunk payloads for a document (used by the UI detail view)."""
        if not self.collection_exists():
            return []
        try:
            records, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=_document_filter(document_id),
                limit=min(limit, _SCROLL_LIMIT),
                with_payload=True,
                with_vectors=False,
                order_by=models.OrderBy(key=PAYLOAD_CHUNK_INDEX),
            )
            return [dict(record.payload or {}) for record in records]
        except Exception as exc:  # noqa: BLE001
            logger.warning("scroll_document(%s) failed: %s", document_id, exc)
            return []

    def chunk_counts_by_document(self) -> dict[str, int]:
        """Aggregate the stored chunk count per document id."""
        counts: dict[str, int] = {}
        for payload in self._iter_payloads([PAYLOAD_DOCUMENT_ID]):
            doc_id = str(payload.get(PAYLOAD_DOCUMENT_ID, ""))
            if doc_id:
                counts[doc_id] = counts.get(doc_id, 0) + 1
        return counts

    def all_document_ids(self) -> set[str]:
        return {
            doc_id for doc_id in self.chunk_counts_by_document() if doc_id
        }

    def filenames_by_document(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for payload in self._iter_payloads([PAYLOAD_DOCUMENT_ID, PAYLOAD_FILENAME]):
            doc_id = str(payload.get(PAYLOAD_DOCUMENT_ID, ""))
            if doc_id and doc_id not in mapping:
                mapping[doc_id] = str(payload.get(PAYLOAD_FILENAME, "unknown"))
        return mapping

    def corpus_terms(self) -> frozenset[str]:
        """Every stemmed word that appears anywhere in the indexed corpus.

        Cached and invalidated by the vector count, which changes on every
        ingest or delete. This is what lets the assistant distinguish *"this chunk
        does not mention the topic"* (look elsewhere) from *"the knowledge base has
        never heard of the topic"* (refuse), which per-chunk scoring alone cannot
        tell apart.
        """
        signature = self.count_vectors()
        if self._corpus_terms is not None and self._corpus_signature == signature:
            return self._corpus_terms

        terms: set[str] = set()
        for payload in self._iter_payloads([PAYLOAD_TEXT]):
            for token in _WORD.findall(str(payload.get(PAYLOAD_TEXT, "")).lower()):
                if len(token) >= 3:
                    terms.add(stem(token))
        self._corpus_terms = frozenset(terms)
        self._corpus_signature = signature
        logger.info("corpus term index built: %d distinct terms", len(self._corpus_terms))
        return self._corpus_terms

    def _iter_payloads(self, keys: list[str]) -> Iterable[dict[str, Any]]:
        """Stream selected payload keys for every point in the collection."""
        if not self.collection_exists():
            return
        offset = None
        try:
            while True:
                records, offset = self.client.scroll(
                    collection_name=self.collection,
                    limit=1024,
                    offset=offset,
                    with_payload=keys,
                    with_vectors=False,
                )
                for record in records:
                    yield dict(record.payload or {})
                if offset is None:
                    return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qdrant payload stream failed: %s", exc)
            return


def _document_filter(document_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key=PAYLOAD_DOCUMENT_ID,
                match=models.MatchValue(value=document_id),
            )
        ]
    )


def build_point_id(document_id: str, chunk_index: int) -> str:
    """Deterministic point id so re-indexing overwrites instead of duplicating."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"hr-nexus:{document_id}:{chunk_index}").hex


def build_payload(
    *,
    document_id: str,
    filename: str,
    document_type: str,
    uploaded_at: str,
    page: int,
    chunk_index: int,
    text: str,
    chunks_total: int,
) -> dict[str, Any]:
    """Metadata stored alongside every vector."""
    return {
        PAYLOAD_DOCUMENT_ID: document_id,
        PAYLOAD_FILENAME: filename,
        PAYLOAD_PAGE: page,
        PAYLOAD_CHUNK_INDEX: chunk_index,
        PAYLOAD_SOURCE: f"{filename} · page {page}",
        PAYLOAD_DOCUMENT_TYPE: document_type,
        PAYLOAD_TEXT: text,
        PAYLOAD_UPLOADED_AT: uploaded_at,
        PAYLOAD_CHUNKS_TOTAL: chunks_total,
    }


vector_store = QdrantStore()
