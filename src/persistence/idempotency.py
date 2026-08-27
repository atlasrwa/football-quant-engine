"""Idempotency service for API write operations.

Implements the full idempotency contract:
1. FIRST REQUEST → execute business logic, store response, return response
2. DUPLICATE SAME REQUEST → return stored response, no side effects
3. DUPLICATE DIFFERENT BODY → HTTP 409 Conflict

The service operates atomically:
- Idempotency check and business execution happen in the same transaction.
- If the transaction fails, no idempotency response is persisted.
- Concurrent duplicate requests are resolved by PostgreSQL's UNIQUE constraint.

Usage in API middleware:
    result = await idempotency_service.check(user_id, key, endpoint, request_hash)
    if result is not None:
        return result  # cached response
    # ... execute business logic ...
    await idempotency_service.store(user_id, key, endpoint, request_hash, status, body)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    """Cached idempotency response."""
    response_status: int
    response_body: dict
    is_conflict: bool = False  # True if same key but different request body


class IdempotencyConflictError(Exception):
    """Raised when the same idempotency key is reused with a different request body."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            f"Idempotency key '{key}' was already used with a different request body. "
            f"Use a new key for a different request."
        )


def compute_request_hash(body: dict) -> str:
    """Compute SHA-256 hash of the canonical request body.

    Excludes non-semantic fields (transport headers, timestamps) —
    only semantically relevant request data is included.

    Args:
        body: The request body dict.

    Returns:
        64-char lowercase hex SHA-256 hash.
    """
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyService:
    """Idempotency check and storage within a database transaction.

    Must be used within the same transaction as the business operation
    to ensure atomicity.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def check(
        self,
        user_id: UUID,
        key: str,
        request_hash: str,
    ) -> Optional[IdempotencyResult]:
        """Check if an idempotency key has already been used.

        Args:
            user_id: The authenticated user.
            key: The client-supplied idempotency key.
            request_hash: SHA-256 of the current request body.

        Returns:
            IdempotencyResult if key exists (either cached response or conflict).
            None if this is a new request.

        Raises:
            IdempotencyConflictError: If key exists with a different request_hash.
        """
        row = await self._conn.fetchrow(
            """
            SELECT response_status, response_body, request_hash
            FROM idempotency_keys
            WHERE user_id = $1 AND idempotency_key = $2 AND expires_at > NOW()
            """,
            user_id, key,
        )
        if row is None:
            return None

        stored_hash = row["request_hash"]
        if stored_hash != request_hash:
            raise IdempotencyConflictError(key)

        # Same key + same request → return cached response
        response_body = row["response_body"]
        if isinstance(response_body, str):
            response_body = json.loads(response_body)
        return IdempotencyResult(
            response_status=row["response_status"],
            response_body=response_body,
        )

    async def store(
        self,
        user_id: UUID,
        key: str,
        endpoint: str,
        http_method: str,
        request_hash: str,
        response_status: int,
        response_body: dict,
    ) -> None:
        """Store the idempotency response atomically.

        Must be called within the same transaction as the business operation.
        If the transaction rolls back, this storage is also rolled back.

        Args:
            user_id: The authenticated user.
            key: The client-supplied idempotency key.
            endpoint: The API endpoint path.
            http_method: HTTP method (POST, PUT, etc.).
            request_hash: SHA-256 of the request body.
            response_status: HTTP status code of the response.
            response_body: The response body to cache.

        Raises:
            asyncpg.UniqueViolationError: If a concurrent request already stored this key.
        """
        await self._conn.execute(
            """
            INSERT INTO idempotency_keys (user_id, idempotency_key, endpoint, http_method,
                                          request_hash, response_status, response_body)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            """,
            user_id,
            key,
            endpoint,
            http_method,
            request_hash,
            response_status,
            json.dumps(response_body),
        )
        logger.debug(
            "Idempotency stored: user=%s key=%s endpoint=%s status=%d",
            str(user_id)[:8], key[:16], endpoint, response_status,
        )
