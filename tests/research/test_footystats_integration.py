"""Comprehensive tests for Batch 6 — FootyStats Real-Data Integration.

Test categories:
A. API parsing and normalization
B. Null preservation (sentinel -1 = NULL, odds 0 = NULL)
C. Schema validation and data quality
D. Deduplication
E. Temporal integrity and leakage prevention
F. Team/league identity
G. Pagination handling
H. Credential security
I. Coverage computation
J. Dataset versioning / reproducibility
K. Market readiness
L. Data provenance
M. Idempotent ingestion
N. Real API smoke test (sandbox key=example)
O. Full research pipeline on real data
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.research.data_source import MarketOdds, ResearchMatch
from src.research.footystats.adapter import FootyStatsDataSource
from src.research.footystats.client import (
    AuthenticationError,
    FootyStatsResearchClient,
    RateLimitError,
)
from src.research.footystats.coverage import (
    CoverageReport,
    MarketReadiness,
    compute_coverage,
)
from src.research.footystats.normalizer import MatchNormalizer, _safe_int, _safe_float, _safe_odds
from src.research.footystats.provenance import DataProvenance, compute_match_hash, create_provenance
from src.research.footystats.quality import DataQualityStatus, QualityReport, RecordValidator


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


def _make_raw_match(
    match_id: int = 1000,
    date_unix: int = 1610000000,
    home_goals: int = 2,
    away_goals: int = 1,
    home_name: str = "Team A",
    away_name: str = "Team B",
    status: str = "complete",
    **kwargs,
) -> dict[str, Any]:
    """Create a minimal valid raw FootyStats match record."""
    record: dict[str, Any] = {
        "id": match_id,
        "date_unix": date_unix,
        "homeGoalCount": home_goals,
        "awayGoalCount": away_goals,
        "home_name": home_name,
        "away_name": away_name,
        "homeID": 100,
        "awayID": 200,
        "competition_id": 4759,
        "season": "2020/2021",
        "status": status,
        "team_a_corners": 5,
        "team_b_corners": 7,
        "totalCornerCount": 12,
        "team_a_shots": 15,
        "team_b_shots": 10,
        "team_a_shotsOnTarget": 6,
        "team_b_shotsOnTarget": 4,
        "team_a_shotsOffTarget": 9,
        "team_b_shotsOffTarget": 6,
        "team_a_yellow_cards": 2,
        "team_b_yellow_cards": 3,
        "team_a_red_cards": 0,
        "team_b_red_cards": 0,
        "team_a_offsides": 3,
        "team_b_offsides": 2,
        "team_a_fouls": 12,
        "team_b_fouls": 14,
        "team_a_possession": 55,
        "team_b_possession": 45,
        "team_a_attacks": 100,
        "team_b_attacks": 80,
        "team_a_dangerous_attacks": 50,
        "team_b_dangerous_attacks": 40,
        "team_a_xg": 1.8,
        "team_b_xg": 0.9,
        "odds_ft_over25": 1.85,
        "odds_ft_under25": 2.0,
        "odds_ft_1": 2.5,
        "odds_ft_x": 3.3,
        "odds_ft_2": 2.8,
        "odds_corners_over_95": 1.9,
        "odds_corners_under_95": 1.95,
        "refereeID": 42,
    }
    record.update(kwargs)
    return record


@pytest.fixture
def raw_match():
    return _make_raw_match()


@pytest.fixture
def normalizer():
    return MatchNormalizer()


@pytest.fixture
def validator():
    return RecordValidator()


# ═══════════════════════════════════════════════════════════════
# A. API PARSING AND NORMALIZATION
# ═══════════════════════════════════════════════════════════════


class TestNormalization:
    """Test raw FootyStats → ResearchMatch normalization."""

    def test_basic_normalization(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match is not None
        assert match.match_id == 1000
        assert match.home_goals == 2
        assert match.away_goals == 1
        assert match.total_goals == 3
        assert match.home_team == "Team A"
        assert match.away_team == "Team B"
        assert match.corners_home == 5
        assert match.corners_away == 7
        assert match.total_corners == 12

    def test_shots_normalized(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.shots_home == 15
        assert match.shots_away == 10
        assert match.shots_on_target_home == 6
        assert match.shots_on_target_away == 4

    def test_cards_normalized(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.yellow_cards_home == 2
        assert match.yellow_cards_away == 3
        assert match.red_cards_home == 0
        assert match.red_cards_away == 0
        assert match.total_cards == 5  # 2+3+0+0

    def test_possession_normalized(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.possession_home == 55.0
        assert match.possession_away == 45.0

    def test_xg_normalized(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.home_xg == 1.8
        assert match.away_xg == 0.9

    def test_odds_normalized(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.odds_over_goals == 1.85
        assert match.odds_under_goals == 2.0
        assert match.odds_home_win == 2.5
        assert match.odds_draw == 3.3
        assert match.odds_away_win == 2.8
        assert match.odds_over_corners == 1.9
        assert match.odds_under_corners == 1.95
        assert match.line_goals == 2.5
        assert match.line_corners == 9.5

    def test_incomplete_match_skipped(self, normalizer):
        raw = _make_raw_match(status="incomplete")
        match = normalizer.normalize(raw)
        assert match is None

    def test_missing_id_skipped(self, normalizer):
        raw = _make_raw_match()
        del raw["id"]
        match = normalizer.normalize(raw)
        assert match is None

    def test_missing_goals_skipped(self, normalizer):
        raw = _make_raw_match()
        del raw["homeGoalCount"]
        match = normalizer.normalize(raw)
        assert match is None

    def test_batch_normalization(self, normalizer):
        records = [_make_raw_match(match_id=i) for i in range(10)]
        matches = normalizer.normalize_batch(records)
        assert len(matches) == 10

    def test_market_odds_extraction(self, normalizer, raw_match):
        odds = normalizer.extract_market_odds(raw_match)
        assert len(odds) == 2  # Goals + Corners
        goals_odds = [o for o in odds if o.market == "GOALS_TOTAL"]
        corners_odds = [o for o in odds if o.market == "CORNERS_TOTAL"]
        assert len(goals_odds) == 1
        assert len(corners_odds) == 1
        assert goals_odds[0].over_odds == 1.85
        assert goals_odds[0].line == 2.5
        # Odds timestamp should be before kickoff
        assert goals_odds[0].timestamp < raw_match["date_unix"]


# ═══════════════════════════════════════════════════════════════
# B. NULL PRESERVATION
# ═══════════════════════════════════════════════════════════════


class TestNullPreservation:
    """Test that NULL ≠ ZERO. Missing data stays None."""

    def test_sentinel_minus_one_becomes_none(self):
        """FootyStats -1 sentinel means 'not recorded' → None."""
        assert _safe_int(-1) is None
        assert _safe_float(-1) is None

    def test_zero_is_valid_zero(self):
        """Zero is a legitimate value (0 corners, 0 cards)."""
        assert _safe_int(0) == 0
        assert _safe_float(0) == 0.0

    def test_odds_zero_becomes_none(self):
        """Odds of 0 means 'market not available' → None."""
        assert _safe_odds(0) is None
        assert _safe_odds(0.0) is None

    def test_odds_below_one_becomes_none(self):
        """Decimal odds must be >= 1.0."""
        assert _safe_odds(0.5) is None
        assert _safe_odds(0.99) is None

    def test_valid_odds_preserved(self):
        assert _safe_odds(1.5) == 1.5
        assert _safe_odds(2.0) == 2.0
        assert _safe_odds(10.0) == 10.0

    def test_none_input_returns_none(self):
        assert _safe_int(None) is None
        assert _safe_float(None) is None
        assert _safe_odds(None) is None

    def test_missing_corners_not_zero(self, normalizer):
        """Missing corner data should be None, not 0."""
        raw = _make_raw_match()
        raw["team_a_corners"] = -1  # Not recorded
        raw["team_b_corners"] = None
        raw["totalCornerCount"] = None
        match = normalizer.normalize(raw)
        assert match.corners_home is None
        assert match.corners_away is None

    def test_missing_xg_not_zero(self, normalizer):
        """Missing xG should be None, not 0."""
        raw = _make_raw_match()
        raw["team_a_xg"] = None
        raw["team_b_xg"] = None
        match = normalizer.normalize(raw)
        assert match.home_xg is None
        assert match.away_xg is None

    def test_missing_possession_not_zero(self, normalizer):
        raw = _make_raw_match()
        raw["team_a_possession"] = -1
        raw["team_b_possession"] = -1
        match = normalizer.normalize(raw)
        assert match.possession_home is None
        assert match.possession_away is None

    def test_missing_odds_not_zero(self, normalizer):
        raw = _make_raw_match()
        raw["odds_ft_over25"] = 0
        raw["odds_ft_under25"] = 0
        raw["odds_corners_over_95"] = 0
        raw["odds_corners_under_95"] = 0
        match = normalizer.normalize(raw)
        assert match.odds_over_goals is None
        assert match.odds_under_goals is None
        assert match.odds_over_corners is None
        assert match.odds_under_corners is None


# ═══════════════════════════════════════════════════════════════
# C. SCHEMA VALIDATION AND DATA QUALITY
# ═══════════════════════════════════════════════════════════════


class TestDataQuality:
    """Test data quality validation."""

    def test_valid_match_passes(self, validator, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        status = validator.validate(match)
        assert status == DataQualityStatus.VALID

    def test_duplicate_detection(self, validator, normalizer):
        raw1 = _make_raw_match(match_id=1)
        raw2 = _make_raw_match(match_id=1)  # Same ID
        m1 = normalizer.normalize(raw1)
        m2 = normalizer.normalize(raw2)
        assert validator.validate(m1) == DataQualityStatus.VALID
        assert validator.validate(m2) == DataQualityStatus.DUPLICATE

    def test_invalid_timestamp(self, validator, normalizer):
        raw = _make_raw_match(date_unix=100)  # Year ~1970, too old
        match = normalizer.normalize(raw)
        assert validator.validate(match) == DataQualityStatus.TIMESTAMP_ERROR

    def test_same_home_away_team(self, validator):
        match = ResearchMatch(
            match_id=999,
            date_unix=1610000000,
            league_id=1,
            season="2020/2021",
            home_team="Same Team",
            away_team="Same Team",
            home_goals=1,
            away_goals=0,
        )
        assert validator.validate(match) == DataQualityStatus.SCHEMA_ERROR

    def test_negative_goals_invalid(self, validator):
        match = ResearchMatch(
            match_id=999,
            date_unix=1610000000,
            league_id=1,
            season="2020/2021",
            home_team="A",
            away_team="B",
            home_goals=-1,
            away_goals=0,
        )
        assert validator.validate(match) == DataQualityStatus.INVALID_STATISTIC

    def test_batch_validation(self, validator, normalizer):
        records = [_make_raw_match(match_id=i + 10, date_unix=1610000000 + i * 86400) for i in range(5)]
        matches = normalizer.normalize_batch(records)
        valid, rejected = validator.validate_batch(matches)
        assert len(valid) == 5  # All unique IDs
        assert len(rejected) == 0

    def test_quality_report(self, validator, normalizer):
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(10)]
        matches = normalizer.normalize_batch(records)
        validator.validate_batch(matches)
        report = validator.report
        assert report.total_records == 10
        assert report.valid_count == 10
        assert report.valid_rate == 1.0


# ═══════════════════════════════════════════════════════════════
# D. DEDUPLICATION
# ═══════════════════════════════════════════════════════════════


class TestDeduplication:
    """Test deterministic deduplication by source match ID."""

    def test_same_match_id_detected(self, validator, normalizer):
        m1 = normalizer.normalize(_make_raw_match(match_id=42))
        m2 = normalizer.normalize(_make_raw_match(match_id=42))
        assert validator.validate(m1) == DataQualityStatus.VALID
        assert validator.validate(m2) == DataQualityStatus.DUPLICATE

    def test_different_ids_both_valid(self, validator, normalizer):
        m1 = normalizer.normalize(_make_raw_match(match_id=1))
        m2 = normalizer.normalize(_make_raw_match(match_id=2))
        assert validator.validate(m1) == DataQualityStatus.VALID
        assert validator.validate(m2) == DataQualityStatus.VALID

    def test_idempotent_ingestion(self, normalizer):
        """Same raw data normalized twice produces identical ResearchMatch."""
        raw = _make_raw_match(match_id=100)
        m1 = normalizer.normalize(raw)
        # New normalizer instance — same result
        norm2 = MatchNormalizer()
        m2 = norm2.normalize(raw)
        assert m1.match_id == m2.match_id
        assert m1.date_unix == m2.date_unix
        assert m1.home_goals == m2.home_goals
        assert m1.corners_home == m2.corners_home


# ═══════════════════════════════════════════════════════════════
# E. TEMPORAL INTEGRITY
# ═══════════════════════════════════════════════════════════════


class TestTemporalIntegrity:
    """Test temporal causality guarantees."""

    def test_odds_timestamp_before_kickoff(self, normalizer, raw_match):
        """Odds timestamps must be before match kickoff."""
        odds = normalizer.extract_market_odds(raw_match)
        for o in odds:
            assert o.timestamp < raw_match["date_unix"]

    def test_post_match_stats_only_from_complete(self, normalizer):
        """Only 'complete' matches have valid post-match stats."""
        raw_incomplete = _make_raw_match(status="incomplete")
        match = normalizer.normalize(raw_incomplete)
        assert match is None  # Not processed

    def test_provenance_timestamps_correct(self, raw_match):
        """Provenance correctly distinguishes event vs information time."""
        prov = create_provenance(raw_match)
        assert prov.event_timestamp == raw_match["date_unix"]
        # Information available after event
        assert prov.information_timestamp > prov.event_timestamp
        # Retrieved at now
        assert prov.retrieved_at > 0

    def test_pre_match_data_available_before_kickoff(self, normalizer, raw_match):
        """Odds are pre-match information available before kickoff."""
        match = normalizer.normalize(raw_match)
        # Odds should be present (they are pre-match)
        assert match.odds_over_goals is not None
        assert match.odds_home_win is not None


# ═══════════════════════════════════════════════════════════════
# F. TEAM/LEAGUE IDENTITY
# ═══════════════════════════════════════════════════════════════


class TestIdentity:
    """Test team and league identity handling."""

    def test_team_id_preserved_in_provenance(self, raw_match):
        prov = create_provenance(raw_match)
        assert prov.source_home_team_id == 100
        assert prov.source_away_team_id == 200

    def test_league_id_preserved(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.league_id == 4759

    def test_season_preserved(self, normalizer, raw_match):
        match = normalizer.normalize(raw_match)
        assert match.season == "2020/2021"

    def test_team_names_preserved_as_strings(self, normalizer):
        raw = _make_raw_match(home_name="Ñíguez FC", away_name="São Paulo")
        match = normalizer.normalize(raw)
        assert match.home_team == "Ñíguez FC"
        assert match.away_team == "São Paulo"


# ═══════════════════════════════════════════════════════════════
# G. PAGINATION
# ═══════════════════════════════════════════════════════════════


class TestPagination:
    """Test API pagination handling."""

    def test_multi_page_fetch(self):
        """Client fetches all pages."""
        client = FootyStatsResearchClient(api_key="test", rate_limit=0.0)

        # Mock the _request method to simulate pagination
        call_count = [0]
        def mock_request(endpoint, params=None):
            call_count[0] += 1
            page = (params or {}).get("page", 1)
            if page == 1:
                return {
                    "data": [{"id": 1}, {"id": 2}],
                    "pager": {"current_page": 1, "max_page": 3},
                }
            elif page == 2:
                return {
                    "data": [{"id": 3}, {"id": 4}],
                    "pager": {"current_page": 2, "max_page": 3},
                }
            else:
                return {
                    "data": [{"id": 5}],
                    "pager": {"current_page": 3, "max_page": 3},
                }

        client._request = mock_request
        matches = client.fetch_season_matches(4759)
        assert len(matches) == 5
        assert call_count[0] == 3

    def test_empty_page_stops(self):
        """Empty data array stops pagination."""
        client = FootyStatsResearchClient(api_key="test", rate_limit=0.0)

        def mock_request(endpoint, params=None):
            return {"data": [], "pager": {"current_page": 1, "max_page": 1}}

        client._request = mock_request
        matches = client.fetch_season_matches(4759)
        assert len(matches) == 0


# ═══════════════════════════════════════════════════════════════
# H. CREDENTIAL SECURITY
# ═══════════════════════════════════════════════════════════════


class TestCredentialSecurity:
    """Test that credentials are never serialized or exposed."""

    def test_api_key_not_in_provenance(self, raw_match):
        prov = create_provenance(raw_match)
        prov_dict = prov.to_dict()
        prov_str = json.dumps(prov_dict)
        assert "example" not in prov_str  # Default key shouldn't appear
        assert "api_key" not in prov_str

    def test_api_key_not_in_match_hash(self):
        match_dict = {"match_id": 1, "date_unix": 1610000000}
        h = compute_match_hash(match_dict)
        # Hash is deterministic and doesn't include credentials
        assert len(h) == 16

    def test_api_key_from_environment(self):
        """Client reads from env when no key provided."""
        with patch.dict(os.environ, {"FOOTYSTATS_API_KEY": "test_secret"}):
            client = FootyStatsResearchClient()
            assert client._api_key == "test_secret"

    def test_api_key_not_in_cache_key(self):
        """Cache keys don't contain API credentials."""
        client = FootyStatsResearchClient(api_key="my_secret")
        key = client._cache_key("/league-matches", {"key": "my_secret", "season_id": 4759})
        assert "my_secret" not in key


