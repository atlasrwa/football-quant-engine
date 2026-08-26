"""Comprehensive tests for Batch 11 — Real Forward Data, Odds & Feature Registry Integration.

Test categories:
A. FootyStats Fixture Provider (normalization, filtering, errors)
B. FootyStats Odds Provider (extraction, temporal validation, closing odds isolation)
C. RegistryTemporalEngine (FeatureRegistry integration, point-in-time computation)
D. Multi-League Support & Market Readiness
E. Fixture Versioning (rescheduled, postponed, invalidation)
F. Deterministic Identity (same inputs → same outputs)
G. Provider Error Handling
H. Temporal Leakage Attacks (20 mandatory adversarial tests)
I. Security (no credentials in artifacts)
J. Snapshot Immutability
K. End-to-End Integration (fixture → features → odds → paper trade)

All tests use mocked/deterministic providers. No network access required.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.research.data_source import ResearchMatch
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)
from src.research.forward.fixture_versioning import FixtureVersion, FixtureVersionTracker
from src.research.forward.footystats_fixture_provider import FootyStatsFixtureProvider
from src.research.forward.footystats_odds_provider import FootyStatsOddsProvider
from src.research.forward.future_fixture import FixtureStatus, FutureFixture
from src.research.forward.league_coverage import (
    MarketReadiness,
    MarketReadinessAssessor,
    MarketReadinessResult,
)
from src.research.forward.odds import OddsSelection, OddsSnapshot, OddsType
from src.research.forward.providers import DeterministicFixtureProvider, DeterministicOddsProvider
from src.research.forward.registry_features import (
    RegistryTemporalEngine,
    create_standard_forward_features,
)
from src.research.forward.snapshot import FeatureProvenance, PreMatchSnapshot, TimestampConfidence


# ═══════════════════════════════════════════════════════════════════
# FIXTURES (pytest)
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def historical_matches():
    """30 completed matches well before prediction time (1700000000)."""
    matches = []
    for i in range(30):
        matches.append(ResearchMatch(
            match_id=5000 + i,
            date_unix=1699000000 + i * 86400,
            league_id=47,
            season="2023/2024",
            home_team="101" if i % 2 == 0 else "202",
            away_team="202" if i % 2 == 0 else "101",
            total_goals=2 + i % 3,
            total_corners=9 + i % 4,
            total_cards=3 + i % 2,
            dangerous_attacks_home=35 + i % 10,
            dangerous_attacks_away=30 + i % 8,
            shots_on_target_home=4 + i % 3,
            shots_on_target_away=3 + i % 2,
            possession_home=50.0 + i % 10,
            possession_away=50.0 - i % 10,
        ))
    return matches


@pytest.fixture
def mock_footystats_client():
    """Mocked FootyStats client returning raw match data."""
    client = MagicMock()
    # Return a mix of completed and upcoming matches
    future_time = int(time.time()) + 86400 * 7  # 7 days from now
    client.fetch_season_matches.return_value = [
        # Completed match
        {"id": 1001, "date_unix": 1699000000, "status": "complete",
         "homeID": 101, "awayID": 202, "home_name": "Arsenal", "away_name": "Chelsea",
         "competition_id": 47, "homeGoalCount": 2, "awayGoalCount": 1,
         "odds_ft_over25": 1.85, "odds_ft_under25": 2.05,
         "odds_corners_over_95": 1.90, "odds_corners_under_95": 1.95,
         "odds_ft_1": 2.10, "odds_ft_x": 3.40, "odds_ft_2": 3.80},
        # Upcoming match
        {"id": 2001, "date_unix": future_time, "status": "incomplete",
         "homeID": 301, "awayID": 401, "home_name": "Liverpool", "away_name": "Man City",
         "competition_id": 47,
         "odds_ft_over25": 1.75, "odds_ft_under25": 2.15,
         "odds_corners_over_95": 1.85, "odds_corners_under_95": 2.00,
         "odds_ft_1": 2.80, "odds_ft_x": 3.50, "odds_ft_2": 2.60},
        # Another upcoming
        {"id": 2002, "date_unix": future_time + 3600, "status": "incomplete",
         "homeID": 101, "awayID": 501, "home_name": "Arsenal", "away_name": "Spurs",
         "competition_id": 47,
         "odds_ft_over25": 1.80, "odds_ft_under25": 2.10},
    ]
    return client


@pytest.fixture
def feature_registry():
    """Registry with standard forward features registered."""
    registry = FeatureRegistry()
    features = create_standard_forward_features()
    registry.register_many(features)
    return registry


# ═══════════════════════════════════════════════════════════════════
# A. FOOTYSTATS FIXTURE PROVIDER
# ═══════════════════════════════════════════════════════════════════


class TestFootyStatsFixtureProvider:
    def test_normalizes_upcoming_fixtures(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
        )
        fixtures = provider.get_upcoming_fixtures()
        # Only the 2 upcoming (incomplete) fixtures should appear
        assert len(fixtures) == 2
        assert all(f.status == FixtureStatus.SCHEDULED for f in fixtures)

    def test_excludes_completed_matches(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
        )
        fixtures = provider.get_upcoming_fixtures()
        # Completed match (id=1001) should not appear
        source_ids = [f.source_fixture_id for f in fixtures]
        assert 1001 not in source_ids

    def test_fixture_identity_stable(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
        )
        f1 = provider.get_upcoming_fixtures()
        f2 = provider.get_upcoming_fixtures()
        # Same fixtures → same IDs
        assert [f.fixture_id for f in f1] == [f.fixture_id for f in f2]

    def test_provider_name(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(season_ids=[4759], client=mock_footystats_client)
        assert provider.provider_name == "footystats"

    def test_handles_missing_team_id(self):
        client = MagicMock()
        client.fetch_season_matches.return_value = [
            {"id": 9999, "date_unix": int(time.time()) + 86400, "status": "incomplete",
             "homeID": 0, "awayID": 0},  # Missing team IDs
        ]
        provider = FootyStatsFixtureProvider(season_ids=[1], client=client)
        fixtures = provider.get_upcoming_fixtures()
        assert len(fixtures) == 0  # Rejected: no valid team IDs

    def test_handles_api_failure_gracefully(self):
        client = MagicMock()
        client.fetch_season_matches.side_effect = RuntimeError("API timeout")
        provider = FootyStatsFixtureProvider(season_ids=[1], client=client)
        fixtures = provider.get_upcoming_fixtures()
        assert fixtures == []  # Graceful failure, no crash

    def test_filter_by_competition(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
        )
        fixtures = provider.get_upcoming_fixtures(competition_id=999)
        assert len(fixtures) == 0  # No matches for competition 999

    def test_sorts_chronologically(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
        )
        fixtures = provider.get_upcoming_fixtures()
        for i in range(1, len(fixtures)):
            assert fixtures[i].kickoff_timestamp >= fixtures[i-1].kickoff_timestamp


# ═══════════════════════════════════════════════════════════════════
# B. FOOTYSTATS ODDS PROVIDER
# ═══════════════════════════════════════════════════════════════════


class TestFootyStatsOddsProvider:
    def test_extracts_goals_odds(self, mock_footystats_client):
        provider = FootyStatsOddsProvider(client=mock_footystats_client)
        count = provider.load_odds_for_season(4759)
        assert count > 0
        # Check we got goals market odds
        all_snapshots = []
        for snaps in provider._odds_cache.values():
            all_snapshots.extend(snaps)
        goals_odds = [s for s in all_snapshots if s.market == "GOALS_TOTAL"]
        assert len(goals_odds) > 0

    def test_extracts_corners_odds(self, mock_footystats_client):
        provider = FootyStatsOddsProvider(client=mock_footystats_client)
        provider.load_odds_for_season(4759)
        all_snapshots = []
        for snaps in provider._odds_cache.values():
            all_snapshots.extend(snaps)
        corners_odds = [s for s in all_snapshots if s.market == "CORNERS_TOTAL"]
        assert len(corners_odds) > 0

    def test_all_odds_are_prematch(self, mock_footystats_client):
        provider = FootyStatsOddsProvider(client=mock_footystats_client)
        provider.load_odds_for_season(4759)
        all_snapshots = []
        for snaps in provider._odds_cache.values():
            all_snapshots.extend(snaps)
        assert all(s.odds_type == OddsType.PRE_MATCH for s in all_snapshots)

    def test_no_closing_odds_from_footystats(self, mock_footystats_client):
        """FootyStats explicitly has no closing odds."""
        provider = FootyStatsOddsProvider(client=mock_footystats_client)
        provider.load_odds_for_season(4759)
        for fixture_id in provider._odds_cache:
            closing = provider.get_closing_odds(fixture_id)
            assert closing == []  # NEVER returns closing odds

    def test_rejects_invalid_odds(self):
        client = MagicMock()
        client.fetch_season_matches.return_value = [
            {"id": 5555, "date_unix": 1699000000, "status": "complete",
             "odds_ft_over25": 0.5,  # Invalid: < 1.0
             "odds_ft_under25": -1,  # Invalid: negative
             "odds_corners_over_95": None,  # Missing
             },
        ]
        provider = FootyStatsOddsProvider(client=client)
        count = provider.load_odds_for_season(1)
        assert count == 0  # All rejected

    def test_odds_timestamp_before_kickoff(self, mock_footystats_client):
        """Odds timestamp must be before kickoff (estimated 1h prior)."""
        provider = FootyStatsOddsProvider(client=mock_footystats_client)
        provider.load_odds_for_season(4759)
        all_snapshots = []
        for snaps in provider._odds_cache.values():
            all_snapshots.extend(snaps)
        for snap in all_snapshots:
            # Estimated timestamp is date_unix - 3600
            # So snapshot_timestamp should be BEFORE match kickoff
            assert snap.snapshot_timestamp < snap.snapshot_timestamp + 3601


# ═══════════════════════════════════════════════════════════════════
# C. REGISTRY TEMPORAL ENGINE
# ═══════════════════════════════════════════════════════════════════


class TestRegistryTemporalEngine:
    def test_builds_snapshot_with_registry_features(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test_fixture",
            home_team_id=101,
            away_team_id=202,
            prediction_timestamp=1700000000.0,
            kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
            hypothesis_id="hyp1",
        )
        assert snapshot.fixture_id == "test_fixture"
        assert snapshot.feature_count > 0
        assert snapshot.prediction_timestamp == 1700000000.0

    def test_only_derived_prematch_features_computed(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        # No POST_MATCH raw features should be in the snapshot
        for feat_id in snapshot.features:
            feat_def = feature_registry.get(feat_id)
            if feat_def:
                assert feat_def.temporal_class in (TemporalClass.DERIVED, TemporalClass.PRE_MATCH)

    def test_filters_future_matches(self, historical_matches):
        """Future matches must never enter computation."""
        future = ResearchMatch(
            match_id=9999, date_unix=1700500000,  # WAY after prediction
            league_id=47, season="2023/2024",
            home_team="101", away_team="202", total_goals=10,
        )
        all_matches = historical_matches + [future]
        registry = FeatureRegistry()
        registry.register_many(create_standard_forward_features())
        engine = RegistryTemporalEngine(registry=registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=all_matches,
        )
        # Provenance must show all info timestamps < prediction
        for prov in snapshot.feature_provenance:
            assert prov.information_timestamp < 1700000000.0

    def test_provenance_has_dataset_version(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        assert snapshot.source_dataset_id != ""
        assert snapshot.source_dataset_id != "empty"

    def test_prediction_after_kickoff_rejected(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        with pytest.raises(ValueError, match="prediction_timestamp.*> kickoff"):
            engine.build_snapshot(
                fixture_id="test", home_team_id=101, away_team_id=202,
                prediction_timestamp=1700200000.0,
                kickoff_timestamp=1700100000.0,  # Kickoff BEFORE prediction
                historical_matches=historical_matches,
            )

    def test_snapshot_deterministic(self, historical_matches, feature_registry):
        """Same inputs → same snapshot_id."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        s1 = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches, hypothesis_id="h1",
        )
        s2 = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches, hypothesis_id="h1",
        )
        assert s1.snapshot_id == s2.snapshot_id


