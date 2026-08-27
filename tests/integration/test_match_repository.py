"""Integration tests for PgMatchRepository — the adapter between engine and DB.

Verifies:
1. Match objects round-trip correctly (engine → DB → engine)
2. Surrogate key is transparent to the engine
3. Provider independence works (same ext_id from different sources)
4. Upsert semantics (update on conflict)
5. Compatibility with existing FeatureAssembler (Match objects must be valid)
"""

import pytest
from uuid import uuid4

from src.models.match import Match
from src.persistence.pg_match_repository import PgMatchRepository
from src.features.assembler import FeatureAssembler


pytestmark = pytest.mark.asyncio


def _make_match(
    id: int = 12345,
    date_unix: int = 1700000000,
    league_id: int = 4759,
    season: str = "2023",
    home_team: str = "Arsenal",
    away_team: str = "Chelsea",
    home_goals: int = 2,
    away_goals: int = 1,
    home_xg: float = 1.8,
    away_xg: float = 1.2,
    referee: str = "Michael Oliver",
    over_under_line: float = 2.5,
    over_odds: float = 1.90,
    under_odds: float = 2.00,
) -> Match:
    """Helper to create a Match with sensible defaults."""
    return Match(
        id=id,
        date_unix=date_unix,
        league_id=league_id,
        season=season,
        home_team=home_team,
        away_team=away_team,
        home_goals=home_goals,
        away_goals=away_goals,
        total_goals=home_goals + away_goals,
        home_xg=home_xg,
        away_xg=away_xg,
        referee=referee,
        over_under_line=over_under_line,
        over_odds=over_odds,
        under_odds=under_odds,
    )


class TestMatchRoundTrip:
    """Verify Match objects survive the DB round-trip unchanged."""

    async def test_basic_round_trip(self, db_conn):
        """Match stored and retrieved has identical field values."""
        repo = PgMatchRepository(db_conn)
        original = _make_match()

        surrogate_id = await repo.upsert(original)
        assert surrogate_id > 0

        retrieved = await repo.get_by_external_id(original.id)
        assert retrieved is not None
        assert retrieved.id == original.id
        assert retrieved.date_unix == original.date_unix
        assert retrieved.league_id == original.league_id
        assert retrieved.season == original.season
        assert retrieved.home_team == original.home_team
        assert retrieved.away_team == original.away_team
        assert retrieved.home_goals == original.home_goals
        assert retrieved.away_goals == original.away_goals
        assert retrieved.total_goals == original.total_goals
        assert retrieved.home_xg == original.home_xg
        assert retrieved.away_xg == original.away_xg
        assert retrieved.referee == original.referee
        assert retrieved.over_under_line == original.over_under_line
        assert retrieved.over_odds == original.over_odds
        assert retrieved.under_odds == original.under_odds

    async def test_null_optional_fields(self, db_conn):
        """Match with NULL odds and referee round-trips correctly."""
        repo = PgMatchRepository(db_conn)
        match = _make_match(
            id=99001, referee=None, over_odds=None, under_odds=None
        )
        await repo.upsert(match)

        retrieved = await repo.get_by_external_id(99001)
        assert retrieved.referee is None
        assert retrieved.over_odds is None
        assert retrieved.under_odds is None

    async def test_retrieved_match_is_frozen_dataclass(self, db_conn):
        """Retrieved match is a proper frozen dataclass (immutable)."""
        repo = PgMatchRepository(db_conn)
        await repo.upsert(_make_match(id=99002))

        match = await repo.get_by_external_id(99002)
        with pytest.raises(AttributeError):
            match.home_goals = 99  # type: ignore


class TestSurrogateKeyTransparency:
    """The engine never needs to know about surrogate keys."""

    async def test_engine_uses_external_id(self, db_conn):
        """Match.id always equals the external_id, not the surrogate."""
        repo = PgMatchRepository(db_conn)
        match = _make_match(id=55555)
        surrogate = await repo.upsert(match)

        # Surrogate is a different number than external_id
        # (auto-incremented, not guaranteed to equal external_id)
        retrieved = await repo.get_by_external_id(55555)
        assert retrieved.id == 55555  # Engine sees external_id
        # The surrogate is only for internal DB use
        assert surrogate > 0

    async def test_surrogate_id_lookup(self, db_conn):
        """Can look up surrogate ID when needed for FK references."""
        repo = PgMatchRepository(db_conn)
        match = _make_match(id=66666)
        expected_surrogate = await repo.upsert(match)

        actual_surrogate = await repo.get_surrogate_id(66666)
        assert actual_surrogate == expected_surrogate

    async def test_get_by_surrogate_returns_match(self, db_conn):
        """Can retrieve a Match by its surrogate ID (for FK resolution)."""
        repo = PgMatchRepository(db_conn)
        match = _make_match(id=77777)
        surrogate = await repo.upsert(match)

        retrieved = await repo.get_by_surrogate_id(surrogate)
        assert retrieved is not None
        assert retrieved.id == 77777


