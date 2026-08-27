"""PostgreSQL repositories for backtest_runs and backtest_bets."""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

import asyncpg

from src.persistence.hashing import compute_backtest_run_hash


class PgBacktestRunRepository:
    """Repository for backtest execution records.

    Runs are user-owned. Deduplication by UNIQUE(user_id, content_hash).
    Status lifecycle: RUNNING → COMPLETED/FAILED (immutable after).
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        user_id: UUID,
        strategy_id: UUID,
        strategy_version: int,
        strategy_content_hash: str,
        dataset_id: UUID,
        feature_version_id: UUID,
        model_version_id: UUID,
        config: dict,
    ) -> dict:
        """Create a new backtest run in RUNNING status.

        Content hash is computed from model_version_id + dataset_id.
        Returns the created record or raises on duplicate.
        """
        content_hash = compute_backtest_run_hash(
            str(model_version_id), str(dataset_id)
        )

        row = await self._conn.fetchrow(
            """
            INSERT INTO backtest_runs (user_id, strategy_id, strategy_version,
                strategy_content_hash, dataset_id, feature_version_id,
                model_version_id, content_hash, config, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, 'RUNNING')
            RETURNING *
            """,
            user_id, strategy_id, strategy_version, strategy_content_hash,
            dataset_id, feature_version_id, model_version_id,
            content_hash, json.dumps(config),
        )
        return dict(row)

    async def complete(
        self,
        run_id: UUID,
        total_bets: int,
        net_roi_pct: float,
        win_rate: float,
        max_drawdown_pct: float,
        avg_model_edge_pct: float,
        total_profit_loss: float,
        total_staked: float,
        n_folds: int,
    ) -> dict:
        """Mark a run as COMPLETED with result metrics."""
        row = await self._conn.fetchrow(
            """
            UPDATE backtest_runs SET
                status = 'COMPLETED',
                total_bets = $2,
                net_roi_pct = $3,
                win_rate = $4,
                max_drawdown_pct = $5,
                avg_model_edge_pct = $6,
                total_profit_loss = $7,
                total_staked = $8,
                n_folds = $9,
                completed_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            run_id, total_bets, net_roi_pct, win_rate, max_drawdown_pct,
            avg_model_edge_pct, total_profit_loss, total_staked, n_folds,
        )
        return dict(row) if row else None

    async def fail(self, run_id: UUID) -> dict:
        """Mark a run as FAILED."""
        row = await self._conn.fetchrow(
            """
            UPDATE backtest_runs SET status = 'FAILED', completed_at = NOW()
            WHERE id = $1
            RETURNING *
            """,
            run_id,
        )
        return dict(row) if row else None

    async def get_by_id(self, run_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM backtest_runs WHERE id = $1", run_id
        )
        return dict(row) if row else None

    async def get_by_user(self, user_id: UUID, limit: int = 50) -> List[dict]:
        rows = await self._conn.fetch(
            "SELECT * FROM backtest_runs WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit,
        )
        return [dict(r) for r in rows]

    async def get_by_content_hash(self, user_id: UUID, content_hash: str) -> Optional[dict]:
        """Check if user already has a run with this content_hash."""
        row = await self._conn.fetchrow(
            "SELECT * FROM backtest_runs WHERE user_id = $1 AND content_hash = $2",
            user_id, content_hash,
        )
        return dict(row) if row else None

    async def get_provenance(self, run_id: UUID) -> Optional[dict]:
        """Get full provenance chain for a backtest run."""
        row = await self._conn.fetchrow(
            """
            SELECT
                br.id AS run_id, br.status, br.content_hash AS run_hash,
                br.strategy_id, br.strategy_version, br.strategy_content_hash,
                br.total_bets, br.net_roi_pct, br.win_rate,
                mv.id AS model_version_id, mv.content_hash AS model_hash,
                mv.train_window, mv.test_window, mv.step_size,
                fv.id AS feature_version_id, fv.content_hash AS feature_hash,
                fv.xg_rolling_window, fv.form_rolling_window, fv.referee_min_matches,
                dv.id AS dataset_id, dv.content_hash AS dataset_hash,
                dv.source, dv.league_id, dv.season, dv.n_matches
            FROM backtest_runs br
            JOIN model_versions mv ON br.model_version_id = mv.id
            JOIN feature_versions fv ON br.feature_version_id = fv.id
            JOIN dataset_versions dv ON br.dataset_id = dv.id
            WHERE br.id = $1
            """,
            run_id,
        )
        return dict(row) if row else None


class PgBacktestBetRepository:
    """INSERT-only repository for individual backtest bet records."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def insert(
        self,
        run_id: UUID,
        match_id: int,
        fold_index: int,
        strategy_name: str,
        direction: str,
        odds: float,
        stake: float,
        outcome: str,
        profit_loss: float,
        model_edge_pct: float,
        clv_pct: Optional[float] = None,
        source: str = "BACKTEST",
    ) -> int:
        """Insert a single bet record. Returns row ID."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO backtest_bets (run_id, match_id, fold_index, strategy_name,
                direction, odds, stake, outcome, profit_loss, model_edge_pct, clv_pct, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            run_id, match_id, fold_index, strategy_name,
            direction, odds, stake, outcome, profit_loss,
            model_edge_pct, clv_pct, source,
        )
        return row["id"]

    async def insert_batch(self, run_id: UUID, bets: List[dict]) -> int:
        """Batch insert bets for a run. Returns count inserted."""
        count = 0
        for b in bets:
            await self.insert(
                run_id=run_id,
                match_id=b["match_id"],
                fold_index=b["fold_index"],
                strategy_name=b["strategy_name"],
                direction=b["direction"],
                odds=b["odds"],
                stake=b["stake"],
                outcome=b["outcome"],
                profit_loss=b["profit_loss"],
                model_edge_pct=b["model_edge_pct"],
                clv_pct=b.get("clv_pct"),
                source=b.get("source", "BACKTEST"),
            )
            count += 1
        return count

    async def get_by_run(self, run_id: UUID) -> List[dict]:
        """Get all bets for a backtest run."""
        rows = await self._conn.fetch(
            "SELECT * FROM backtest_bets WHERE run_id = $1 ORDER BY id ASC",
            run_id,
        )
        return [dict(r) for r in rows]

    async def get_by_match(self, match_id: int) -> List[dict]:
        """Get all bets involving a specific match (across all runs)."""
        rows = await self._conn.fetch(
            "SELECT * FROM backtest_bets WHERE match_id = $1 ORDER BY id ASC",
            match_id,
        )
        return [dict(r) for r in rows]

    async def count_by_run(self, run_id: UUID) -> int:
        """Count bets in a run."""
        row = await self._conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM backtest_bets WHERE run_id = $1", run_id
        )
        return row["cnt"]
