"""FootyStats Future Fixture Provider — real upcoming fixture discovery.

Reuses the existing FootyStatsResearchClient. Does NOT create a second HTTP client.
Does NOT expose API keys in objects, logs, hashes, or persistence.

The FootyStats /league-matches endpoint returns ALL matches for a season,
including upcoming (non-complete) ones. This provider filters to only
scheduled/upcoming fixtures and normalizes them into FutureFixture objects.

Temporal Rule:
    Only fixtures with kickoff_timestamp > current time are returned as "upcoming".
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from src.research.footystats.client import FootyStatsResearchClient
from src.research.forward.future_fixture import FixtureStatus, FutureFixture
from src.research.forward.providers import FutureFixtureProvider

logger = logging.getLogger(__name__)

# FootyStats match status mapping
_STATUS_MAP = {
    "incomplete": FixtureStatus.SCHEDULED,
    "suspended": FixtureStatus.POSTPONED,
    "cancelled": FixtureStatus.CANCELLED,
    "complete": FixtureStatus.COMPLETED,
    "inprogress": FixtureStatus.STARTED,
    "in progress": FixtureStatus.STARTED,
}


class FootyStatsFixtureProvider(FutureFixtureProvider):
    """Real fixture provider using FootyStats API.

    Fetches season matches and filters to upcoming/scheduled fixtures.
    Normalizes into FutureFixture model with stable team/league IDs.

    Usage:
        provider = FootyStatsFixtureProvider(season_ids=[4759, 4760])
        fixtures = provider.get_upcoming_fixtures()
    """

    def __init__(
        self,
        season_ids: list[int],
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        client: Optional[FootyStatsResearchClient] = None,
        fixture_cache_ttl: float = 300.0,  # 5 min cache for fixtures
    ) -> None:
        """Initialize with season IDs to monitor.

        Args:
            season_ids: FootyStats season/competition IDs to check for upcoming.
            api_key: API key (from env if None).
            cache_dir: Cache directory for responses.
            client: Pre-configured client (for testing/DI).
            fixture_cache_ttl: How long to cache fixture data (seconds).
        """
        self._season_ids = season_ids
        self._client = client or FootyStatsResearchClient(
            api_key=api_key, cache_dir=cache_dir,
        )
        self._fixture_cache_ttl = fixture_cache_ttl
        self._fixtures: dict[str, FutureFixture] = {}
        self._last_refresh: float = 0.0

    @property
    def provider_name(self) -> str:
        return "footystats"

    def get_upcoming_fixtures(
        self,
        competition_id: Optional[int] = None,
        from_timestamp: Optional[float] = None,
        to_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> list[FutureFixture]:
        """Get upcoming fixtures from FootyStats.

        Fetches matches for configured seasons and filters to those
        that are scheduled/incomplete with kickoff in the future.
        """
        self._refresh_if_stale()

        fixtures = list(self._fixtures.values())

        # Apply filters
        now = time.time()
        # Only truly upcoming (kickoff in future)
        fixtures = [f for f in fixtures if f.kickoff_timestamp > now]

        if competition_id is not None:
            fixtures = [f for f in fixtures if f.competition_id == competition_id]
        if from_timestamp is not None:
            fixtures = [f for f in fixtures if f.kickoff_timestamp >= from_timestamp]
        if to_timestamp is not None:
            fixtures = [f for f in fixtures if f.kickoff_timestamp <= to_timestamp]

        # Sort chronologically
        fixtures.sort(key=lambda f: f.kickoff_timestamp)
        return fixtures[:limit]

    def get_fixture(self, fixture_id: str) -> Optional[FutureFixture]:
        """Get a specific fixture by its deterministic ID."""
        self._refresh_if_stale()
        return self._fixtures.get(fixture_id)

    def get_fixture_status(self, fixture_id: str) -> Optional[FixtureStatus]:
        """Get current status of a fixture."""
        fixture = self.get_fixture(fixture_id)
        return fixture.status if fixture else None

    def _refresh_if_stale(self) -> None:
        """Refresh fixture data if cache TTL expired."""
        elapsed = time.time() - self._last_refresh
        if elapsed < self._fixture_cache_ttl and self._fixtures:
            return
        self._refresh_fixtures()

    def _refresh_fixtures(self) -> None:
        """Fetch all matches from configured seasons and update fixture cache."""
        now = time.time()

        for season_id in self._season_ids:
            try:
                raw_matches = self._client.fetch_season_matches(season_id)
                for raw in raw_matches:
                    fixture = self._normalize_fixture(raw, season_id)
                    if fixture is not None:
                        self._fixtures[fixture.fixture_id] = fixture
            except Exception as e:
                # Never log credentials in error
                logger.warning(
                    "Failed to fetch season %d: %s", season_id, type(e).__name__
                )

        self._last_refresh = now
        logger.info(
            "Refreshed fixtures: %d total across %d seasons",
            len(self._fixtures), len(self._season_ids),
        )

    def _normalize_fixture(
        self, raw: dict[str, Any], season_id: int
    ) -> Optional[FutureFixture]:
        """Normalize a raw FootyStats match record into a FutureFixture.

        Unlike the historical normalizer, this handles non-complete matches.
        Returns None if the record is malformed or unusable.
        """
        # Required fields
        match_id = raw.get("id")
        if not match_id:
            return None

        date_unix = raw.get("date_unix")
        if not date_unix or not isinstance(date_unix, (int, float)):
            return None

        # Status mapping
        raw_status = str(raw.get("status", "incomplete")).lower().strip()
        status = _STATUS_MAP.get(raw_status, FixtureStatus.SCHEDULED)

        # Team IDs — prefer numeric IDs over names for stable identity
        home_id = raw.get("homeID") or raw.get("home_id") or 0
        away_id = raw.get("awayID") or raw.get("away_id") or 0
        if not home_id or not away_id:
            return None

        # Team names (metadata only, not identity)
        home_name = raw.get("home_name", "") or raw.get("homeTeam", "") or ""
        away_name = raw.get("away_name", "") or raw.get("awayTeam", "") or ""

        # Competition/league
        competition_id = raw.get("competition_id") or raw.get("league_id") or season_id

        return FutureFixture(
            source_fixture_id=int(match_id),
            home_team_id=int(home_id),
            away_team_id=int(away_id),
            home_team_name=str(home_name),
            away_team_name=str(away_name),
            competition_id=int(competition_id),
            season_id=season_id,
            kickoff_timestamp=int(date_unix),
            source="footystats",
            retrieved_at=time.time(),
            status=status,
        )
