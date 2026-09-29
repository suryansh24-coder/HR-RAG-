"""Shared schema primitives."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocumentStatus = Literal["pending", "processing", "ready", "failed"]
HealthStatus = Literal["ok", "degraded", "error"]


class MessageResponse(BaseModel):
    detail: str = "OK"


class MetaResponse(BaseModel):
    """Capability flags so the frontend never has to hard-code backend behaviour."""

    detail: str
    version: str
    environment: str
    api_prefix: str
    features: dict[str, object] = Field(default_factory=dict)


class HealthComponent(BaseModel):
    status: Literal["ok", "error"] = "ok"
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: HealthStatus
    app: str
    version: str
    environment: str
    components: dict[str, HealthComponent]


class ErrorResponse(BaseModel):
    """Uniform error body returned by every endpoint."""

    detail: str
    code: str = "error"


class Page(BaseModel):
    """Generic pagination envelope."""

    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
