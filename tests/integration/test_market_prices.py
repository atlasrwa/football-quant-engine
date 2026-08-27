"""Integration tests for market_prices time-series table."""

from datetime import datetime, timezone, timedelta

import pytest
import asyncpg

from src.persistence.pg_market_price_repository import PgMarketPriceRepository


pytestmark = pytest.mark.asyncio


async def _insert_match(db_conn, external_id: int = 90001) -> int:
    """Helper: insert a match and return its surrogate match_id."""
    row = await db_conn.fetchrow(
        """
        INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
                             home_team, away_team, home_goals, away_goals)
        VALUES ($1, 'footystats', 1700000000, 4759, '2023', 'A', 'B', 2, 1)
        ON CONFLICT (external_source, external_id) DO UPDATE SET home_goals = EXCLUDED.home_goals
        RETURNING match_id
        """,
        external_id,
    )
    return row["match_id"]


class TestMarketPriceTimeSeries:
    """Verify multiple observations are allowed for the same match/market/selection."""

    async def test_multiple_observations_allowed(self, db_conn):
        """Same match/market/selection can have many price points over time."""
        repo = PgMarketPriceRepository(db_conn)
        match_id = await _insert_match(db_conn, 80001)

        base_time = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        prices = [2.10, 2.05, 1.95, 1.90]

        for i, odds in enumerate(prices):
            await repo.insert(
                match_id=match_id,
                market_type="OVER_UNDER",
                selection="OVER",
                price_type="LIVE",
                odds=odds,
                observed_at=base_time + timedelta(hours=i),
                source="pinnacle",
                line=2.5,
            )

        history = await repo.get_price_history(match_id, "OVER_UNDER", "OVER")
        assert len(history) == 4
        # Chronological order
        assert history[0]["odds"] == 2.10
        assert history[3]["odds"] == 1.90

    async def test_provider_identity_preserved(self, db_conn):
        """Different sources for same market coexist."""
        repo = PgMarketPriceRepository(db_conn)
        match_id = await _insert_match(db_conn, 80002)
        t = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

        await repo.insert(match_id=match_id, market_type="OVER_UNDER", selection="OVER",
                          price_type="CLOSING", odds=1.95, observed_at=t, source="pinnacle", line=2.5)
        await repo.insert(match_id=match_id, market_type="OVER_UNDER", selection="OVER",
                          price_type="CLOSING", odds=1.92, observed_at=t, source="bet365", line=2.5)

        history = await repo.get_price_history(match_id, "OVER_UNDER", "OVER")
        assert len(history) == 2
        sources = {r["source"] for r in history}
        assert sources == {"pinnacle", "bet365"}

    async def test_null_odds_not_allowed(self, db_conn):
        """Odds column is NOT NULL — no silent synthetic defaults."""
        match_id = await _insert_match(db_conn, 80003)
        with pytest.raises(asyncpg.NotNullViolationError):
            await db_conn.execute(
                """INSERT INTO market_prices (match_id, market_type, selection, price_type,
                   odds, observed_at, source) VALUES ($1, 'X', 'HOME', 'LIVE', NULL, NOW(), 'test')""",
                match_id,
            )

    async def test_odds_must_exceed_one(self, db_conn):
        """Odds <= 1.0 are rejected by CHECK constraint."""
        match_id = await _insert_match(db_conn, 80004)
        with pytest.raises(asyncpg.CheckViolationError):
            await db_conn.execute(
                """INSERT INTO market_prices (match_id, market_type, selection, price_type,
                   odds, observed_at, source) VALUES ($1, 'X', 'HOME', 'LIVE', 0.95, NOW(), 'test')""",
                match_id,
            )

    async def test_closing_price_lookup(self, db_conn):
        """get_closing_price returns the most recent closing observation."""
        repo = PgMarketPriceRepository(db_conn)
        match_id = await _insert_match(db_conn, 80005)

        t1 = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        t2 = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

        await repo.insert(match_id=match_id, market_type="OVER_UNDER", selection="OVER",
                          price_type="CLOSING", odds=1.95, observed_at=t1, source="pinnacle", line=2.5)
        await repo.insert(match_id=match_id, market_type="OVER_UNDER", selection="OVER",
                          price_type="CLOSING", odds=1.92, observed_at=t2, source="pinnacle", line=2.5)

        closing = await repo.get_closing_price(match_id, "OVER_UNDER", "OVER")
        assert closing == 1.92  # Most recent

    async def test_immutability_update_blocked(self, db_conn):
        """UPDATE on market_prices is blocked (RLS prevents matching)."""
        repo = PgMarketPriceRepository(db_conn)
        match_id = await _insert_match(db_conn, 80006)
        t = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)

        price_id = await repo.insert(match_id=match_id, market_type="OVER_UNDER",
                                     selection="OVER", price_type="LIVE", odds=2.0,
                                     observed_at=t, source="test")

        result = await db_conn.execute(
            "UPDATE market_prices SET odds = 99.0 WHERE id = $1", price_id
        )
        assert result == "UPDATE 0"  # RLS blocks
