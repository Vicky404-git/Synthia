"""Structured error types and consistent API error payloads."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class SynthiaError(Exception):
    """Base application error.

    ``code`` is a stable machine-readable identifier the frontend can branch on.
    ``status_code`` maps to the HTTP response status.
    ``details`` must never contain secrets or stack traces.
    """

    code = "synthia_error"
    status_code = 400

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ValidationError(SynthiaError):
    code = "validation_error"
    status_code = 422


class UnknownToolError(SynthiaError):
    code = "unknown_tool"
    status_code = 400


class InvalidToolArgumentsError(SynthiaError):
    code = "invalid_tool_arguments"
    status_code = 422


class PermissionDeniedError(SynthiaError):
    code = "permission_denied"
    status_code = 403


class UnauthorizedError(SynthiaError):
    code = "unauthorized"
    status_code = 401


class ConfirmationRequiredError(SynthiaError):
    code = "confirmation_required"
    status_code = 409


class ProviderNotConfiguredError(SynthiaError):
    code = "provider_not_configured"
    status_code = 400


class InvalidLLMConfigError(SynthiaError):
    """A request-scoped (BYOK) LLM configuration is missing or invalid.

    Details never include the API key itself.
    """

    code = "invalid_llm_config"
    status_code = 400


class ProviderError(SynthiaError):
    code = "provider_error"
    status_code = 502


class RateLimitedError(SynthiaError):
    code = "rate_limited"
    status_code = 429


async def synthia_error_handler(_: Request, exc: SynthiaError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Never leak stack traces or internal details to the client.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected internal error occurred.",
                "details": {"type": type(exc).__name__},
            }
        },
    )
