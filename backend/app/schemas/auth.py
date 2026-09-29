"""Authentication schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class AuthStatusResponse(BaseModel):
    """Describes the auth mode so the UI can render the right controls."""

    auth_required: bool
    auth_configured: bool
    verified: bool = False
