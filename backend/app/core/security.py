"""Security utilities: CORS, upload validation, auth, rate limiting.

Design notes
------------
* **CORS** is an explicit allow-list derived from ``FRONTEND_URL`` /
  ``CORS_ORIGINS``. Credentials are not allowed because the API is token
  authenticated rather than cookie authenticated.
* **Uploads** are validated on three axes: extension allow-list, size limit and
  content sniffing (magic bytes for PDF, decodability + NUL-byte rejection for
  text formats). The stored filename is always server generated.
* **Auth** is a static bearer token (``API_AUTH_TOKEN``) compared with
  ``secrets.compare_digest``. When it is unset, destructive routes are open in
  development but ``AUTH_REQUIRED`` (auto-true in production) makes the API fail
  closed with a clear 503 instead of silently exposing write endpoints.
* **Rate limiting** is an in-process sliding window. The interface is
  intentionally simple so it can be swapped for a Redis-backed implementation.
"""

from __future__ import annotations

import math
import re
import secrets
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import AppError, ProviderConfigurationError

PDF_MAGIC = b"%PDF"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06")


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #
def configure_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.CORS_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )


# --------------------------------------------------------------------------- #
# Filenames
# --------------------------------------------------------------------------- #
_UNSAFE_CHARS = re.compile(r"[^\w.\- ]")
_WHITESPACE = re.compile(r"\s+")


def sanitize_display_name(original: str) -> str:
    """Strip any path component from a user supplied filename (for display)."""
    cleaned = Path(original.replace("\\", "/")).name.strip()
    cleaned = _UNSAFE_CHARS.sub(" ", cleaned)
    return _WHITESPACE.sub(" ", cleaned)[:180] or "document"


def safe_filename(original: str) -> str:
    """Generate a safe, unique, fully server-controlled filename."""
    cleaned = _UNSAFE_CHARS.sub("", Path(original.replace("\\", "/")).name).strip()
    cleaned = _WHITESPACE.sub("-", cleaned) or "document"
    stem, _, suffix = cleaned.rpartition(".")
    if not stem:  # no extension present
        stem, suffix = cleaned, ""
    stem = stem[:80] or "document"
    suffix = suffix[:10]
    prefix = uuid.uuid4().hex[:12]
    return f"{prefix}_{stem}.{suffix}" if suffix else f"{prefix}_{stem}"


# --------------------------------------------------------------------------- #
# Upload validation
# --------------------------------------------------------------------------- #
def validate_upload(filename: str, content: bytes, content_type: str | None = None) -> tuple[str, str]:
    """Validate an upload and return ``(safe_name, extension)``.

    Raises :class:`AppError` with a user-safe message for every rejection.
    """
    ext = Path(filename or "").suffix.lower()

    if ext not in settings.ALLOWED_EXTENSIONS:
        allowed = ", ".join(settings.ALLOWED_EXTENSIONS)
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext or 'unknown'}'. Allowed types: {allowed}.",
            code="unsupported_file_type",
        )

    if not content:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
            code="empty_file",
        )

    if len(content) > settings.upload_size_limit_bytes:
        raise AppError(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit.",
            code="file_too_large",
        )

    if content_type and content_type.strip().lower() not in settings.ALLOWED_CONTENT_TYPES:
        raise AppError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content type '{content_type}' is not accepted.",
            code="unsupported_content_type",
        )

    if ext == ".pdf":
        if not content.startswith(PDF_MAGIC):
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File has a .pdf extension but is not a valid PDF.",
                code="invalid_pdf",
            )
    else:
        if content.startswith(ZIP_MAGICS) or b"\x00" in content[:4096]:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text documents must be plain UTF-8 text, not binary or archive data.",
                code="invalid_text_document",
            )
        try:
            content[:2048].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text documents must be encoded as UTF-8.",
                code="invalid_text_encoding",
            ) from exc

    return safe_filename(filename), ext


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def bearer_from_header(header: str | None) -> str:
    if not header or not header.lower().startswith("bearer "):
        return ""
    return header.split(" ", 1)[1].strip()


async def require_auth(request: Request) -> None:
    """Guard write operations. Fails closed when auth is required but unset."""
    configured = settings.API_AUTH_TOKEN

    if not configured:
        if settings.auth_enforced:
            raise ProviderConfigurationError(
                "API_AUTH_TOKEN is not configured on the server, so protected "
                "operations are disabled. Set API_AUTH_TOKEN or AUTH_REQUIRED=false."
            )
        return

    provided = bearer_from_header(request.headers.get("Authorization"))
    if not provided or not secrets.compare_digest(provided, configured):
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication token.",
            code="unauthorized",
        )


async def optional_auth(request: Request) -> None:
    """Validate the token when one is configured, but never block anonymous reads."""
    if settings.API_AUTH_TOKEN:
        provided = bearer_from_header(request.headers.get("Authorization"))
        if provided and not secrets.compare_digest(provided, settings.API_AUTH_TOKEN):
            raise AppError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
                code="unauthorized",
            )


# --------------------------------------------------------------------------- #
# Client identity
# --------------------------------------------------------------------------- #
def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Sliding-window, process-local rate limiter."""

    def __init__(self, limit_per_minute: int = 0, window_seconds: int = 60) -> None:
        self._window = window_seconds
        self._limit = max(0, limit_per_minute)
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, now: float | None = None) -> bool:
        if self._limit <= 0:
            return True
        now = time.time() if now is None else now
        window_start = now - self._window
        hits = [t for t in self._hits.get(key, []) if t > window_start]
        if len(hits) >= self._limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = time.time() if now is None else now
        hits = self._hits.get(key) or []
        if not hits:
            return 1
        return max(1, math.ceil(self._window - (now - min(hits))))

    def reset(self) -> None:
        self._hits.clear()


chat_rate_limiter = RateLimiter(settings.RATE_LIMIT_PER_MINUTE)
upload_rate_limiter = RateLimiter(settings.RATE_LIMIT_UPLOADS_PER_MINUTE)


def _enforce(limiter: RateLimiter, request: Request) -> None:
    key = client_ip(request)
    if limiter.check(key):
        return
    retry_after = limiter.retry_after(key)
    raise AppError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded. Please wait a moment and try again.",
        code="rate_limited",
        headers={"Retry-After": str(retry_after)},
    )


async def rate_limit_dependency(request: Request) -> None:
    _enforce(chat_rate_limiter, request)


async def upload_rate_limit_dependency(request: Request) -> None:
    _enforce(upload_rate_limiter, request)
