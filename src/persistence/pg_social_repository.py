"""PostgreSQL repositories for social features: follows, reputation, leaderboard."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

import asyncpg


class PgFollowRepository:
    """Repository for follow/unfollow relationships."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def follow(self, follower_id: UUID, followed_id: UUID) -> bool:
        """Create a follow relationship. Returns True if new, False if exists."""
        result = await self._conn.execute(
            """
            INSERT INTO follows (follower_id, followed_id)
            VALUES ($1, $2)
            ON CONFLICT (follower_id, followed_id) DO NOTHING
            """,
            follower_id, followed_id,
        )
        return result == "INSERT 0 1"

    async def unfollow(self, follower_id: UUID, followed_id: UUID) -> bool:
        """Remove a follow relationship. Returns True if deleted."""
        result = await self._conn.execute(
            "DELETE FROM follows WHERE follower_id = $1 AND followed_id = $2",
            follower_id, followed_id,
        )
        return result == "DELETE 1"

    async def get_followers(self, user_id: UUID, limit: int = 50) -> List[UUID]:
        """Get user IDs of people who follow this user."""
        rows = await self._conn.fetch(
            "SELECT follower_id FROM follows WHERE followed_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit,
        )
        return [r["follower_id"] for r in rows]

    async def get_following(self, user_id: UUID, limit: int = 50) -> List[UUID]:
        """Get user IDs of people this user follows."""
        rows = await self._conn.fetch(
            "SELECT followed_id FROM follows WHERE follower_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit,
        )
        return [r["followed_id"] for r in rows]

    async def is_following(self, follower_id: UUID, followed_id: UUID) -> bool:
        """Check if a follow relationship exists."""
        row = await self._conn.fetchrow(
            "SELECT 1 FROM follows WHERE follower_id = $1 AND followed_id = $2",
            follower_id, followed_id,
        )
        return row is not None

    async def follower_count(self, user_id: UUID) -> int:
        row = await self._conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM follows WHERE followed_id = $1", user_id
        )
        return row["cnt"]

    async def following_count(self, user_id: UUID) -> int:
        row = await self._conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM follows WHERE follower_id = $1", user_id
        )
        return row["cnt"]


class PgReputationRepository:
    """System-owned repository for derived reputation scores."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert(
        self,
        user_id: UUID,
        period_type: str,
        period_start: date,
        period_end: date,
        total_predictions: int,
        settled_predictions: int,
        win_rate: Optional[float],
        roi_pct: Optional[float],
        avg_clv_pct: Optional[float],
        max_drawdown_pct: Optional[float],
        reputation_score: float,
        rank: Optional[int] = None,
    ) -> dict:
        """Insert or update a reputation score."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO reputation_scores (user_id, period_type, period_start, period_end,
                total_predictions, settled_predictions, win_rate, roi_pct,
                avg_clv_pct, max_drawdown_pct, reputation_score, rank, calculated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())
            ON CONFLICT (user_id, period_type, period_start) DO UPDATE SET
                period_end = EXCLUDED.period_end,
                total_predictions = EXCLUDED.total_predictions,
                settled_predictions = EXCLUDED.settled_predictions,
                win_rate = EXCLUDED.win_rate,
                roi_pct = EXCLUDED.roi_pct,
                avg_clv_pct = EXCLUDED.avg_clv_pct,
                max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                reputation_score = EXCLUDED.reputation_score,
                rank = EXCLUDED.rank,
                calculated_at = NOW()
            RETURNING *
            """,
            user_id, period_type, period_start, period_end,
            total_predictions, settled_predictions, win_rate, roi_pct,
            avg_clv_pct, max_drawdown_pct, reputation_score, rank,
        )
        return dict(row)

    async def get_by_user(self, user_id: UUID, period_type: str = "30d") -> Optional[dict]:
        """Get latest reputation score for a user."""
        row = await self._conn.fetchrow(
            """
            SELECT * FROM reputation_scores
            WHERE user_id = $1 AND period_type = $2
            ORDER BY period_start DESC LIMIT 1
            """,
            user_id, period_type,
        )
        return dict(row) if row else None


class PgLeaderboardRepository:
    """System-owned repository for leaderboard snapshots."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def insert_snapshot(
        self,
        scope: str,
        period_type: str,
        rank: int,
        user_id: UUID,
        display_name: str,
        score: float,
        roi_pct: Optional[float] = None,
        win_rate: Optional[float] = None,
        total_bets: int = 0,
        avg_clv_pct: Optional[float] = None,
    ) -> dict:
        """Insert a single leaderboard ranking entry."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO leaderboard_snapshots (scope, period_type, rank, user_id,
                display_name, score, roi_pct, win_rate, total_bets, avg_clv_pct)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            RETURNING *
            """,
            scope, period_type, rank, user_id, display_name,
            score, roi_pct, win_rate, total_bets, avg_clv_pct,
        )
        return dict(row)

    async def get_leaderboard(
        self, scope: str = "global", period_type: str = "30d", limit: int = 50
    ) -> List[dict]:
        """Get the most recent leaderboard snapshot."""
        rows = await self._conn.fetch(
            """
            SELECT * FROM leaderboard_snapshots
            WHERE scope = $1 AND period_type = $2
              AND snapshot_at = (
                  SELECT MAX(snapshot_at) FROM leaderboard_snapshots
                  WHERE scope = $1 AND period_type = $2
              )
            ORDER BY rank ASC
            LIMIT $3
            """,
            scope, period_type, limit,
        )
        return [dict(r) for r in rows]

    async def get_user_rank(self, user_id: UUID, scope: str = "global", period_type: str = "30d") -> Optional[dict]:
        """Get user's most recent ranking."""
        row = await self._conn.fetchrow(
            """
            SELECT * FROM leaderboard_snapshots
            WHERE user_id = $1 AND scope = $2 AND period_type = $3
            ORDER BY snapshot_at DESC LIMIT 1
            """,
            user_id, scope, period_type,
        )
        return dict(row) if row else None