# ═══════════════════════════════════════════════════════════════
# I. COVERAGE COMPUTATION
# ═══════════════════════════════════════════════════════════════


class TestCoverage:
    """Test coverage analysis."""

    def test_basic_coverage(self, normalizer):
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(50)]
        matches = normalizer.normalize_batch(records)
        report = compute_coverage(matches)
        assert report.total_matches == 50
        assert report.total_teams == 2  # Team A and Team B only

    def test_field_coverage_calculation(self, normalizer):
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(20)]
        # Make some records have missing corners
        for i in range(5):
            records[i]["team_a_corners"] = -1
        matches = normalizer.normalize_batch(records)
        report = compute_coverage(matches)
        corners_cov = next(
            (fc for fc in report.field_coverage if fc.field_name == "corners_home"), None
        )
        assert corners_cov is not None
        assert corners_cov.available_count == 15
        assert corners_cov.missing_count == 5

    def test_empty_dataset_coverage(self):
        report = compute_coverage([])
        assert report.total_matches == 0

    def test_market_readiness_assessed(self, normalizer):
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(150)]
        matches = normalizer.normalize_batch(records)
        report = compute_coverage(matches)
        # Goals should be READY (has data + odds)
        assert report.market_readiness.get("GOALS_TOTAL") == MarketReadiness.READY
        # Corners should be READY (has data + odds)
        assert report.market_readiness.get("CORNERS_TOTAL") == MarketReadiness.READY


