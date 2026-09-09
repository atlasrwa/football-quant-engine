"""Integration tests for TheStatsAPI providers against the cached corpus.

These use the on-disk cache under data/thestatsapi/championship/ (no network).
They skip cleanly if that corpus is not present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.research.data_source import ResearchDataSource
from src.research.forward.providers import FutureFixtureProvider
from src.research.thestatsapi.adapter import TheStatsAPIDataSource
from src.research.thestatsapi.corpus_loader import TheStatsAPICorpusLoader
from src.research.thestatsapi.fixture_provider import TheStatsAPIFixtureProvider

_BASE = Path("data/thestatsapi/championship")
_FIXTURES_FILE = "_all_fixtures_epl_sn_3057848.json"

_corpus_available = (_BASE / _FIXTURES_FILE).exists()
pytestmark = pytest.mark.skipif(
    not _corpus_available, reason="TheStatsAPI cached corpus not present"
)


@pytest.fixture
def loader():
    return TheStatsAPICorpusLoader(_BASE)


class TestDataSource:
    def test_implements_interface(self, loader):
        src = TheStatsAPIDataSource(loader=loader, fixtures_files=[_FIXTURES_FILE],
                                    stats_glob="epl_stats_mt_*.json")
        assert isinstance(src, ResearchDataSource)

    def test_normalizes_season(self, loader):
        src = TheStatsAPIDataSource(loader=loader, fixtures_files=[_FIXTURES_FILE],
                                    stats_glob="epl_stats_mt_*.json")
        matches = src.get_matches()
        assert len(matches) > 300  # a full EPL season
        # sorted ascending by date
        assert all(matches[i].date_unix <= matches[i + 1].date_unix
                   for i in range(len(matches) - 1))
        # goals populated on every completed match
        assert all(m.home_goals is not None and m.away_goals is not None for m in matches)

    def test_content_hash_deterministic(self, loader):
        a = TheStatsAPIDataSource(loader=loader, fixtures_files=[_FIXTURES_FILE])
        b = TheStatsAPIDataSource(loader=loader, fixtures_files=[_FIXTURES_FILE])
        assert a.compute_content_hash() == b.compute_content_hash()

    def test_provenance_distinguishes_timestamps(self, loader):
        src = TheStatsAPIDataSource(loader=loader, fixtures_files=[_FIXTURES_FILE])
        src.get_matches()
        prov = src.provenance_records
        assert prov
        p = prov[0]
        assert p.source == "THESTATSAPI"
        # information_timestamp is an estimate strictly after the event.
        assert p.information_timestamp > p.event_timestamp
        # original prefixed refs retained alongside numeric ids
        assert p.source_match_ref.startswith("mt_")


class TestFixtureProvider:
    def test_implements_interface_and_ids(self, loader):
        fp = TheStatsAPIFixtureProvider(loader=loader, fixtures_files=[_FIXTURES_FILE])
        assert isinstance(fp, FutureFixtureProvider)
        assert fp.provider_name == "thestatsapi"
        fixtures = fp.get_upcoming_fixtures(limit=5)
        assert fixtures
        # identity is stable and independent of team names
        f0 = fixtures[0]
        assert fp.get_fixture(f0.fixture_id).fixture_id == f0.fixture_id
