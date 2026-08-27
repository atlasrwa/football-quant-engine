"""PostgreSQL implementation of EventLogRepository."""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

import asyncpg

from src.persistence.repositories import EventRecord


class PgEventLogRepository:
    """PostgreSQL-backed append-only event log.

    Events are INSERT-only. UPDATE and DELETE are blocked by database triggers.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def append(self, event: EventRecord) -> int:
        """Append an event to the log. Returns the assigned sequential ID."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO event_log (event_type, event_version, aggregate_type, aggregate_id,
                                   actor_type, actor_id, payload, correlation_id, causation_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
            RETURNING id
            """,
            event.event_type,
            event.event_version,
            event.aggregate_type,
            event.aggregate_id,
            event.actor_type,
            event.actor_id,
            json.dumps(event.payload),
            event.correlation_id,
            event.causation_id,
        )
        return row["id"]

    async def get_by_aggregate(
        self, aggregate_type: str, aggregate_id: str, limit: int = 50
    ) -> List[dict]:
        """Get events for a specific aggregate, most recent first."""
        rows = await self._conn.fetch(
            """
            SELECT id, event_type, event_version, aggregate_type, aggregate_id,
                   actor_type, actor_id, payload, correlation_id, causation_id, created_at
            FROM event_log
            WHERE aggregate_type = $1 AND aggregate_id = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            aggregate_type,
            aggregate_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def get_by_correlation(self, correlation_id: UUID) -> List[dict]:
        """Get all events in a correlation group."""
        rows = await self._conn.fetch(
            """
            SELECT id, event_type, event_version, aggregate_type, aggregate_id,
                   actor_type, actor_id, payload, correlation_id, causation_id, created_at
            FROM event_log
            WHERE correlation_id = $1
            ORDER BY id ASC
            """,
            correlation_id,
        )
        return [dict(row) for row in rows]