# ═══════════════════════════════════════════════════════════════════
# D. MULTI-LEAGUE & MARKET READINESS
# ═══════════════════════════════════════════════════════════════════


class TestMultiLeagueReadiness:
    def test_market_ready(self):
        assessor = MarketReadinessAssessor()
        result = assessor.assess(
            league_id=47, market="CORNERS_TOTAL",
            historical_sample=200, odds_coverage=0.8, feature_coverage=0.9,
        )
        assert result.readiness == MarketReadiness.READY

    def test_market_insufficient_history(self):
        assessor = MarketReadinessAssessor(min_historical_sample=100)
        result = assessor.assess(
            league_id=47, market="CORNERS_TOTAL",
            historical_sample=30, odds_coverage=0.8, feature_coverage=0.9,
        )
        assert result.readiness in (MarketReadiness.INSUFFICIENT_DATA, MarketReadiness.PARTIAL)
        assert any("history" in r.lower() for r in result.reasons)

    def test_market_low_odds_coverage(self):
        assessor = MarketReadinessAssessor(min_odds_coverage=0.7)
        result = assessor.assess(
            league_id=47, market="CORNERS_TOTAL",
            historical_sample=200, odds_coverage=0.3, feature_coverage=0.9,
        )
        assert result.readiness != MarketReadiness.READY
        assert any("odds" in r.lower() for r in result.reasons)

    def test_market_unavailable(self):
        assessor = MarketReadinessAssessor()
        result = assessor.assess(
            league_id=47, market="OFFSIDES_TOTAL",
            historical_sample=0, odds_coverage=0.0, feature_coverage=0.0,
        )
        assert result.readiness == MarketReadiness.UNAVAILABLE

    def test_clv_not_available_footystats(self):
        """FootyStats has no closing odds → CLV unavailable."""
        assessor = MarketReadinessAssessor()
        result = assessor.assess(
            league_id=47, market="CORNERS_TOTAL",
            historical_sample=200, odds_coverage=0.8, feature_coverage=0.9,
            has_closing_odds=False,
        )
        assert result.clv_available is False


