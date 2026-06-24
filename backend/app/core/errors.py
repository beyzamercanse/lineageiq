"""Domain exceptions and centralized API error handling.

API responses never expose stack traces (CLAUDE.md rule).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger(__name__)


class LineageIQError(Exception):
    """Base domain error."""

    status_code = 400
    code = "lineageiq_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(LineageIQError):
    status_code = 404
    code = "not_found"


class ValidationError(LineageIQError):
    status_code = 422
    code = "validation_error"


class ToolSafetyError(LineageIQError):
    """Raised when an agent tool input violates a safety constraint."""

    status_code = 400
    code = "tool_safety_error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LineageIQError)
    async def _handle_domain_error(_request: Request, exc: LineageIQError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # Log full detail server-side; return a generic message to the client.
        log.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}},
        )
