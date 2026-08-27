"""PostgreSQL implementation of IdempotencyRepository."""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

import asyncpg


class PgIdempotencyRepository:
    """PostgreSQL-backed idempotency key store.

    Manages deduplication of write requests with a 24-hour TTL.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID, key: str) -> Optional[dict]:
        """Look up a non-expired idempotency record.

        Returns None if not found or expired.
        """
        row = await self._conn.fetchrow(
            """
            SELECT response_status, response_body, request_hash, endpoint, created_at
            FROM idempotency_keys
            WHERE user_id = $1 AND idempotency_key = $2 AND expires_at > NOW()
            """,
            user_id,
            key,
        )
        if row is None:
            return None
        return {
            "response_status": row["response_status"],
            "response_body": json.loads(row["response_body"]) if isinstance(row["response_body"], str) else row["response_body"],
            "request_hash": row["request_hash"],
            "endpoint": row["endpoint"],
            "created_at": row["created_at"],
        }

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
        """Store an idempotency response atomically.

        Raises asyncpg.UniqueViolationError if key already exists for this user.
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

    async def cleanup_expired(self) -> int:
        """Delete expired idempotency keys. Returns count removed."""
        result = await self._conn.execute(
            "DELETE FROM idempotency_keys WHERE expires_at < NOW()"
        )
        # asyncpg returns 'DELETE N'
        return int(result.split()[-1])
