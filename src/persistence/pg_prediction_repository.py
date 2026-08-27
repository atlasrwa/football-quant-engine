"""PostgreSQL repository for predictions."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

import asyncpg


class PgPredictionRepository:
    """Repository for prediction records.

    Predictions are created with server-computed proof_hash.
    Only status + settled_at are mutable after creation.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        prediction_id: UUID,
        user_id: UUID,
        strategy_id: UUID,
        strategy_version: int,
        strategy_content_hash: str,
        match_id: int,
        match_date_unix: int,
        home_team: str,
        away_team: str,
        league_id: int,
        market_type: str,
        direction: str,
        entry_odds: Optional[float],
        model_edge_pct: float,
        confidence: float,
        recommended_stake: float,
        source: str,
        proof_hash: str,
        market_line: Optional[float] = None,
        model_version_id: Optional[UUID] = None,
    ) -> dict:
        """Insert a new prediction. Returns the created record."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO predictions (id, user_id, strategy_id, strategy_version,
                strategy_content_hash, model_version_id, match_id, match_date_unix,
                home_team, away_team, league_id, market_type, market_line,
                direction, entry_odds, model_edge_pct, confidence,
                recommended_stake, source, proof_hash)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            RETURNING *
            """,
            prediction_id, user_id, strategy_id, strategy_version,
            strategy_content_hash, model_version_id, match_id, match_date_unix,
            home_team, away_team, league_id, market_type, market_line,
            direction, entry_odds, model_edge_pct, confidence,
            recommended_stake, source, proof_hash,
        )
        return dict(row)

    async def get_by_id(self, prediction_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM predictions WHERE id = $1", prediction_id
        )
        return dict(row) if row else None

    async def get_pending_for_match(self, match_id: int) -> List[dict]:
        """Get all PENDING predictions for a match (for settlement)."""
        rows = await self._conn.fetch(
            "SELECT * FROM predictions WHERE match_id = $1 AND status = 'PENDING'",
            match_id,
        )
        return [dict(r) for r in rows]

    async def get_by_user(self, user_id: UUID, status: Optional[str] = None, limit: int = 50) -> List[dict]:
        if status:
            rows = await self._conn.fetch(
                "SELECT * FROM predictions WHERE user_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3",
                user_id, status, limit,
            )
        else:
            rows = await self._conn.fetch(
                "SELECT * FROM predictions WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
                user_id, limit,
            )
        return [dict(r) for r in rows]

    async def mark_settled(self, prediction_id: UUID, status: str) -> None:
        """Transition prediction to a settled status."""
        await self._conn.execute(
            "UPDATE predictions SET status = $2, settled_at = NOW() WHERE id = $1",
            prediction_id, status,
        )

    async def mark_expired(self, prediction_id: UUID) -> None:
        """Mark a prediction as EXPIRED."""
        await self._conn.execute(
            "UPDATE predictions SET status = 'EXPIRED', settled_at = NOW() WHERE id = $1",
            prediction_id,
        )
