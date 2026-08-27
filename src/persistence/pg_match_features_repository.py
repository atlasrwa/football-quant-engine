"""PostgreSQL repository for match_features (computed feature vectors)."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

import asyncpg

from src.models.features import MatchFeatures


class PgMatchFeaturesRepository:
    """INSERT-only repository for computed feature vectors.

    Bridges the engine's MatchFeatures dataclass to the database.
    """

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def insert(
        self,
        match_id: int,
        feature_version_id: UUID,
        features: MatchFeatures,
        xmetrics: Optional[dict] = None,
    ) -> int:
        """Insert a computed feature vector. Returns row ID.

        Args:
            match_id: Surrogate match_id from matches table.
            feature_version_id: The feature version these were computed under.
            features: The engine's MatchFeatures object.
            xmetrics: Optional dict with home_xc, away_xc, etc.

        Returns:
            The inserted row ID.
        """
        xm = xmetrics or {}
        row = await self._conn.fetchrow(
            """
            INSERT INTO match_features (match_id, feature_version_id, date_unix,
                home_xg_eff_delta_rolling, away_xg_eff_delta_rolling,
                home_rolling_form, away_rolling_form, referee_volatility_index,
                home_xc, away_xc, home_xb, away_xb, home_xo, away_xo,
                total_goals, over_under_line, over_odds, under_odds)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            ON CONFLICT (match_id, feature_version_id) DO NOTHING
            RETURNING id
            """,
            match_id, feature_version_id, features.date_unix,
            features.home_xg_eff_delta_rolling, features.away_xg_eff_delta_rolling,
            features.home_rolling_form, features.away_rolling_form,
            features.referee_volatility_index,
            xm.get("home_xc"), xm.get("away_xc"),
            xm.get("home_xb"), xm.get("away_xb"),
            xm.get("home_xo"), xm.get("away_xo"),
            features.total_goals, features.over_under_line,
            features.over_odds, features.under_odds,
        )
        return row["id"] if row else 0

    async def insert_batch(
        self,
        match_ids: List[int],
        feature_version_id: UUID,
        features_list: List[MatchFeatures],
    ) -> int:
        """Batch insert features. Returns count inserted."""
        count = 0
        for match_id, features in zip(match_ids, features_list):
            result = await self.insert(match_id, feature_version_id, features)
            if result:
                count += 1
        return count

    async def get_by_match_and_version(
        self, match_id: int, feature_version_id: UUID
    ) -> Optional[dict]:
        """Get features for a specific match under a specific version."""
        row = await self._conn.fetchrow(
            """
            SELECT * FROM match_features
            WHERE match_id = $1 AND feature_version_id = $2
            """,
            match_id, feature_version_id,
        )
        return dict(row) if row else None

    async def list_by_feature_version(
        self, feature_version_id: UUID
    ) -> List[dict]:
        """Get all features for a feature version, ordered by date."""
        rows = await self._conn.fetch(
            """
            SELECT * FROM match_features
            WHERE feature_version_id = $1
            ORDER BY date_unix ASC
            """,
            feature_version_id,
        )
        return [dict(r) for r in rows]

    async def count_by_feature_version(self, feature_version_id: UUID) -> int:
        """Count features computed for a version."""
        row = await self._conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM match_features WHERE feature_version_id = $1",
            feature_version_id,
        )
        return row["cnt"]
