"""Closing Odds Provider — abstraction for genuine closing line data.

Independent from FootyStatsOddsProvider. A closing price is only genuine
if the provider supplies sufficient information to establish it represents
the market close.

Supported sources (via adapter pattern):
- Pinnacle closing lines (if available)
- Betfair exchange closing (if available)
- DeterministicClosingOddsProvider (testing)

No fabrication. No scraping. No credential leakage.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ClosingOddsStatus(Enum):
    """Status of a closing odds observation."""
    VALID = "VALID"          # Genuine closing odds with verified timestamp
    ESTIMATED = "ESTIMATED"  # Timestamp estimated, not exact
    UNKNOWN = "UNKNOWN"      # Insufficient timestamp information
    UNAVAILABLE = "UNAVAILABLE"  # Provider cannot supply this data
    INVALID = "INVALID"      # Failed validation


class TimestampSemantics(Enum):
    """What the timestamp represents."""
    EXACT_CLOSE = "EXACT_CLOSE"      # Provider marks this as exact closing time
    LAST_BEFORE_KICKOFF = "LAST_BEFORE_KICKOFF"  # Last snapshot before kickoff
    PROVIDER_ESTIMATED = "PROVIDER_ESTIMATED"    # Provider's estimate
    RETRIEVAL_TIME = "RETRIEVAL_TIME"            # When we fetched it (weakest)


@dataclass(frozen=True)
class ClosingOddsObservation:
    """Immutable closing odds observation with provenance.

    This is EVALUATION-ONLY data. It must NEVER influence:
    - predictions, features, staking, eligibility, or entry odds.
    """
    fixture_id: str
    market: str
    selection: str  # OVER, UNDER, HOME, DRAW, AWAY, YES, NO
    line: float = 0.0
    decimal_odds: float = 0.0
    bookmaker: str = ""
    source: str = ""
    closing_timestamp: float = 0.0
    timestamp_semantics: TimestampSemantics = TimestampSemantics.PROVIDER_ESTIMATED
    kickoff_timestamp: float = 0.0
    retrieved_at: float = field(default_factory=time.time)
    status: ClosingOddsStatus = ClosingOddsStatus.VALID
    provider_event_id: str = ""  # Provider's own event identifier
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def observation_id(self) -> str:
        """Deterministic identity for this observation."""
        canonical = json.dumps({
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "decimal_odds": self.decimal_odds,
            "bookmaker": self.bookmaker,
            "source": self.source,
            "closing_timestamp": self.closing_timestamp,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def implied_probability(self) -> float:
        if self.decimal_odds <= 0:
            return 0.0
        return 1.0 / self.decimal_odds

    @property
    def is_genuine(self) -> bool:
        """Whether this is considered genuine closing data."""
        return (
            self.status == ClosingOddsStatus.VALID
            and self.timestamp_semantics in (
                TimestampSemantics.EXACT_CLOSE,
                TimestampSemantics.LAST_BEFORE_KICKOFF,
            )
            and self.decimal_odds >= 1.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "decimal_odds": self.decimal_odds,
            "implied_probability": round(self.implied_probability, 6),
            "bookmaker": self.bookmaker,
            "source": self.source,
            "closing_timestamp": self.closing_timestamp,
            "timestamp_semantics": self.timestamp_semantics.value,
            "kickoff_timestamp": self.kickoff_timestamp,
            "status": self.status.value,
            "is_genuine": self.is_genuine,
        }


class ClosingOddsProvider(ABC):
    """Abstract provider for genuine closing odds.

    Independent from pre-match odds providers.
    Multiple implementations possible (Pinnacle, Betfair, etc).
    """

    @abstractmethod
    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        selection: Optional[str] = None,
    ) -> list[ClosingOddsObservation]:
        """Get closing odds for a fixture.

        Returns only observations the provider can supply.
        Never fabricates data.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider is configured and reachable."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def supports_genuine_closing(self) -> bool:
        """Whether this provider can supply genuine (EXACT_CLOSE) data."""
        ...


class DeterministicClosingOddsProvider(ClosingOddsProvider):
    """Test provider returning pre-configured closing odds.

    CLEARLY labeled as test-only. Never pretends to be real data.
    """

    def __init__(self) -> None:
        self._observations: dict[str, list[ClosingOddsObservation]] = {}

    @property
    def provider_name(self) -> str:
        return "deterministic_test"

    @property
    def supports_genuine_closing(self) -> bool:
        return True  # Test provider can simulate genuine data

    def is_available(self) -> bool:
        return True

    def add_observation(self, obs: ClosingOddsObservation) -> None:
        if obs.fixture_id not in self._observations:
            self._observations[obs.fixture_id] = []
        self._observations[obs.fixture_id].append(obs)

    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        selection: Optional[str] = None,
    ) -> list[ClosingOddsObservation]:
        results = self._observations.get(fixture_id, [])
        if market:
            results = [o for o in results if o.market == market]
        if selection:
            results = [o for o in results if o.selection == selection]
        return results
