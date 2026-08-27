"""PostgreSQL repositories for provenance chain:
dataset_versions, feature_versions, model_versions.

All tables are INSERT-only (immutable after creation).
Content hashes computed using src/persistence/hashing.py.
"""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

import asyncpg

from src.persistence.hashing import (
    compute_dataset_content_hash,
    compute_feature_version_hash,
    compute_model_version_hash,
)


class PgDatasetVersionRepository:
    """INSERT-only repository for dataset version snapshots."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        source: str,
        league_id: int,
        season: str,
        match_ids: List[int],
        date_range_start: int,
        date_range_end: int,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Create a dataset version. Deduplicates by content_hash.

        If a dataset with the same content_hash already exists, returns
        the existing record (idempotent).

        Returns:
            Dict with id, content_hash, and other fields.
        """
        content_hash = compute_dataset_content_hash(match_ids)

        # Check for existing (dedup)
        existing = await self.get_by_hash(content_hash)
        if existing:
            return existing

        row = await self._conn.fetchrow(
            """
            INSERT INTO dataset_versions (source, league_id, season, n_matches,
                                          date_range_start, date_range_end,
                                          content_hash, match_ids, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING *
            """,
            source, league_id, season, len(match_ids),
            date_range_start, date_range_end,
            content_hash, json.dumps(sorted(match_ids)), created_by,
        )
        if row:
            return dict(row)
        # Race condition: another transaction inserted between check and insert
        return await self.get_by_hash(content_hash)

    async def get_by_id(self, dataset_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM dataset_versions WHERE id = $1", dataset_id
        )
        return dict(row) if row else None

    async def get_by_hash(self, content_hash: str) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM dataset_versions WHERE content_hash = $1", content_hash
        )
        return dict(row) if row else None


class PgFeatureVersionRepository:
    """INSERT-only repository for feature version configurations."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        dataset_id: UUID,
        xg_rolling_window: int,
        form_rolling_window: int,
        referee_min_matches: int,
        xmetric_coefficients: Optional[dict] = None,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Create a feature version. Deduplicates by content_hash."""
        content_hash = compute_feature_version_hash(
            str(dataset_id), xg_rolling_window, form_rolling_window,
            referee_min_matches, xmetric_coefficients,
        )

        existing = await self.get_by_hash(content_hash)
        if existing:
            return existing

        row = await self._conn.fetchrow(
            """
            INSERT INTO feature_versions (dataset_id, xg_rolling_window, form_rolling_window,
                                          referee_min_matches, xmetric_coefficients,
                                          content_hash, created_by)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING *
            """,
            dataset_id, xg_rolling_window, form_rolling_window,
            referee_min_matches,
            json.dumps(xmetric_coefficients) if xmetric_coefficients else None,
            content_hash, created_by,
        )
        if row:
            return dict(row)
        return await self.get_by_hash(content_hash)

    async def get_by_id(self, feature_version_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM feature_versions WHERE id = $1", feature_version_id
        )
        return dict(row) if row else None

    async def get_by_hash(self, content_hash: str) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM feature_versions WHERE content_hash = $1", content_hash
        )
        return dict(row) if row else None


class PgModelVersionRepository:
    """INSERT-only repository for model version configurations."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def create(
        self,
        strategy_id: UUID,
        strategy_version: int,
        strategy_content_hash: str,
        feature_version_id: UUID,
        train_window: int,
        test_window: int,
        step_size: int,
        min_odds: float,
        max_odds: float,
        created_by: Optional[UUID] = None,
    ) -> dict:
        """Create a model version. Deduplicates by content_hash."""
        content_hash = compute_model_version_hash(
            strategy_content_hash, str(feature_version_id),
            train_window, test_window, step_size, min_odds, max_odds,
        )

        existing = await self.get_by_hash(content_hash)
        if existing:
            return existing

        row = await self._conn.fetchrow(
            """
            INSERT INTO model_versions (strategy_id, strategy_version, strategy_content_hash,
                                        feature_version_id, train_window, test_window,
                                        step_size, min_odds, max_odds, content_hash, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING *
            """,
            strategy_id, strategy_version, strategy_content_hash,
            feature_version_id, train_window, test_window,
            step_size, min_odds, max_odds, content_hash, created_by,
        )
        if row:
            return dict(row)
        return await self.get_by_hash(content_hash)

    async def get_by_id(self, model_version_id: UUID) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM model_versions WHERE id = $1", model_version_id
        )
        return dict(row) if row else None

    async def get_by_hash(self, content_hash: str) -> Optional[dict]:
        row = await self._conn.fetchrow(
            "SELECT * FROM model_versions WHERE content_hash = $1", content_hash
        )
        return dict(row) if row else None
