"""PostgreSQL repository for broadcast_logs.

Append-only delivery audit records. One prediction → many broadcasts
(one per channel/destination). Idempotent via UNIQUE constraint on
(prediction_id, channel, destination).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

import asyncpg


class PgBroadcastRepository:
    """Repository for immutable broadcast delivery records."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        broadcast_id: UUID,
        user_id: UUID,
        prediction_id: UUID,
        channel: str,
        status: str,
        payload_hash: str,
        destination: Optional[str] = None,
        deep_link: Optional[str] = None,
        dispatched_at: Optional[datetime] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> dict:
        """Create a broadcast log entry.

        Idempotent via unique index on (prediction_id, channel, COALESCE(destination, '')).
        Returns the existing record if duplicate.

        Args:
            broadcast_id: Pre-generated UUID for the broadcast record.
            user_id: Owner of the prediction being broadcast.
            prediction_id: The prediction being broadcast.
            channel: Delivery channel (web, mobile, telegram, etc.).
            status: Initial status (PENDING, DISPATCHED, DELIVERED, FAILED).
            payload_hash: SHA-256 of canonical broadcast payload.
            destination: Channel-specific address (optional).
            deep_link: Stable public reference URL.
            dispatched_at: When dispatch occurred (None if PENDING).
            error_code: Error code if FAILED.
            error_message: Error details if FAILED.

        Returns:
            The created or existing broadcast record dict.
        """
        # Check for existing broadcast (idempotency)
        existing = await self.get_by_prediction_channel(prediction_id, channel, destination)
        if existing:
            return existing

        try:
            row = await self._conn.fetchrow(
                """
                INSERT INTO broadcast_logs (
                    id, user_id, prediction_id, channel, destination,
                    status, payload_hash, deep_link, dispatched_at,
                    error_code, error_message
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING *
                """,
                broadcast_id, user_id, prediction_id, channel, destination,
                status, payload_hash, deep_link, dispatched_at,
                error_code, error_message,
            )
            return dict(row)
        except asyncpg.UniqueViolationError:
            # Race condition: another request inserted first
            return await self.get_by_prediction_channel(prediction_id, channel, destination)

    async def get_by_id(self, broadcast_id: UUID) -> Optional[dict]:
        """Get a broadcast record by ID."""
        row = await self._conn.fetchrow(
            "SELECT * FROM broadcast_logs WHERE id = $1",
            broadcast_id,
        )
        return dict(row) if row else None

    async def get_by_prediction(self, prediction_id: UUID) -> list[dict]:
        """Get all broadcasts for a prediction."""
        rows = await self._conn.fetch(
            "SELECT * FROM broadcast_logs WHERE prediction_id = $1 ORDER BY created_at DESC",
            prediction_id,
        )
        return [dict(r) for r in rows]

    async def get_by_prediction_channel(
        self, prediction_id: UUID, channel: str, destination: Optional[str] = None,
    ) -> Optional[dict]:
        """Get a broadcast by prediction + channel + destination (unique key)."""
        if destination is None:
            row = await self._conn.fetchrow(
                """
                SELECT * FROM broadcast_logs
                WHERE prediction_id = $1 AND channel = $2 AND destination IS NULL
                """,
                prediction_id, channel,
            )
        else:
            row = await self._conn.fetchrow(
                """
                SELECT * FROM broadcast_logs
                WHERE prediction_id = $1 AND channel = $2 AND destination = $3
                """,
                prediction_id, channel, destination,
            )
        return dict(row) if row else None

    async def get_by_user(
        self, user_id: UUID, limit: int = 50, status: Optional[str] = None,
    ) -> list[dict]:
        """Get broadcast history for a user."""
        if status:
            rows = await self._conn.fetch(
                """
                SELECT * FROM broadcast_logs
                WHERE user_id = $1 AND status = $2
                ORDER BY created_at DESC LIMIT $3
                """,
                user_id, status, limit,
            )
        else:
            rows = await self._conn.fetch(
                """
                SELECT * FROM broadcast_logs
                WHERE user_id = $1
                ORDER BY created_at DESC LIMIT $2
                """,
                user_id, limit,
            )
        return [dict(r) for r in rows]
