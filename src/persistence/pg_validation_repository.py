"""PostgreSQL repository for validation_runs (INSERT-only)."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

import asyncpg


class PgValidationRepository:
    """INSERT-only repository for statistical validation results."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        strategy_id: UUID,
        strategy_version: int,
        status: str,
        p_value: float,
        roi_pct: float,
        sample_size: int,
        effect_size: float,
        ci_lower: float,
        ci_upper: float,
        min_sample_required: int,
        min_roi_required: float,
        max_p_value: float,
        fdr_submission_count: int,
        reason: str,
        fdr_adjusted_threshold: Optional[float] = None,
        backtest_run_id: Optional[UUID] = None,
    ) -> dict:
        """Persist a validation result. Returns the created record."""
        row = await self._conn.fetchrow(
            """
            INSERT INTO validation_runs (backtest_run_id, strategy_id, strategy_version,
                status, p_value, roi_pct, sample_size, effect_size, ci_lower, ci_upper,
                min_sample_required, min_roi_required, max_p_value,
                fdr_submission_count, fdr_adjusted_threshold, reason)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            RETURNING *
            """,
            backtest_run_id, strategy_id, strategy_version,
            status, p_value, roi_pct, sample_size, effect_size, ci_lower, ci_upper,
            min_sample_required, min_roi_required, max_p_value,
            fdr_submission_count, fdr_adjusted_threshold, reason,
        )
        return dict(row)

    async def get_by_id(self, validation_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM validation_runs WHERE id = $1", validation_id
        )
        return dict(row) if row else None

    async def get_by_strategy(self, strategy_id: UUID, strategy_version: int) -> List[dict]:
        """Get all validation runs for a strategy version."""
        rows = await self._conn.fetch(
            """
            SELECT * FROM validation_runs
            WHERE strategy_id = $1 AND strategy_version = $2
            ORDER BY validated_at DESC
            """,
            strategy_id, strategy_version,
        )
        return [dict(r) for r in rows]

    async def get_latest_passed(self, strategy_id: UUID, strategy_version: int) -> Optional[dict]:
        """Get the most recent PASSED validation for a strategy version."""
        row = await self._conn.fetchrow(
            """
            SELECT * FROM validation_runs
            WHERE strategy_id = $1 AND strategy_version = $2 AND status = 'PASSED'
            ORDER BY validated_at DESC LIMIT 1
            """,
            strategy_id, strategy_version,
        )
        return dict(row) if row else None
