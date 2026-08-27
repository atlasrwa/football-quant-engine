"""PostgreSQL repository for settlements (INSERT-only)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

import asyncpg


class PgSettlementRepository:
    """INSERT-only repository for settlement records.

    Settlements are immutable after creation (trigger enforced).
    prediction_id is UNIQUE (idempotent settlement — I14).
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        settlement_id: UUID,
        prediction_id: UUID,
        match_id: int,
        outcome: str,
        actual_total_goals: int,
        actual_result: str,
        entry_odds: Optional[float],
        closing_odds: Optional[float],
        clv_pct: Optional[float],
        stake: float,
        profit_loss: float,
        settled_at: datetime,
    ) -> dict:
        """Insert a settlement record. Returns the created record.

        Raises asyncpg.UniqueViolationError if prediction already settled (idempotent).
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO settlements (id, prediction_id, match_id, outcome,
                actual_total_goals, actual_result, entry_odds, closing_odds,
                clv_pct, stake, profit_loss, settled_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            RETURNING *
            """,
            settlement_id, prediction_id, match_id, outcome,
            actual_total_goals, actual_result, entry_odds, closing_odds,
            clv_pct, stake, profit_loss, settled_at,
        )
        return dict(row)

    async def get_by_prediction_id(self, prediction_id: UUID) -> Optional[dict]:
        """Get settlement for a prediction (idempotency check)."""
        row = await self._conn.fetchrow(
            "SELECT * FROM settlements WHERE prediction_id = $1", prediction_id
        )
        return dict(row) if row else None

    async def get_by_id(self, settlement_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM settlements WHERE id = $1", settlement_id
        )
        return dict(row) if row else None

    async def get_by_match(self, match_id: int) -> List[dict]:
        rows = await self._conn.fetch(
            "SELECT * FROM settlements WHERE match_id = $1 ORDER BY created_at",
            match_id,
        )
        return [dict(r) for r in rows]
