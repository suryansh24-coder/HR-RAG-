"""Embedding service built on Sentence-Transformers.

Design notes
------------
* The model is loaded lazily on first use (avoiding startup cost when the
  backend boots without a query).
* Embedding calls are thread-safe: callers use ``fastapi.concurrency.run_in_threadpool``
  so the async event loop is not blocked while the CPU-bound model runs.
* The **same** model instance embeds both documents and queries (requirement).
"""

from __future__ import annotations

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str | None = None, device: str | None = None) -> None:
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.device = device or settings.EMBEDDING_DEVICE
        self._model = None
        self._dimension: int | None = None

    def _ensure_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ServiceUnavailableError(
                    "Sentence-Transformers is not installed."
                ) from exc
            try:
                logger.info("Loading embedding model %s on %s", self.model_name, self.device)
                self._model = SentenceTransformer(self.model_name, device=self.device)
                # get_sentence_embedding_dimension() is deprecated in
                # sentence-transformers>=5 in favour of get_embedding_dimension().
                get_dimension = getattr(self._model, "get_embedding_dimension", None)
                if get_dimension is None:
                    get_dimension = self._model.get_sentence_embedding_dimension
                self._dimension = int(get_dimension())
                logger.info("Embedding model ready, dim=%s", self._dimension)
            except Exception as exc:  # noqa: BLE001
                raise ServiceUnavailableError(
                    f"Failed to load embedding model '{self.model_name}': {exc}"
                ) from exc

    @property
    def dimension(self) -> int:
        self._ensure_model()
        assert self._dimension is not None
        return self._dimension

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_model()
        if len(texts) < 200:
            vectors = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=False)
        else:
            vectors = self._model.encode(
                texts,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
                normalize_embeddings=True,
                convert_to_numpy=False,
            )
        return [list(map(float, v.tolist())) for v in vectors]

    def encode_query(self, query: str) -> list[float]:
        return self.encode([query])[0]


embedding_service = EmbeddingService()