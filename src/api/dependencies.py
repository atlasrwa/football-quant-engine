"""FastAPI dependencies for authentication and database access.

Provides injectable dependencies that extract the authenticated user
from the JWT token and provide database connections with RLS context.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, Request

from src.auth.context import AuthContext
from src.auth.tokens import decode_access_token, TokenError
from src.api.errors import APIError, ErrorCodes


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> AuthContext:
    """Extract and validate the authenticated user from the Authorization header.

    The user_id and role come ONLY from the verified JWT token.
    They are NEVER accepted from request body or query parameters.

    Args:
        authorization: The Authorization header value (Bearer <token>).

    Returns:
        AuthContext with user_id and role.

    Raises:
        APIError(401): If token is missing, expired, or invalid.
    """
    if not authorization:
        raise APIError(
            status_code=401,
            code=ErrorCodes.UNAUTHENTICATED,
            message="Authorization header required",
        )

    # Extract token from "Bearer <token>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise APIError(
            status_code=401,
            code=ErrorCodes.UNAUTHENTICATED,
            message="Authorization header must be: Bearer <token>",
        )

    token = parts[1]
    try:
        payload = decode_access_token(token)
    except TokenError as e:
        raise APIError(
            status_code=401,
            code=ErrorCodes.UNAUTHENTICATED,
            message=str(e),
        )

    return AuthContext(
        user_id=UUID(payload["sub"]),
        role=payload["role"],
    )


async def get_optional_user(
    authorization: Optional[str] = Header(None),
) -> Optional[AuthContext]:
    """Optionally extract user from Authorization header.

    Returns None if no header is present (for public endpoints).
    Raises 401 if header is present but invalid.
    """
    if not authorization:
        return None
    # Delegate to required version
    return await get_current_user(Request(scope={"type": "http"}), authorization)