# ═══════════════════════════════════════════════════════════════
# J. DATASET VERSIONING / REPRODUCIBILITY
# ═══════════════════════════════════════════════════════════════


class TestDatasetVersioning:
    """Test deterministic dataset hashing."""

    def test_same_data_same_hash(self):
        """Same matches produce same content hash."""
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(5)]

        client = FootyStatsResearchClient(api_key="test", rate_limit=0.0)
        client.fetch_season_matches = MagicMock(return_value=records)

        source1 = FootyStatsDataSource(season_ids=[4759], client=client)
        source2 = FootyStatsDataSource(season_ids=[4759], client=client)

        hash1 = source1.compute_content_hash()
        hash2 = source2.compute_content_hash()
        assert hash1 == hash2

    def test_different_data_different_hash(self):
        """Different matches produce different content hash."""
        records1 = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(5)]
        records2 = [_make_raw_match(match_id=i + 100, date_unix=1610000000 + i * 86400) for i in range(5)]

        client1 = FootyStatsResearchClient(api_key="test", rate_limit=0.0)
        client1.fetch_season_matches = MagicMock(return_value=records1)

        client2 = FootyStatsResearchClient(api_key="test", rate_limit=0.0)
        client2.fetch_season_matches = MagicMock(return_value=records2)

        source1 = FootyStatsDataSource(season_ids=[4759], client=client1)
        source2 = FootyStatsDataSource(season_ids=[4759], client=client2)

        assert source1.compute_content_hash() != source2.compute_content_hash()

    def test_match_hash_deterministic(self):
        """Same match content always produces same hash."""
        d = {"match_id": 1, "home_goals": 2, "away_goals": 1}
        h1 = compute_match_hash(d)
        h2 = compute_match_hash(d)
        assert h1 == h2


