"""Deterministic tests for retained TheStatsAPI provider adapters."""

from __future__ import annotations

from src.research.data_source import ResearchDataSource
from src.research.forward.providers import FutureFixtureProvider
from src.research.thestatsapi.adapter import TheStatsAPIDataSource
from src.research.thestatsapi.fixture_provider import TheStatsAPIFixtureProvider


def _fixtures():
    return [
        {
            "id": "mt_1001",
            "competition_id": "comp_3039",
            "season_id": "sn_3057848",
            "status": "finished",
            "utc_date": "2025-01-01T15:00:00.000Z",
            "home_team": {"id": "tm_1", "name": "Home FC"},
            "away_team": {"id": "tm_2", "name": "Away FC"},
            "score": {"home": 2, "away": 1},
        },
        {
            "id": "mt_1002",
            "competition_id": "comp_3039",
            "season_id": "sn_3057848",
            "status": "finished",
            "utc_date": "2025-01-08T15:00:00.000Z",
            "home_team": {"id": "tm_2", "name": "Away FC"},
            "away_team": {"id": "tm_1", "name": "Home FC"},
            "score": {"home": 0, "away": 0},
        },
    ]


def _stats():
    return {
        "mt_1001": {
            "data": {
                "match_id": "mt_1001",
                "overview": {
                    "corner_kicks": {"all": {"home": 6, "away": 4}},
                    "yellow_cards": {"all": {"home": 1, "away": 2}},
                    "red_cards": {"all": {"home": 0, "away": 0}},
                },
            }
        }
    }


class TestDataSource:
    def test_implements_interface(self):
        src = TheStatsAPIDataSource(fixtures=_fixtures(), stats_by_match_ref=_stats())
        assert isinstance(src, ResearchDataSource)

    def test_normalizes_and_sorts_matches(self):
        src = TheStatsAPIDataSource(fixtures=list(reversed(_fixtures())), stats_by_match_ref=_stats())
        matches = src.get_matches()
        assert [m.match_id for m in matches] == [1001, 1002]
        assert matches[0].total_goals == 3
        assert matches[0].total_corners == 10
        assert matches[0].total_cards == 3

    def test_content_hash_deterministic(self):
        a = TheStatsAPIDataSource(fixtures=_fixtures(), stats_by_match_ref=_stats())
        b = TheStatsAPIDataSource(fixtures=_fixtures(), stats_by_match_ref=_stats())
        assert a.compute_content_hash() == b.compute_content_hash()

    def test_provenance_distinguishes_timestamps(self):
        src = TheStatsAPIDataSource(fixtures=_fixtures())
        src.get_matches()
        p = src.provenance_records[0]
        assert p.source == "THESTATSAPI"
        assert p.information_timestamp > p.event_timestamp
        assert p.source_match_ref.startswith("mt_")


class TestFixtureProvider:
    def test_implements_interface_and_ids(self):
        fp = TheStatsAPIFixtureProvider(fixtures=_fixtures())
        assert isinstance(fp, FutureFixtureProvider)
        assert fp.provider_name == "thestatsapi"
        fixtures = fp.get_upcoming_fixtures(limit=5)
        assert len(fixtures) == 2
        f0 = fixtures[0]
        assert fp.get_fixture(f0.fixture_id).fixture_id == f0.fixture_id
