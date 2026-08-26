"""Batch 10 — Forward Research & Future Fixtures.

Provides the infrastructure for prospective research:
- Future fixture discovery and tracking
- Pre-match feature snapshots (immutable, temporal-causal)
- Odds snapshots (immutable, timestamped)
- Temporal feature engine (strict information-time enforcement)
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
from src.research.forward.odds import OddsSnapshot, OddsSelection
from src.research.forward.temporal_features import TemporalFeatureEngine
from src.research.forward.providers import (
    FutureFixtureProvider,
    OddsProvider,
    DeterministicFixtureProvider,
    DeterministicOddsProvider,
)

__all__ = [
    "FutureFixture",
    "FixtureStatus",
    "PreMatchSnapshot",
    "OddsSnapshot",
    "OddsSelection",
    "TemporalFeatureEngine",
    "FutureFixtureProvider",
    "OddsProvider",
    "DeterministicFixtureProvider",
    "DeterministicOddsProvider",
]
