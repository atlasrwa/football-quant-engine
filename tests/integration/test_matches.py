"""Integration tests for matches table (provider-independent identity)."""

import pytest
import asyncpg
from uuid import uuid4


pytestmark = pytest.mark.asyncio


class TestMatchProviderIndependence:
    """Test that match identity is decoupled from external providers."""

    async def test_insert_match(self, db_conn):
        """Basic match insertion succeeds."""
        row = await db_conn.fetchrow(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals, over_under_line)
            VALUES (12345, 'footystats', 1700000000, 4759, '2023',
                    'Arsenal', 'Chelsea', 2, 1, 2.5)
            RETURNING match_id, total_goals
            """
        )
        assert row["match_id"] > 0
        assert row["total_goals"] == 3  # generated column

    async def test_duplicate_external_id_same_source_rejected(self, db_conn):
        """Same (external_source, external_id) cannot be inserted twice."""
        await db_conn.execute(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals)
            VALUES (99999, 'footystats', 1700000000, 4759, '2023', 'A', 'B', 1, 1)
            """
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await db_conn.execute(
                """
                INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                     home_team, away_team, home_goals, away_goals)
                VALUES (99999, 'footystats', 1700000000, 4759, '2023', 'A', 'B', 1, 1)
                """
            )

    async def test_same_external_id_different_source_allowed(self, db_conn):
        """Same external_id from different sources creates distinct matches."""
        await db_conn.execute(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals)
            VALUES (77777, 'footystats', 1700000000, 4759, '2023', 'X', 'Y', 0, 0)
            """
        )
        # Same external_id but different source — should succeed
        await db_conn.execute(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals)
            VALUES (77777, 'opta', 1700000000, 4759, '2023', 'X', 'Y', 0, 0)
            """
        )

    async def test_total_goals_generated_correctly(self, db_conn):
        """total_goals is always home_goals + away_goals."""
        row = await db_conn.fetchrow(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals)
            VALUES (88888, 'footystats', 1700000000, 1625, '2024', 'Liverpool', 'City', 4, 3)
            RETURNING total_goals
            """
        )
        assert row["total_goals"] == 7

    async def test_negative_goals_rejected(self, db_conn):
        """Negative goal values are rejected by CHECK constraint."""
        with pytest.raises(asyncpg.CheckViolationError):
            await db_conn.execute(
                """
                INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                     home_team, away_team, home_goals, away_goals)
                VALUES (11111, 'footystats', 1700000000, 4759, '2023', 'A', 'B', -1, 0)
                """
            )

    async def test_invalid_odds_rejected(self, db_conn):
        """Odds <= 1.0 are rejected by CHECK constraint."""
        with pytest.raises(asyncpg.CheckViolationError):
            await db_conn.execute(
                """
                INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                     home_team, away_team, home_goals, away_goals, over_odds)
                VALUES (22222, 'footystats', 1700000000, 4759, '2023', 'A', 'B', 1, 1, 0.95)
                """
            )

    async def test_null_odds_allowed(self, db_conn):
        """NULL odds are valid (odds may be unavailable)."""
        row = await db_conn.fetchrow(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals,
                                 over_odds, under_odds)
            VALUES (33333, 'footystats', 1700000000, 4759, '2023', 'A', 'B', 1, 0, NULL, NULL)
            RETURNING over_odds, under_odds
            """
        )
        assert row["over_odds"] is None
        assert row["under_odds"] is None

    async def test_raw_data_jsonb_stored(self, db_conn):
        """Raw provider payload is preserved in JSONB column."""
        import json
        raw = {"homeGoalCount": 2, "awayGoalCount": 1, "extra_field": "preserved"}
        row = await db_conn.fetchrow(
            """
            INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                                 home_team, away_team, home_goals, away_goals, raw_data)
            VALUES (44444, 'footystats', 1700000000, 4759, '2023', 'A', 'B', 2, 1, $1::jsonb)
            RETURNING raw_data
            """,
            json.dumps(raw),
        )
        raw_data = row["raw_data"]
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        assert raw_data["extra_field"] == "preserved"
