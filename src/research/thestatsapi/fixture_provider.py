"""TheStatsAPI fixture provider — implements FutureFixtureProvider.

Maps TheStatsAPI fixture payloads to the canonical ``FutureFixture`` type.
Cache-backed by default (reads fixtures from a corpus loader); live mode uses
the client. Fixture identity is (source, source_fixture_id) — never team name.

Status mapping: TheStatsAPI uses "finished"/"scheduled"/etc.; we map to the
existing ``FixtureStatus`` enum. Unknown statuses default to SCHEDULED only
when kickoff is in the future, otherwise COMPLETED is NOT assumed — we mark
STARTED/COMPLETED only from explicit provider status to avoid fabricating a
lifecycle state.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.research.forward.future_fixture import FixtureStatus, FutureFixture
from src.research.forward.providers import FutureFixtureProvider
from src.research.thestatsapi import ids
from src.research.thestatsapi.corpus_loader import TheStatsAPICorpusLoader
from src.research.thestatsapi.normalizer import parse_iso_to_unix

logger = logging.getLogger(__name__)

_SOURCE = "thestatsapi"

_STATUS_MAP = {
    "scheduled": FixtureStatus.SCHEDULED,
    "not_started": FixtureStatus.SCHEDULED,
    "timed": FixtureStatus.SCHEDULED,
    "in_play": FixtureStatus.STARTED,
    "live": FixtureStatus.STARTED,
    "finished": FixtureStatus.COMPLETED,
    "complete": FixtureStatus.COMPLETED,
    "played": FixtureStatus.COMPLETED,
    "postponed": FixtureStatus.POSTPONED,
    "cancelled": FixtureStatus.CANCELLED,
    "canceled": FixtureStatus.CANCELLED,
}


def _to_future_fixture(fx: dict[str, Any]) -> Optional[FutureFixture]:
    match_ref = fx.get("id")
    if not isinstance(match_ref, str) or not match_ref:
        return None
    try:
        source_fixture_id = ids.parse_match_id(match_ref)
    except ids.ProviderIdError:
        return None

    home = fx.get("home_team") or {}
    away = fx.get("away_team") or {}
    try:
        home_id = ids.parse_team_id(str(home.get("id", "")))
    except ids.ProviderIdError:
        home_id = 0
    try:
        away_id = ids.parse_team_id(str(away.get("id", "")))
    except ids.ProviderIdError:
        away_id = 0

    comp_ref = str(fx.get("competition_id", ""))
    try:
        competition_id = ids.parse_competition_id(comp_ref) if comp_ref else 0
    except ids.ProviderIdError:
        competition_id = 0

    season_ref = str(fx.get("season_id", ""))
    try:
        season_id = ids.parse_season_id(season_ref) if season_ref else 0
    except ids.ProviderIdError:
        season_id = 0

    kickoff = parse_iso_to_unix(fx.get("utc_date")) or 0
    status = _STATUS_MAP.get(str(fx.get("status", "")).lower(), FixtureStatus.SCHEDULED)

    return FutureFixture(
        source_fixture_id=source_fixture_id,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name=str(home.get("name", "")),
        away_team_name=str(away.get("name", "")),
        competition_id=competition_id,
        season_id=season_id,
        kickoff_timestamp=kickoff,
        source=_SOURCE,
        retrieved_at=time.time(),
        status=status,
    )


class TheStatsAPIFixtureProvider(FutureFixtureProvider):
    """FutureFixtureProvider backed by TheStatsAPI fixtures.

    Usage (cache-backed):
        loader = TheStatsAPICorpusLoader("data/thestatsapi/championship")
        provider = TheStatsAPIFixtureProvider(
            loader=loader,
            fixtures_glob="_all_fixtures_*.json",
        )
    """

    def __init__(
        self,
        *,
        loader: Optional[TheStatsAPICorpusLoader] = None,
        fixtures_files: Optional[list[str]] = None,
        fixtures_glob: Optional[str] = None,
        fixtures: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._loader = loader
        self._fixtures_files = fixtures_files
        self._fixtures_glob = fixtures_glob
        self._preloaded = fixtures
        self._cache: Optional[dict[str, FutureFixture]] = None

    @property
    def provider_name(self) -> str:
        return _SOURCE

    def _ensure_loaded(self) -> dict[str, FutureFixture]:
        if self._cache is not None:
            return self._cache
        raw: list[dict[str, Any]] = []
        if self._preloaded is not None:
            raw = self._preloaded
        elif self._loader is not None:
            if self._fixtures_files:
                raw.extend(self._loader.load_fixtures(self._fixtures_files))
            if self._fixtures_glob:
                raw.extend(self._loader.load_fixtures_glob(self._fixtures_glob))
        else:
            raise ValueError("TheStatsAPIFixtureProvider requires fixtures or a loader")

        cache: dict[str, FutureFixture] = {}
        for fx in raw:
            ff = _to_future_fixture(fx) if isinstance(fx, dict) else None
            if ff is not None:
                cache[ff.fixture_id] = ff
        self._cache = cache
        return cache

    def get_upcoming_fixtures(
        self,
        competition_id: Optional[int] = None,
        from_timestamp: Optional[float] = None,
        to_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> list[FutureFixture]:
        fixtures = list(self._ensure_loaded().values())
        if competition_id is not None:
            fixtures = [f for f in fixtures if f.competition_id == competition_id]
        if from_timestamp is not None:
            fixtures = [f for f in fixtures if f.kickoff_timestamp >= from_timestamp]
        if to_timestamp is not None:
            fixtures = [f for f in fixtures if f.kickoff_timestamp <= to_timestamp]
        fixtures.sort(key=lambda f: f.kickoff_timestamp)
        return fixtures[:limit]

    def get_fixture(self, fixture_id: str) -> Optional[FutureFixture]:
        return self._ensure_loaded().get(fixture_id)

    def get_fixture_status(self, fixture_id: str) -> Optional[FixtureStatus]:
        fx = self._ensure_loaded().get(fixture_id)
        return fx.status if fx else None