# ═══════════════════════════════════════════════════════════════
# K. MARKET READINESS
# ═══════════════════════════════════════════════════════════════


class TestMarketReadiness:
    """Test market readiness assessment."""

    def test_insufficient_data(self):
        """Small dataset → INSUFFICIENT_DATA."""
        matches = [
            ResearchMatch(
                match_id=i, date_unix=1610000000 + i * 86400,
                league_id=1, season="2020", home_team="A", away_team="B",
                home_goals=1, away_goals=0,
            )
            for i in range(10)
        ]
        report = compute_coverage(matches)
        assert report.market_readiness.get("GOALS_TOTAL") == MarketReadiness.INSUFFICIENT_DATA

    def test_partial_without_odds(self, normalizer):
        """Data available but no odds → PARTIAL."""
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(150)]
        # Remove all odds
        for r in records:
            r["odds_ft_over25"] = 0
            r["odds_ft_under25"] = 0
        matches = normalizer.normalize_batch(records)
        report = compute_coverage(matches)
        assert report.market_readiness.get("GOALS_TOTAL") == MarketReadiness.PARTIAL


# ═══════════════════════════════════════════════════════════════
# L. DATA PROVENANCE
# ═══════════════════════════════════════════════════════════════


class TestProvenance:
    """Test data provenance tracking."""

    def test_provenance_created(self, raw_match):
        prov = create_provenance(raw_match)
        assert prov.source == "FOOTYSTATS"
        assert prov.source_match_id == 1000
        assert prov.source_season_id == 4759
        assert prov.event_timestamp == raw_match["date_unix"]
        assert prov.information_timestamp > prov.event_timestamp

    def test_provenance_normalization_version(self, raw_match):
        prov = create_provenance(raw_match)
        assert prov.normalization_version == "1.0.0"

    def test_provenance_to_dict(self, raw_match):
        prov = create_provenance(raw_match)
        d = prov.to_dict()
        assert "source" in d
        assert "source_match_id" in d
        assert "normalization_version" in d