class TestProviderIndependence:
    """Same external_id from different providers creates distinct matches."""

    async def test_different_sources_coexist(self, db_conn):
        """FootyStats ID 100 and Opta ID 100 are different matches."""
        repo = PgMatchRepository(db_conn)

        fs_match = _make_match(id=100, home_team="Team A", away_team="Team B")
        opta_match = _make_match(id=100, home_team="Team X", away_team="Team Y")

        fs_surrogate = await repo.upsert(fs_match, external_source="footystats")
        opta_surrogate = await repo.upsert(opta_match, external_source="opta")

        assert fs_surrogate != opta_surrogate

        fs_retrieved = await repo.get_by_external_id(100, "footystats")
        opta_retrieved = await repo.get_by_external_id(100, "opta")

        assert fs_retrieved.home_team == "Team A"
        assert opta_retrieved.home_team == "Team X"


class TestUpsertSemantics:
    """Upsert updates existing records on conflict."""

    async def test_upsert_updates_goals(self, db_conn):
        """Re-upserting with different goals updates the record."""
        repo = PgMatchRepository(db_conn)

        # First insert: score is 1-0
        match_v1 = _make_match(id=88888, home_goals=1, away_goals=0)
        await repo.upsert(match_v1)

        # Score update: 2-1 (match finished)
        match_v2 = _make_match(id=88888, home_goals=2, away_goals=1)
        await repo.upsert(match_v2)

        retrieved = await repo.get_by_external_id(88888)
        assert retrieved.home_goals == 2
        assert retrieved.away_goals == 1
        assert retrieved.total_goals == 3

    async def test_upsert_preserves_surrogate_id(self, db_conn):
        """Upsert on conflict preserves the same surrogate match_id."""
        repo = PgMatchRepository(db_conn)

        match = _make_match(id=44444)
        surrogate_1 = await repo.upsert(match)

        # Upsert again — same record
        match_updated = _make_match(id=44444, home_goals=3, away_goals=2)
        surrogate_2 = await repo.upsert(match_updated)

        assert surrogate_1 == surrogate_2


class TestListByLeagueSeason:
    """Test bulk retrieval for feature assembly."""

    async def test_list_returns_chronological_order(self, db_conn):
        """Matches are returned sorted by date_unix ascending."""
        repo = PgMatchRepository(db_conn)

        # Insert out of order
        for i, ts in enumerate([1700003000, 1700001000, 1700002000]):
            await repo.upsert(_make_match(
                id=30000 + i, date_unix=ts,
                league_id=1625, season="2024",
                home_team=f"H{i}", away_team=f"A{i}",
            ))

        matches = await repo.list_by_league_season(1625, "2024")
        assert len(matches) == 3
        assert matches[0].date_unix == 1700001000
        assert matches[1].date_unix == 1700002000
        assert matches[2].date_unix == 1700003000

    async def test_list_filters_by_league_and_season(self, db_conn):
        """Only matches matching league_id AND season are returned."""
        repo = PgMatchRepository(db_conn)

        await repo.upsert(_make_match(id=40001, league_id=4759, season="2023"))
        await repo.upsert(_make_match(id=40002, league_id=4759, season="2024"))
        await repo.upsert(_make_match(id=40003, league_id=1625, season="2023"))

        results = await repo.list_by_league_season(4759, "2023")
        assert len(results) == 1
        assert results[0].id == 40001


class TestEngineCompatibility:
    """Verify retrieved matches work with the existing quant engine."""

    async def test_matches_compatible_with_feature_assembler(self, db_conn):
        """Matches from DB can be fed into FeatureAssembler without errors."""
        repo = PgMatchRepository(db_conn)

        # Create enough matches for feature assembly (needs history)
        for i in range(20):
            await repo.upsert(_make_match(
                id=50000 + i,
                date_unix=1700000000 + i * 86400,
                league_id=4759,
                season="2023",
                home_team="TeamA",
                away_team="TeamB",
                home_goals=i % 3,
                away_goals=(i + 1) % 3,
                home_xg=1.0 + (i % 5) * 0.2,
                away_xg=0.8 + (i % 4) * 0.15,
                referee="RefA",
            ))

        matches = await repo.list_by_league_season(4759, "2023")
        assert len(matches) == 20

        # Feed into the existing engine — this must not raise
        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        # Should produce features (exact count depends on rolling windows)
        assert len(features) > 0
        # Verify features are proper MatchFeatures objects
        for f in features:
            assert hasattr(f, "match_id")
            assert hasattr(f, "home_rolling_form")
            assert 0 <= f.home_rolling_form <= 1
            assert f.referee_volatility_index >= 0
