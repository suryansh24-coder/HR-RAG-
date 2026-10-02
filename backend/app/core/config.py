"""Application settings loaded from environment variables.

All secrets and tunables are configured via environment variables (or a ``.env``
file in the project root). Nothing sensitive is hard-coded. See ``.env.example``
for the full, documented list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App -----------------------------------------------------------
    APP_NAME: str = "HR Nexus"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    API_PREFIX: str = "/api"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # --- URLs / CORS ---------------------------------------------------
    API_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: list[str] = Field(default_factory=list)
    TRUST_PROXY_HEADERS: bool = False

    # --- Storage -------------------------------------------------------
    DATA_DIR: Path = PROJECT_ROOT / "data" / "documents"
    QDRANT_PATH: Path = PROJECT_ROOT / "data" / "qdrant"
    MAX_UPLOAD_SIZE_MB: int = 20

    # --- Qdrant --------------------------------------------------------
    QDRANT_URL: str = "local"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "hr_documents"
    QDRANT_GRPC: bool = False
    QDRANT_TIMEOUT_SECONDS: int = 20

    # --- Embeddings ----------------------------------------------------
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_BATCH_SIZE: int = 16

    # --- RAG -----------------------------------------------------------
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120
    TOP_K: int = 4
    # Minimum *hybrid* relevance (see app/rag/retrieval/scorer.py) for a chunk to
    # reach the prompt. Calibrated with `python -m evaluation.evaluate_rag`: the
    # 26 answerable questions score 0.61-0.89 and the 6 unanswerable ones 0.00-0.56,
    # so 0.58 sits in the middle of the widest gap between the two classes. Re-run
    # the evaluation after changing the corpus, the chunker or the embeddings.
    SCORE_THRESHOLD: float = 0.58
    # Weight of cosine similarity in the hybrid score (1 - alpha = lexical weight).
    HYBRID_ALPHA: float = 0.65
    # How many candidates the vector store returns *before* hybrid re-ranking.
    # Pure cosine ranks the wrong chunk first for questions whose answer sentence
    # shares no wording with the question ("how many paid leave days" -> the
    # sentence that states "18 days of paid annual leave"), so the re-ranker needs
    # a deeper pool than the final top_k.
    RETRIEVAL_CANDIDATES: int = 30
    MAX_CHUNKS_PER_DOCUMENT: int = 2
    MAX_CONTEXT_CHUNKS: int = 6
    HISTORY_TURNS: int = 2

    # --- LLM -----------------------------------------------------------
    LLM_PROVIDER: str = "extractive"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 600
    LLM_TIMEOUT_SECONDS: int = 60

    # --- Insufficient-knowledge behaviour -------------------------------
    NO_CONTEXT_RESPONSE: str = (
        "I couldn't find sufficient information about this topic in the HR knowledge base. "
        "Please contact HR or try rephrasing your question."
    )

    # --- Database ------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./data/hr_nexus.db"
    DB_ECHO: bool = False

    # --- Security ------------------------------------------------------
    API_AUTH_TOKEN: str = ""
    AUTH_REQUIRED: bool | None = None
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_UPLOADS_PER_MINUTE: int = 10
    ALLOWED_EXTENSIONS: tuple[str, ...] = (".pdf", ".txt", ".md", ".markdown")
    ALLOWED_CONTENT_TYPES: tuple[str, ...] = (
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/octet-stream",
    )

    # --- Observability -------------------------------------------------
    RAG_DEBUG: bool = False
    QUERY_LOG_ENABLED: bool = True
    QUERY_LOG_LIMIT: int = 200

    # --- Evaluation ----------------------------------------------------
    EVAL_TOP_K: int = 2

    # --- Validators ----------------------------------------------------
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        """Accept ``CORS_ORIGINS`` as a JSON array or a comma separated string."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ALLOWED_EXTENSIONS", "ALLOWED_CONTENT_TYPES", mode="before")
    @classmethod
    def _split_tuples(cls, value: Any) -> Any:
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _finalise(self) -> "Settings":
        if not self.CORS_ORIGINS:
            self.CORS_ORIGINS = [self.FRONTEND_URL]
        if self.AUTH_REQUIRED is None:
            # Destructive operations must be protected once deployed publicly.
            self.AUTH_REQUIRED = self.is_production
        if self.CHUNK_OVERLAP >= self.CHUNK_SIZE:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        if self.TOP_K < 1:
            raise ValueError("TOP_K must be at least 1.")
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return self

    # --- Derived properties ---------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV.lower() in ("test", "testing")

    @property
    def upload_size_limit_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def auth_enforced(self) -> bool:
        """True when protected routes must present a bearer token."""
        return bool(self.API_AUTH_TOKEN) or bool(self.AUTH_REQUIRED)

    @property
    def qdrant_is_local(self) -> bool:
        return (self.QDRANT_URL or "local").strip().lower() in ("", "local", "memory")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
