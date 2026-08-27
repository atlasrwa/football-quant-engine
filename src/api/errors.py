"""Standardized API error model.

All API errors return a consistent JSON structure:
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human-readable description",
        "details": { ... optional context ... }
    },
    "request_id": "correlation-uuid"
}

PostgreSQL internals are NEVER leaked to clients.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


# ═══════════════════════════════════════════════════════════════════
# ERROR CODES
# ═══════════════════════════════════════════════════════════════════

class ErrorCodes:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ═══════════════════════════════════════════════════════════════════
# ERROR RESPONSE BUILDER
# ═══════════════════════════════════════════════════════════════════

def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> JSONResponse:
    """Build a standardized error response.

    Args:
        status_code: HTTP status code.
        code: Machine-readable error code from ErrorCodes.
        message: Human-readable error description.
        request_id: Correlation ID for tracing.
        details: Optional additional context.

    Returns:
        JSONResponse with consistent error structure.
    """
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        body["error"]["details"] = details
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=body)


class APIError(HTTPException):
    """Base API exception with structured error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(status_code=status_code, detail=message)