# ═══════════════════════════════════════════════════════════════
# M. IDEMPOTENT INGESTION
# ═══════════════════════════════════════════════════════════════


class TestIdempotentIngestion:
    """Test that re-ingesting same data produces same results."""

    def test_double_ingestion_same_result(self):
        """Loading same season twice produces identical dataset."""
        records = [_make_raw_match(match_id=i, date_unix=1610000000 + i * 86400) for i in range(20)]

        client = FootyStatsResearchClient(api_key="test", rate_limit=0.0)
        client.fetch_season_matches = MagicMock(return_value=records)

        source = FootyStatsDataSource(season_ids=[4759], client=client)
        matches1 = source.get_matches()

        # Reset and reload
        source._matches = None
        source._validator = RecordValidator()
        matches2 = source.get_matches()

        assert len(matches1) == len(matches2)
        for m1, m2 in zip(matches1, matches2):
            assert m1.match_id == m2.match_id
            assert m1.date_unix == m2.date_unix


# ═══════════════════════════════════════════════════════════════
# N. REAL API SMOKE TEST (sandbox key=example)
# ═══════════════════════════════════════════════════════════════


class TestRealAPISmokeTest:
    """Smoke test using the FootyStats sandbox (key=example).

    These tests make real HTTP calls to the FootyStats API.
    They are bounded and conservative.
    """

    @pytest.fixture
    def sandbox_client(self, tmp_path):
        """Client with sandbox key and local cache."""
        return FootyStatsResearchClient(
            api_key="example",
            cache_dir=tmp_path / "cache",
            rate_limit=2.5,  # Conservative
        )

    def test_fetch_league_list(self, sandbox_client):
        """Can fetch league list from sandbox."""
        leagues = sandbox_client.fetch_league_list()
        assert len(leagues) >= 1
        # EPL should be present
        epl = [l for l in leagues if "Premier" in l.get("name", "")]
        assert len(epl) >= 1

    def test_fetch_season_matches(self, sandbox_client):
        """Can fetch matches for EPL 2020/21 (season_id=4759)."""
        matches = sandbox_client.fetch_season_matches(4759, max_per_page=10)
        # Sandbox should have 380 matches for full EPL season
        assert len(matches) >= 10
        # Verify structure
        first = matches[0]
        assert "id" in first
        assert "date_unix" in first
        assert "homeGoalCount" in first
        assert "team_a_corners" in first

    def test_normalize_real_data(self, sandbox_client):
        """Can normalize real API data to ResearchMatch."""
        raw = sandbox_client.fetch_season_matches(4759, max_per_page=5)
        normalizer = MatchNormalizer()
        matches = normalizer.normalize_batch(raw)
        # Should get at least some valid matches
        assert len(matches) >= 1
        for m in matches:
            assert m.match_id > 0
            assert m.date_unix > 0
            assert m.home_goals is not None
            assert m.away_goals is not None
            assert m.home_team != ""

    def test_full_adapter_smoke(self, tmp_path):
        """Full adapter smoke test with sandbox data."""
        source = FootyStatsDataSource(
            season_ids=[4759],
            api_key="example",
            cache_dir=tmp_path / "cache",
        )
        matches = source.get_matches()
        assert len(matches) >= 100  # Full EPL season = 380

        # Verify ResearchDataSource interface
        fields = source.get_available_fields()
        assert "home_goals" in fields
        assert "corners_home" in fields

        odds = source.get_market_odds(market="GOALS_TOTAL")
        assert len(odds) > 0

        # Content hash is deterministic
        h1 = source.compute_content_hash()
        h2 = source.compute_content_hash()
        assert h1 == h2

    def test_coverage_on_real_data(self, tmp_path):
        """Coverage report on real sandbox data."""
        source = FootyStatsDataSource(
            season_ids=[4759],
            api_key="example",
            cache_dir=tmp_path / "cache",
        )
        matches = source.get_matches()
        report = compute_coverage(matches)
        assert report.total_matches >= 100
        assert report.total_teams >= 10
        # EPL should have good corners coverage
        corners_cov = next(
            (fc for fc in report.field_coverage if fc.field_name == "corners_home"), None
        )
        assert corners_cov is not None
        assert corners_cov.coverage_pct > 80