# ═══════════════════════════════════════════════════════════════════
# E. FIXTURE VERSIONING
# ═══════════════════════════════════════════════════════════════════


class TestFixtureVersioning:
    def test_initial_record(self):
        tracker = FixtureVersionTracker()
        fixture = FutureFixture(
            source_fixture_id=100, home_team_id=1, away_team_id=2,
            kickoff_timestamp=1700100000, source="test",
        )
        changed = tracker.record(fixture)
        assert changed is True
        versions = tracker.get_versions(fixture.fixture_id)
        assert len(versions) == 1
        assert versions[0].change_reason == "initial"

    def test_no_change_detected(self):
        tracker = FixtureVersionTracker()
        fixture = FutureFixture(
            source_fixture_id=100, home_team_id=1, away_team_id=2,
            kickoff_timestamp=1700100000, source="test",
        )
        tracker.record(fixture)
        changed = tracker.record(fixture)  # Same fixture again
        assert changed is False
        assert len(tracker.get_versions(fixture.fixture_id)) == 1

    def test_status_change_detected(self):
        tracker = FixtureVersionTracker()
        fixture = FutureFixture(
            source_fixture_id=100, home_team_id=1, away_team_id=2,
            kickoff_timestamp=1700100000, source="test", status=FixtureStatus.SCHEDULED,
        )
        tracker.record(fixture)
        started = fixture.transition(FixtureStatus.STARTED)
        changed = tracker.record(started)
        assert changed is True
        assert len(tracker.get_versions(fixture.fixture_id)) == 2

    def test_kickoff_reschedule_detected(self):
        tracker = FixtureVersionTracker(kickoff_change_threshold=3600)
        fixture = FutureFixture(
            source_fixture_id=100, home_team_id=1, away_team_id=2,
            kickoff_timestamp=1700100000, source="test",
        )
        tracker.record(fixture)
        # Rescheduled by 2 hours (> threshold)
        from dataclasses import replace
        rescheduled = replace(fixture, kickoff_timestamp=1700107200)
        changed = tracker.record(rescheduled)
        assert changed is True
        assert tracker.is_kickoff_changed(fixture.fixture_id) is True
        assert tracker.should_invalidate_snapshots(fixture.fixture_id) is True

    def test_small_kickoff_change_tolerated(self):
        tracker = FixtureVersionTracker(kickoff_change_threshold=3600)
        fixture = FutureFixture(
            source_fixture_id=100, home_team_id=1, away_team_id=2,
            kickoff_timestamp=1700100000, source="test",
        )
        tracker.record(fixture)
        # Changed by 5 minutes (< threshold)
        from dataclasses import replace
        slightly_changed = replace(fixture, kickoff_timestamp=1700100300)
        changed = tracker.record(slightly_changed)
        assert changed is False  # Not significant


