"""Auth status endpoints.

HR Nexus protects write operations with a static bearer token
(``API_AUTH_TOKEN``) rather than a user account system: the deployment is
usually internal, single-tenant, and the token is issued by whoever administers
the HR knowledge base. The UI reads ``/api/auth/status`` to decide whether to
show the management controls, and stores the token in ``sessionStorage`` only —
no LLM or Qdrant credentials ever reach the browser.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.config import settings
from app.core.security import bearer_from_header, require_auth
from app.schemas import AuthStatusResponse, TokenRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/status",
    response_model=AuthStatusResponse,
    summary="Whether document management requires a token",
)
def auth_status(request: Request) -> AuthStatusResponse:
    configured = bool(settings.API_AUTH_TOKEN)
    presented = bool(bearer_from_header(request.headers.get("Authorization")))
    return AuthStatusResponse(
        auth_required=settings.auth_enforced,
        auth_configured=configured,
        verified=configured and presented,
    )


@router.post(
    "/verify",
    response_model=AuthStatusResponse,
    dependencies=[Depends(require_auth)],
    summary="Validate a management token",
)
def verify() -> AuthStatusResponse:
    return AuthStatusResponse(
        auth_required=settings.auth_enforced,
        auth_configured=bool(settings.API_AUTH_TOKEN),
        verified=True,
    )