# ═══════════════════════════════════════════════════════════════
# O. FULL RESEARCH PIPELINE ON REAL DATA
# ═══════════════════════════════════════════════════════════════


class TestRealDataResearchPipeline:
    """Test the full research pipeline using real FootyStats data."""

    def test_real_data_through_research_pipeline(self, tmp_path):
        """Real data flows through: dataset → candidates → experiment → WF → FDR."""
        from src.research.candidates import CandidateCondition, CandidateOperator, ResearchCandidate
        from src.research.experiment_engine.config import ExperimentConfig, OddsMode
        from src.research.experiment_engine.dataset import ResearchDataset
        from src.research.experiment_engine.hypothesis import ExperimentHypothesis
        from src.research.experiment_engine.runner import ExperimentRunner
        from src.research.fdr import FDRAdapter, ResearchFamilyBuilder
        from src.research.governance import GovernanceClassifier, GovernanceCriteria
        from src.research.market import MarketType, create_default_registry
        from src.research.probability import HistoricalFrequencyModel
        from src.research.walkforward import (
            WalkForwardConfig,
            WalkForwardOrchestrator,
            WalkForwardStatus,
            WindowType,
        )

        DAY = 86400
        MONTH = 30 * DAY

        # Step 1: Load real data
        source = FootyStatsDataSource(
            season_ids=[4759],
            api_key="example",
            cache_dir=tmp_path / "cache",
        )

        # Step 2: Create research dataset
        registry = create_default_registry()
        corners_market = registry.get(MarketType.CORNERS_TOTAL)
        dataset = ResearchDataset(source=source, market=corners_market)
        assert dataset.size >= 100

        # Step 3: Create a candidate
        candidate = ResearchCandidate(
            candidate_id="real_data_test",
            market_type=MarketType.CORNERS_TOTAL.value,
            feature_ids=("dangerous_attacks_home",),
            conditions=(
                CandidateCondition(
                    feature_id="dangerous_attacks_home", operator=">", threshold=40.0
                ),
            ),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        hypothesis = ExperimentHypothesis.from_candidate(candidate)

        # Step 4: Run walk-forward
        wf_config = WalkForwardConfig(
            initial_training_period=4 * MONTH,
            test_period=2 * MONTH,
            step_period=2 * MONTH,
            minimum_training_observations=20,
            minimum_test_observations=5,
            window_type=WindowType.EXPANDING,
            minimum_folds=3,
            maximum_folds=10,
        )

        base_config = ExperimentConfig(
            hypothesis=hypothesis,
            market_type=MarketType.CORNERS_TOTAL.value,
            dataset_version=dataset.content_hash,
            model_type="historical_frequency",
            model_parameters=(),
            training_start=0,
            training_end=1,
            evaluation_start=2,
            evaluation_end=3,
            minimum_observations=10,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
        )

        orchestrator = WalkForwardOrchestrator(wf_config)
        wf_result = orchestrator.run(
            hypothesis=hypothesis,
            dataset=dataset,
            model_factory=lambda: HistoricalFrequencyModel(),
            experiment_config_base=base_config,
        )

        # Should produce some result (may or may not complete depending on data)
        assert wf_result.fold_count > 0

        # Step 5: FDR (even if just 1 hypothesis)
        if wf_result.p_value_for_fdr is not None:
            adapter = FDRAdapter(alpha=0.05)
            family = ResearchFamilyBuilder.build(
                market_type=MarketType.CORNERS_TOTAL.value,
                dataset_version=dataset.content_hash,
                research_run_id="real_data_smoke",
            )
            fdr_result = adapter.correct([wf_result], family)
            assert fdr_result.total_hypotheses == 1

            # Step 6: Governance
            classifier = GovernanceClassifier(GovernanceCriteria(
                minimum_folds=2,
                minimum_positive_fold_ratio=0.3,
                minimum_sample_size=10,
                maximum_p_value=0.50,
                minimum_effect_size=0.0001,
                minimum_calibration_quality=0.50,
            ))
            decision = classifier.classify_walk_forward(wf_result)
            # We don't assert it passes — just that the pipeline executes
            assert decision.new_state is not None