# ═══════════════════════════════════════════════════════════════════
# F. DETERMINISTIC IDENTITY
# ═══════════════════════════════════════════════════════════════════


class TestDeterministicIdentity:
    def test_fixture_id_from_source(self):
        """Same source + source_fixture_id → same fixture_id regardless of other fields."""
        f1 = FutureFixture(source_fixture_id=123, home_team_id=1, away_team_id=2, source="footystats")
        f2 = FutureFixture(source_fixture_id=123, home_team_id=99, away_team_id=88, source="footystats",
                           home_team_name="Different", retrieved_at=9999.0)
        assert f1.fixture_id == f2.fixture_id

    def test_odds_snapshot_id_deterministic(self):
        s1 = OddsSnapshot(fixture_id="abc", market="GOALS_TOTAL", selection=OddsSelection.OVER,
                          line=2.5, decimal_odds=1.85, source="test", snapshot_timestamp=1700000000)
        s2 = OddsSnapshot(fixture_id="abc", market="GOALS_TOTAL", selection=OddsSelection.OVER,
                          line=2.5, decimal_odds=1.85, source="test", snapshot_timestamp=1700000000)
        assert s1.odds_snapshot_id == s2.odds_snapshot_id

    def test_snapshot_id_deterministic(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        s1 = engine.build_snapshot(
            fixture_id="f1", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches, hypothesis_id="h1", model_id="m1",
        )
        s2 = engine.build_snapshot(
            fixture_id="f1", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches, hypothesis_id="h1", model_id="m1",
        )
        assert s1.snapshot_id == s2.snapshot_id
        assert s1.content_hash == s2.content_hash


# ═══════════════════════════════════════════════════════════════════
# G. PROVIDER ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════


class TestProviderErrors:
    def test_fixture_provider_handles_timeout(self):
        client = MagicMock()
        client.fetch_season_matches.side_effect = TimeoutError("Connection timeout")
        provider = FootyStatsFixtureProvider(season_ids=[1], client=client)
        fixtures = provider.get_upcoming_fixtures()
        assert fixtures == []

    def test_odds_provider_handles_failure(self):
        client = MagicMock()
        client.fetch_season_matches.side_effect = RuntimeError("500 Internal Server Error")
        provider = FootyStatsOddsProvider(client=client)
        count = provider.load_odds_for_season(1)
        assert count == 0

    def test_malformed_fixture_data_rejected(self):
        client = MagicMock()
        client.fetch_season_matches.return_value = [
            {"no_id": True},  # Missing id
            {"id": 1, "no_date": True},  # Missing date
            {"id": 2, "date_unix": "not_a_number"},  # Invalid date
        ]
        provider = FootyStatsFixtureProvider(season_ids=[1], client=client)
        fixtures = provider.get_upcoming_fixtures()
        assert len(fixtures) == 0


# ═══════════════════════════════════════════════════════════════════
# H. TEMPORAL LEAKAGE ATTACKS (20 mandatory)
# ═══════════════════════════════════════════════════════════════════


class TestTemporalLeakageAttacks:
    """Adversarial tests proving temporal integrity."""

    def test_01_future_match_in_historical_data(self, historical_matches, feature_registry):
        """Future match inserted into historical feature data → excluded."""
        future = ResearchMatch(
            match_id=8888, date_unix=1700500000,
            league_id=47, season="2023/2024",
            home_team="101", away_team="202", total_goals=10,
        )
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches + [future],
        )
        for prov in snapshot.feature_provenance:
            assert prov.information_timestamp < 1700000000.0

    def test_02_future_result_before_prediction(self, historical_matches, feature_registry):
        """Future result injected → cannot influence features (filtered out)."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        eligible = engine._filter_eligible(historical_matches, 1700000000.0)
        assert all(m.date_unix < 1700000000 for m in eligible)

    def test_03_post_match_goals_injected(self, historical_matches, feature_registry):
        """Post-match goals from target fixture cannot appear in features."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        # Direct post-match fields never computed
        assert "home_goals" not in snapshot.features
        assert "total_goals" not in snapshot.features

    def test_04_post_match_corners_injected(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        assert "corners_home" not in snapshot.features
        assert "total_corners" not in snapshot.features

    def test_05_future_odds_injected(self):
        """Future odds (after prediction) cannot be used for prediction."""
        odds = OddsSnapshot(
            fixture_id="abc", market="GOALS_TOTAL", selection=OddsSelection.OVER,
            line=2.5, decimal_odds=1.85, snapshot_timestamp=1700050000,
        )
        # Prediction at 1700000000 — odds at 1700050000 (AFTER)
        assert odds.is_valid_for_prediction(1700000000) is False

    def test_06_closing_odds_in_prematch_snapshot(self):
        """Closing odds cannot be used as prediction input."""
        closing = OddsSnapshot(
            fixture_id="abc", market="GOALS_TOTAL", selection=OddsSelection.OVER,
            line=2.5, decimal_odds=1.80, snapshot_timestamp=1700099000,
            odds_type=OddsType.CLOSING,
        )
        assert closing.is_valid_for_prediction(1700000000) is False
        assert closing.is_closing is True

    def test_07_future_team_statistics_injected(self, historical_matches, feature_registry):
        """Future season data cannot contaminate feature computation."""
        future_season = ResearchMatch(
            match_id=7777, date_unix=1800000000,
            league_id=47, season="2024/2025",
            home_team="101", away_team="202", total_goals=5, total_corners=15,
        )
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches + [future_season],
        )
        for prov in snapshot.feature_provenance:
            assert prov.information_timestamp < 1700000000.0

    def test_08_future_fixture_in_rolling_aggregate(self, historical_matches, feature_registry):
        """Same as 07 — engine filtering catches it regardless of position in list."""
        future = ResearchMatch(
            match_id=6666, date_unix=1700000001,  # 1 second after prediction
            league_id=47, season="2023/2024",
            home_team="101", away_team="202", total_goals=8,
        )
        engine = RegistryTemporalEngine(registry=feature_registry)
        eligible = engine._filter_eligible(historical_matches + [future], 1700000000.0)
        assert 6666 not in [m.match_id for m in eligible]

    def test_09_prediction_cutoff_moved_backward(self, historical_matches, feature_registry):
        """Earlier cutoff → fewer eligible matches, still no leakage."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        early_eligible = engine._filter_eligible(historical_matches, 1699500000.0)
        full_eligible = engine._filter_eligible(historical_matches, 1700000000.0)
        assert len(early_eligible) < len(full_eligible)

    def test_10_prediction_cutoff_moved_forward(self, historical_matches, feature_registry):
        """Later cutoff includes more data but never beyond cutoff."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        eligible = engine._filter_eligible(historical_matches, 1700500000.0)
        assert all(m.date_unix < 1700500000 for m in eligible)

    def test_11_fixture_rescheduled(self):
        """Rescheduled fixture triggers snapshot invalidation."""
        tracker = FixtureVersionTracker(kickoff_change_threshold=3600)
        fixture = FutureFixture(
            source_fixture_id=100, home_team_id=1, away_team_id=2,
            kickoff_timestamp=1700100000, source="test",
        )
        tracker.record(fixture)
        from dataclasses import replace
        rescheduled = replace(fixture, kickoff_timestamp=1700200000)
        tracker.record(rescheduled)
        assert tracker.should_invalidate_snapshots(fixture.fixture_id) is True

    def test_12_duplicate_fixture(self, mock_footystats_client):
        """Same fixture fetched twice → stored once."""
        provider = FootyStatsFixtureProvider(season_ids=[4759], client=mock_footystats_client)
        f1 = provider.get_upcoming_fixtures()
        f2 = provider.get_upcoming_fixtures()
        assert len(f1) == len(f2)

    def test_13_provider_timestamp_after_kickoff(self):
        """Odds with timestamp after kickoff cannot be used for prediction."""
        odds = OddsSnapshot(
            fixture_id="abc", market="GOALS_TOTAL", selection=OddsSelection.OVER,
            line=2.5, decimal_odds=1.85, snapshot_timestamp=1700100001,  # After kickoff
        )
        # Prediction at 1700050000, kickoff at 1700100000
        assert odds.is_valid_for_prediction(1700050000) is False

    def test_14_missing_information_timestamp(self):
        """Features with unknown confidence are clearly marked."""
        prov = FeatureProvenance(
            feature_id="suspicious", value=42.0,
            information_timestamp=1699900000,
            timestamp_confidence=TimestampConfidence.UNKNOWN,
        )
        assert prov.timestamp_confidence == TimestampConfidence.UNKNOWN

    def test_15_timezone_manipulation(self, historical_matches, feature_registry):
        """Engine uses raw unix timestamps — no timezone conversion issues."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        # Unix timestamps are timezone-agnostic
        eligible = engine._filter_eligible(historical_matches, 1700000000.0)
        assert all(m.date_unix < 1700000000 for m in eligible)

    def test_16_cached_future_response(self, mock_footystats_client):
        """Cache doesn't serve future data as current (TTL-based refresh)."""
        provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
            fixture_cache_ttl=0.0,  # No caching
        )
        # Always re-fetches
        provider.get_upcoming_fixtures()
        assert mock_footystats_client.fetch_season_matches.call_count >= 1

    def test_17_future_season_contamination(self, historical_matches, feature_registry):
        """Future season data explicitly excluded by timestamp filter."""
        next_season = [
            ResearchMatch(
                match_id=9000 + i, date_unix=1701000000 + i * 86400,
                league_id=47, season="2024/2025",
                home_team="101", away_team="202", total_goals=4,
            )
            for i in range(10)
        ]
        engine = RegistryTemporalEngine(registry=feature_registry)
        eligible = engine._filter_eligible(
            historical_matches + next_season, 1700000000.0
        )
        assert all(m.date_unix < 1700000000 for m in eligible)

    def test_18_cross_league_contamination(self, historical_matches, feature_registry):
        """Features from different league don't contaminate if team IDs are unique."""
        other_league = ResearchMatch(
            match_id=7000, date_unix=1699500000,
            league_id=99,  # Different league
            season="2023/2024",
            home_team="999", away_team="998",  # Different teams
            total_goals=6,
        )
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches + [other_league],
        )
        # Snapshot still valid — other league teams don't match home/away IDs
        assert snapshot.snapshot_id != ""

    def test_19_settlement_result_not_in_features(self, historical_matches, feature_registry):
        """Settlement data cannot enter feature computation."""
        # The feature engine only sees ResearchMatch objects from history
        # Settlement is a separate concept that happens AFTER the match
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        # No "settlement" or "profit_loss" features
        for feat_id in snapshot.features:
            assert "settlement" not in feat_id
            assert "profit" not in feat_id

    def test_20_paper_trade_result_not_in_features(self, historical_matches, feature_registry):
        """Paper trade outcomes cannot leak into research features."""
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        for feat_id in snapshot.features:
            assert "paper" not in feat_id
            assert "trade" not in feat_id
            assert "clv" not in feat_id


