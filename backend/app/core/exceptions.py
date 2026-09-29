"""Domain exceptions.

Every error surfaced by the API is an :class:`AppError`, which guarantees a
human-readable ``detail`` string and a machine-readable ``code``. Stack traces
are never returned to clients.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    """HTTP exception with a machine-readable error code."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str = "error",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


class NotFoundError(AppError):
    def __init__(self, detail: str = "Resource not found.") -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail, code="not_found")


class ValidationError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            code="validation_error",
        )


class ServiceUnavailableError(AppError):
    def __init__(self, detail: str = "A required service is unavailable.") -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            code="service_unavailable",
        )


class ProviderConfigurationError(AppError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            code="provider_configuration_error",
        )


class InternalError(AppError):
    def __init__(self, detail: str = "Internal server error.") -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            code="internal_error",
        )


class AuthenticationError(AppError):
    def __init__(self, detail: str = "Authentication required.") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            code="unauthorized",
        )


class ForbiddenError(AppError):
    def __init__(self, detail: str = "You do not have permission to perform this action.") -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            code="forbidden",
        )


class TimeoutError_(AppError):
    def __init__(self, detail: str = "The request timed out. Please try again.") -> None:
        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=detail,
            code="timeout",
        )


def to_payload(exc: AppError) -> dict[str, Any]:
    return {"detail": exc.detail, "code": exc.code}
