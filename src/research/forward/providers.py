"""Forward Research Providers — abstractions for fixture and odds data.

Two provider categories:
1. FutureFixtureProvider — discovers upcoming matches
2. OddsProvider — captures odds snapshots

Each has:
- Abstract interface (for real implementations)
- Deterministic test provider (for testing without network)

Real providers are CLEARLY distinguished from test providers.
Test providers NEVER pretend to be real data sources.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from src.research.forward.future_fixture import FixtureStatus, FutureFixture
from src.research.forward.odds import OddsSelection, OddsSnapshot, OddsType


# ═══════════════════════════════════════════════════════════════════
# FIXTURE PROVIDER
# ═══════════════════════════════════════════════════════════════════


class FutureFixtureProvider(ABC):
    """Abstract interface for future fixture discovery.

    Implementations:
    - FootyStatsFixtureProvider (real, requires API key)
    - DeterministicFixtureProvider (test, no network)
    """

    @abstractmethod
    def get_upcoming_fixtures(
        self,
        competition_id: Optional[int] = None,
        from_timestamp: Optional[float] = None,
        to_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> list[FutureFixture]:
        """Get upcoming fixtures matching criteria.

        Args:
            competition_id: Filter by competition.
            from_timestamp: Earliest kickoff time.
            to_timestamp: Latest kickoff time.
            limit: Maximum fixtures to return.

        Returns:
            List of FutureFixture sorted by kickoff_timestamp ascending.
        """
        ...

    @abstractmethod
    def get_fixture(self, fixture_id: str) -> Optional[FutureFixture]:
        """Get a specific fixture by ID."""
        ...

    @abstractmethod
    def get_fixture_status(self, fixture_id: str) -> Optional[FixtureStatus]:
        """Get current status of a fixture."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        ...


class DeterministicFixtureProvider(FutureFixtureProvider):
    """Deterministic fixture provider for testing.

    Returns pre-configured fixtures without network access.
    CLEARLY labeled as a test provider — never pretends to be real data.

    Usage:
        fixtures = [FutureFixture(...), ...]
        provider = DeterministicFixtureProvider(fixtures=fixtures)
    """

    def __init__(self, fixtures: Optional[list[FutureFixture]] = None) -> None:
        self._fixtures: dict[str, FutureFixture] = {}
        if fixtures:
            for f in fixtures:
                self._fixtures[f.fixture_id] = f

    @property
    def provider_name(self) -> str:
        return "deterministic_test"

    def add_fixture(self, fixture: FutureFixture) -> None:
        """Add a fixture to the test provider."""
        self._fixtures[fixture.fixture_id] = fixture

    def update_status(self, fixture_id: str, status: FixtureStatus) -> None:
        """Update fixture status (for testing state transitions)."""
        if fixture_id in self._fixtures:
            self._fixtures[fixture_id] = self._fixtures[fixture_id].transition(status)

    def get_upcoming_fixtures(
        self,
        competition_id: Optional[int] = None,
        from_timestamp: Optional[float] = None,
        to_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> list[FutureFixture]:
        fixtures = list(self._fixtures.values())

        if competition_id is not None:
            fixtures = [f for f in fixtures if f.competition_id == competition_id]
        if from_timestamp is not None:
            fixtures = [f for f in fixtures if f.kickoff_timestamp >= from_timestamp]
        if to_timestamp is not None:
            fixtures = [f for f in fixtures if f.kickoff_timestamp <= to_timestamp]

        # Sort by kickoff ascending
        fixtures.sort(key=lambda f: f.kickoff_timestamp)
        return fixtures[:limit]

    def get_fixture(self, fixture_id: str) -> Optional[FutureFixture]:
        return self._fixtures.get(fixture_id)

    def get_fixture_status(self, fixture_id: str) -> Optional[FixtureStatus]:
        fixture = self._fixtures.get(fixture_id)
        return fixture.status if fixture else None


# ═══════════════════════════════════════════════════════════════════
# ODDS PROVIDER
# ═══════════════════════════════════════════════════════════════════


class OddsProvider(ABC):
    """Abstract interface for odds data.

    Supports:
    - Multiple bookmakers
    - Multiple market types
    - Temporal snapshots (never overwritten)
    - Closing odds (separate from pre-match)

    Implementations:
    - Real odds provider (requires API key, not yet implemented)
    - DeterministicOddsProvider (test, no network)
    """

    @abstractmethod
    def get_odds_snapshot(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        bookmaker: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Get latest odds snapshots for a fixture.

        Args:
            fixture_id: Target fixture.
            market: Filter by market type.
            bookmaker: Filter by bookmaker.

        Returns:
            List of OddsSnapshot records.
        """
        ...

    @abstractmethod
    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Get closing odds for a completed fixture.

        Closing odds are captured AT or NEAR kickoff.
        They must NEVER be used for predictions — only for CLV analysis.

        Returns:
            List of OddsSnapshot with odds_type=CLOSING.
        """
        ...

    @abstractmethod
    def get_odds_history(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Get all historical odds snapshots for a fixture.

        Returns all captured snapshots in chronological order.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        ...


class DeterministicOddsProvider(OddsProvider):
    """Deterministic odds provider for testing.

    Returns pre-configured odds without network access.
    CLEARLY labeled as test provider.

    Usage:
        provider = DeterministicOddsProvider()
        provider.add_snapshot(OddsSnapshot(...))
    """

    def __init__(self) -> None:
        self._snapshots: list[OddsSnapshot] = []

    @property
    def provider_name(self) -> str:
        return "deterministic_test"

    def add_snapshot(self, snapshot: OddsSnapshot) -> None:
        """Add an odds snapshot to the test provider."""
        self._snapshots.append(snapshot)

    def add_snapshots(self, snapshots: list[OddsSnapshot]) -> None:
        """Add multiple odds snapshots."""
        self._snapshots.extend(snapshots)

    def get_odds_snapshot(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        bookmaker: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        results = [s for s in self._snapshots if s.fixture_id == fixture_id]
        if market:
            results = [s for s in results if s.market == market]
        if bookmaker:
            results = [s for s in results if s.bookmaker == bookmaker]
        # Return only pre-match odds, most recent first
        pre_match = [s for s in results if s.odds_type == OddsType.PRE_MATCH]
        pre_match.sort(key=lambda s: s.snapshot_timestamp, reverse=True)
        return pre_match

    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        results = [
            s for s in self._snapshots
            if s.fixture_id == fixture_id and s.odds_type == OddsType.CLOSING
        ]
        if market:
            results = [s for s in results if s.market == market]
        return results

    def get_odds_history(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        results = [s for s in self._snapshots if s.fixture_id == fixture_id]
        if market:
            results = [s for s in results if s.market == market]
        results.sort(key=lambda s: s.snapshot_timestamp)
        return results
