"""Batch 10/11 — Forward Research & Future Fixtures.

Provides the infrastructure for prospective research:
- Future fixture discovery and tracking (real + deterministic providers)
- Pre-match feature snapshots (immutable, temporal-causal)
- Odds snapshots (immutable, timestamped)
- Temporal feature engine (strict information-time enforcement)
- Full FeatureRegistry integration for point-in-time features
- Multi-league support and market readiness
- Fixture versioning for rescheduled/postponed
- Forward research orchestration

Temporal Causality Rule:
    ALL information used to generate a prediction must satisfy:
    information_timestamp < prediction_timestamp <= kickoff_timestamp

This is NOT live betting. This is NOT production trading.
Paper trading is research evaluation only.
"""

from src.research.forward.future_fixture import (
    FutureFixture,
    FixtureStatus,
)
from src.research.forward.snapshot import PreMatchSnapshot
from src.research.forward.odds import OddsSnapshot, OddsSelection, OddsType
from src.research.forward.temporal_features import TemporalFeatureEngine
from src.research.forward.providers import (
    FutureFixtureProvider,
    OddsProvider,
    DeterministicFixtureProvider,
    DeterministicOddsProvider,
)
from src.research.forward.footystats_fixture_provider import FootyStatsFixtureProvider
from src.research.forward.footystats_odds_provider import FootyStatsOddsProvider
from src.research.forward.registry_features import RegistryTemporalEngine, create_standard_forward_features
from src.research.forward.league_coverage import (
    LeagueCoverageReport,
    MarketReadiness,
    MarketReadinessAssessor,
    MarketReadinessResult,
)
from src.research.forward.fixture_versioning import FixtureVersionTracker, FixtureVersion

__all__ = [
    # Core models
    "FutureFixture",
    "FixtureStatus",
    "PreMatchSnapshot",
    "OddsSnapshot",
    "OddsSelection",
    "OddsType",
    # Feature engines
    "TemporalFeatureEngine",
    "RegistryTemporalEngine",
    "create_standard_forward_features",
    # Provider interfaces
    "FutureFixtureProvider",
    "OddsProvider",
    # Deterministic providers (testing)
    "DeterministicFixtureProvider",
    "DeterministicOddsProvider",
    # Real providers (FootyStats)
    "FootyStatsFixtureProvider",
    "FootyStatsOddsProvider",
    # Multi-league & readiness
    "LeagueCoverageReport",
    "MarketReadiness",
    "MarketReadinessAssessor",
    "MarketReadinessResult",
    # Fixture versioning
    "FixtureVersionTracker",
    "FixtureVersion",
]
