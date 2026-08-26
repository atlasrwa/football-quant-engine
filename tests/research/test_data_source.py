"""Tests for research data source abstraction and synthetic data generation."""

import pytest

from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.synthetic_data import SyntheticResearchDataSource


class TestResearchMatch:
    """Tests for the ResearchMatch data class."""

    def test_required_fields(self):
        m = ResearchMatch(
            match_id=1, date_unix=1000000, league_id=1,
            season="2023", home_team="A", away_team="B",
        )
        assert m.match_id == 1
        assert m.home_team == "A"
        assert m.away_team == "B"

    def test_optional_fields_default_none(self):
        m = ResearchMatch(
            match_id=1, date_unix=1000000, league_id=1,
            season="2023", home_team="A", away_team="B",
        )
        assert m.home_goals is None
        assert m.corners_home is None
        assert m.odds_over_goals is None

    def test_to_dict(self):
        m = ResearchMatch(
            match_id=1, date_unix=1000000, league_id=1,
            season="2023", home_team="A", away_team="B",
            home_goals=2, away_goals=1,
        )
        d = m.to_dict()
        assert d["match_id"] == 1
        assert d["home_goals"] == 2
        assert d["corners_home"] is None

    def test_available_fields(self):
        m = ResearchMatch(
            match_id=1, date_unix=1000000, league_id=1,
            season="2023", home_team="A", away_team="B",
            home_goals=2,
        )
        fields = m.available_fields
        assert "match_id" in fields
        assert "home_goals" in fields
        assert "corners_home" not in fields

    def test_frozen_immutability(self):
        m = ResearchMatch(
            match_id=1, date_unix=1000000, league_id=1,
            season="2023", home_team="A", away_team="B",
        )
        with pytest.raises(Exception):
            m.match_id = 2  # type: ignore


class TestSyntheticResearchDataSource:
    """Tests for the synthetic data source."""

    @pytest.fixture
    def source(self):
        return SyntheticResearchDataSource(seed=42, num_seasons=2)

    def test_implements_interface(self, source):
        assert isinstance(source, ResearchDataSource)

    def test_deterministic_with_same_seed(self):
        s1 = SyntheticResearchDataSource(seed=42, num_seasons=1)
        s2 = SyntheticResearchDataSource(seed=42, num_seasons=1)
        m1 = s1.get_matches()
        m2 = s2.get_matches()
        assert len(m1) == len(m2)
        assert m1[0].match_id == m2[0].match_id
        assert m1[0].home_goals == m2[0].home_goals
        assert m1[0].corners_home == m2[0].corners_home

    def test_different_seed_produces_different_data(self):
        s1 = SyntheticResearchDataSource(seed=42, num_seasons=1)
        s2 = SyntheticResearchDataSource(seed=99, num_seasons=1)
        m1 = s1.get_matches()
        m2 = s2.get_matches()
        # At least some values should differ
        diffs = sum(1 for a, b in zip(m1[:20], m2[:20]) if a.home_goals != b.home_goals)
        assert diffs > 0

    def test_generates_expected_match_count(self, source):
        matches = source.get_matches()
        # 12 teams, each plays 11 others = 132 matches per season, 2 seasons
        assert len(matches) == 132 * 2

    def test_matches_sorted_by_date(self, source):
        matches = source.get_matches()
        dates = [m.date_unix for m in matches]
        assert dates == sorted(dates)

    def test_filter_by_season(self, source):
        matches = source.get_matches(season="2020")
        assert all(m.season == "2020" for m in matches)
        assert len(matches) == 132

    def test_filter_by_league(self, source):
        matches = source.get_matches(league_id=1001)
        assert all(m.league_id == 1001 for m in matches)

    def test_filter_by_date_range(self, source):
        matches = source.get_matches()
        mid_date = matches[len(matches) // 2].date_unix
        before = source.get_matches(max_date=mid_date)
        after = source.get_matches(min_date=mid_date)
        assert all(m.date_unix < mid_date for m in before)
        assert all(m.date_unix >= mid_date for m in after)

    def test_all_post_match_fields_populated(self, source):
        matches = source.get_matches()
        for m in matches[:10]:
            assert m.home_goals is not None
            assert m.away_goals is not None
            assert m.corners_home is not None
            assert m.corners_away is not None
            assert m.total_corners is not None
            assert m.possession_home is not None
            assert m.dangerous_attacks_home is not None

    def test_odds_populated(self, source):
        matches = source.get_matches()
        for m in matches[:10]:
            assert m.odds_over_goals is not None
            assert m.odds_under_goals is not None
            assert m.odds_over_corners is not None
            assert m.odds_under_corners is not None

    def test_odds_are_valid_decimals(self, source):
        matches = source.get_matches()
        for m in matches[:50]:
            if m.odds_over_goals is not None:
                assert m.odds_over_goals > 1.0
            if m.odds_under_goals is not None:
                assert m.odds_under_goals > 1.0

    def test_get_available_fields(self, source):
        fields = source.get_available_fields()
        assert "match_id" in fields
        assert "home_goals" in fields
        assert "corners_home" in fields
        assert "possession_home" in fields
        assert "odds_over_corners" in fields

    def test_get_market_odds(self, source):
        odds = source.get_market_odds(market="CORNERS_TOTAL")
        assert len(odds) > 0
        assert all(isinstance(o, MarketOdds) for o in odds)
        assert all(o.market == "CORNERS_TOTAL" for o in odds)

    def test_get_market_odds_by_match_ids(self, source):
        matches = source.get_matches()
        ids = [matches[0].match_id, matches[1].match_id]
        odds = source.get_market_odds(match_ids=ids)
        assert all(o.match_id in ids for o in odds)

    def test_content_hash_deterministic(self, source):
        h1 = source.compute_content_hash()
        h2 = source.compute_content_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_total_corners_equals_sum(self, source):
        matches = source.get_matches()
        for m in matches[:50]:
            assert m.total_corners == m.corners_home + m.corners_away

    def test_total_goals_equals_sum(self, source):
        matches = source.get_matches()
        for m in matches[:50]:
            assert m.total_goals == m.home_goals + m.away_goals

    def test_possession_sums_to_100(self, source):
        matches = source.get_matches()
        for m in matches[:50]:
            total = m.possession_home + m.possession_away
            assert abs(total - 100.0) < 0.01
