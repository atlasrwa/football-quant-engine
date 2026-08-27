"""Correlation ID middleware.

Assigns a unique request_id to every incoming request for tracing.
The ID is available via request.state.request_id and returned in
the X-Request-ID response header.
"""

from __future__ import annotations

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Attach a correlation/request ID to each request.

    If the client sends X-Request-ID, it is preserved.
    Otherwise, a new UUID is generated.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided ID or generate one
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