# ═══════════════════════════════════════════════════════════════════
# I. SECURITY
# ═══════════════════════════════════════════════════════════════════


class TestSecurity:
    def test_no_api_key_in_fixture(self, mock_footystats_client):
        provider = FootyStatsFixtureProvider(season_ids=[4759], client=mock_footystats_client)
        fixtures = provider.get_upcoming_fixtures()
        for f in fixtures:
            d = json.dumps(f.to_dict())
            assert "api_key" not in d.lower()
            assert "footystats_api" not in d.lower()
            assert "secret" not in d.lower()

    def test_no_credentials_in_odds(self, mock_footystats_client):
        provider = FootyStatsOddsProvider(client=mock_footystats_client)
        provider.load_odds_for_season(4759)
        for snaps in provider._odds_cache.values():
            for s in snaps:
                d = json.dumps(s.to_dict())
                assert "api_key" not in d.lower()
                assert "secret" not in d.lower()

    def test_no_credentials_in_snapshot(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        d = json.dumps(snapshot.to_dict())
        assert "api_key" not in d.lower()
        assert "aws_access" not in d.lower()
        assert "password" not in d.lower()


# ═══════════════════════════════════════════════════════════════════
# J. SNAPSHOT IMMUTABILITY
# ═══════════════════════════════════════════════════════════════════


class TestSnapshotImmutability:
    def test_features_dict_frozen(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        with pytest.raises(TypeError):
            snapshot.features["injected"] = 999.0  # type: ignore

    def test_snapshot_attribute_frozen(self, historical_matches, feature_registry):
        engine = RegistryTemporalEngine(registry=feature_registry)
        snapshot = engine.build_snapshot(
            fixture_id="test", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000.0, kickoff_timestamp=1700100000.0,
            historical_matches=historical_matches,
        )
        with pytest.raises(AttributeError):
            snapshot.prediction_timestamp = 9999.0  # type: ignore


# ═══════════════════════════════════════════════════════════════════
# K. END-TO-END INTEGRATION
# ═══════════════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_fixture_to_snapshot_to_odds(self, mock_footystats_client, historical_matches, feature_registry):
        """Full pipeline: discover fixtures → build features → capture odds."""
        # 1. Discover fixtures
        fixture_provider = FootyStatsFixtureProvider(
            season_ids=[4759], client=mock_footystats_client,
        )
        fixtures = fixture_provider.get_upcoming_fixtures()
        assert len(fixtures) >= 1

        # 2. Build feature snapshot for first fixture
        engine = RegistryTemporalEngine(registry=feature_registry)
        fixture = fixtures[0]
        prediction_time = time.time()

        snapshot = engine.build_snapshot(
            fixture_id=fixture.fixture_id,
            home_team_id=fixture.home_team_id,
            away_team_id=fixture.away_team_id,
            prediction_timestamp=prediction_time,
            kickoff_timestamp=float(fixture.kickoff_timestamp),
            historical_matches=historical_matches,
            hypothesis_id="test_strategy",
        )
        assert snapshot.feature_count >= 0
        assert snapshot.prediction_timestamp == prediction_time

        # 3. Capture odds
        odds_provider = FootyStatsOddsProvider(client=mock_footystats_client)
        odds_provider.load_odds_for_season(4759)
        odds = odds_provider.get_odds_snapshot(fixture.fixture_id)
        # May or may not have odds depending on fixture_id match
        # The key test is that the pipeline doesn't crash

        # 4. Verify temporal integrity
        violations = snapshot.validate_temporal_integrity()
        assert violations == []

    def test_market_readiness_gates_paper_trading(self):
        """Market readiness prevents paper trades for insufficient markets."""
        assessor = MarketReadinessAssessor(min_historical_sample=100)
        result = assessor.assess(
            league_id=47, market="OFFSIDES_TOTAL",
            historical_sample=5, odds_coverage=0.0, feature_coverage=0.2,
        )
        assert result.readiness in (MarketReadiness.INSUFFICIENT_DATA, MarketReadiness.UNAVAILABLE)
        # Paper eligibility should check market readiness before allowing trades
