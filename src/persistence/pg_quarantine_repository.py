"""PostgreSQL repository for quarantine_entries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import asyncpg


# 90-day quarantine period (matches QuarantineTracker.QUARANTINE_DAYS)
QUARANTINE_DAYS = 90


class PgQuarantineRepository:
    """Repository for version-specific quarantine lifecycle."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def enter(
        self,
        strategy_id: UUID,
        strategy_version: int,
        user_id: UUID,
    ) -> dict:
        """Enter a strategy version into quarantine. Returns the entry."""
        now = datetime.now(timezone.utc)
        quarantine_until = now + timedelta(days=QUARANTINE_DAYS)

        row = await self._conn.fetchrow(
            """
            INSERT INTO quarantine_entries (strategy_id, strategy_version, user_id,
                status, entered_at, quarantine_until)
            VALUES ($1, $2, $3, 'PENDING_QUARANTINE', $4, $5)
            ON CONFLICT (strategy_id, strategy_version) DO NOTHING
            RETURNING *
            """,
            strategy_id, strategy_version, user_id, now, quarantine_until,
        )
        if row:
            return dict(row)
        # Already exists — return existing
        return await self.get(strategy_id, strategy_version)

    async def get(self, strategy_id: UUID, strategy_version: int) -> Optional[dict]:
        """Get quarantine entry for a strategy version."""
        row = await self._conn.fetchrow(
            "SELECT * FROM quarantine_entries WHERE strategy_id = $1 AND strategy_version = $2",
            strategy_id, strategy_version,
        )
        return dict(row) if row else None

    async def promote(self, strategy_id: UUID, strategy_version: int) -> Optional[dict]:
        """Promote a quarantined strategy. Returns updated entry or None if not eligible."""
        row = await self._conn.fetchrow(
            """
            UPDATE quarantine_entries
            SET status = 'PROMOTED', promoted_at = NOW()
            WHERE strategy_id = $1 AND strategy_version = $2
              AND status = 'PENDING_QUARANTINE'
              AND quarantine_until <= NOW()
            RETURNING *
            """,
            strategy_id, strategy_version,
        )
        return dict(row) if row else None

    async def reject(self, strategy_id: UUID, strategy_version: int) -> Optional[dict]:
        """Reject a quarantined strategy."""
        row = await self._conn.fetchrow(
            """
            UPDATE quarantine_entries
            SET status = 'REJECTED', rejected_at = NOW()
            WHERE strategy_id = $1 AND strategy_version = $2
              AND status = 'PENDING_QUARANTINE'
            RETURNING *
            """,
            strategy_id, strategy_version,
        )
        return dict(row) if row else None

    async def update_paper_pnl(
        self, strategy_id: UUID, strategy_version: int,
        pnl_delta: float, bets_delta: int = 1
    ) -> None:
        """Update paper trading P&L for a quarantined strategy."""
        await self._conn.execute(
            """
            UPDATE quarantine_entries
            SET paper_pnl = paper_pnl + $3, paper_bets = paper_bets + $4
            WHERE strategy_id = $1 AND strategy_version = $2
              AND status = 'PENDING_QUARANTINE'
            """,
            strategy_id, strategy_version, pnl_delta, bets_delta,
        )

    async def get_by_user(self, user_id: UUID) -> list:
        """Get all quarantine entries for a user."""
        rows = await self._conn.fetch(
            "SELECT * FROM quarantine_entries WHERE user_id = $1 ORDER BY entered_at DESC",
            user_id,
        )
        return [dict(r) for r in rows]
