"""Quota-conscious live coverage reconnaissance for VERIFIED competitions.

Given the identity crosswalk, this module performs a SMALL, bounded live probe
per VERIFIED competition to measure real coverage:

- current season id (via ``is_current`` on the seasons list),
- scheduled fixtures in a discovery horizon (competition-scoped query),
- odds endpoint availability + bookmakers + markets present on a sample fixture,
- lineup / injuries / referee endpoint support vs current availability.

It distinguishes ENDPOINT SUPPORTED from DATA CURRENTLY AVAILABLE: e.g. a lineup
being unavailable 4 days before kickoff is recorded as "not-yet-available",
never as "league lacks lineup support". Unknown stays UNKNOWN (never False).

A hard reconnaissance request budget is enforced; on reaching it the recon
STOPS and reports partial results rather than silently continuing.

No large historical downloads. No secrets logged. Read-only.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.research.prospective.api_contract import Endpoint
from src.research.prospective.capture import ProspectiveApiClient, payload_hash
from src.research.prospective.crosswalk import CrosswalkEntry, IdentityStatus
from src.research.prospective.odds_capture import OVER_UNDER_MARKET_KEYS
from src.research.prospective.quota import parse_rate_limit

#: Hard reconnaissance budget for the whole mapping/coverage phase.
DEFAULT_RECON_BUDGET = 1000

#: Champion-supported over/under markets we care about (subset of contract).
_CHAMPION_MARKETS = ("total_goals", "match_corners", "total_cards", "match_shots_on_target")


@dataclass
class CompetitionCoverage:
    """Live coverage evidence for one competition (UNKNOWN where unprobed)."""

    canonical_name: str
    country: Optional[str]
    thestatsapi_competition_id: Optional[str]
    thestatsapi_season_id: Optional[str] = None
    season_is_current: Optional[bool] = None
    scheduled_fixtures_in_scan: Optional[int] = None
    nearest_kickoff_iso: Optional[str] = None
    odds_endpoint_verified: Optional[bool] = None
    odds_fixture_probed: Optional[bool] = None
    bookmakers_present: tuple[str, ...] = ()
    markets_present: tuple[str, ...] = ()
    pinnacle_available: Optional[bool] = None
    bet365_available: Optional[bool] = None
    lineup_endpoint_verified: Optional[bool] = None
    lineup_current_availability: Optional[bool] = None
    injuries_endpoint_verified: Optional[bool] = None
    referee_available: Optional[bool] = None
    requests_used: int = 0
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "country": self.country,
            "thestatsapi_competition_id": self.thestatsapi_competition_id,
            "thestatsapi_season_id": self.thestatsapi_season_id,
            "season_is_current": self.season_is_current,
            "scheduled_fixtures_in_scan": self.scheduled_fixtures_in_scan,
            "nearest_kickoff": self.nearest_kickoff_iso,
            "odds_endpoint_verified": self.odds_endpoint_verified,
            "odds_fixture_probed": self.odds_fixture_probed,
            "bookmakers_present": list(self.bookmakers_present),
            "markets_present": list(self.markets_present),
            "pinnacle_available": self.pinnacle_available,
            "bet365_available": self.bet365_available,
            "lineup_endpoint_verified": self.lineup_endpoint_verified,
            "lineup_current_availability": self.lineup_current_availability,
            "injuries_endpoint_verified": self.injuries_endpoint_verified,
            "referee_available": self.referee_available,
            "requests_used": self.requests_used,
            "errors": list(self.errors),
        }


@dataclass
class ReconResult:
    coverage: list[CompetitionCoverage]
    total_requests: int
    budget: int
    stopped_early: bool
    monthly_quota_remaining: Optional[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "budget": self.budget,
            "stopped_early": self.stopped_early,
            "monthly_quota_remaining": self.monthly_quota_remaining,
            "competitions": [c.to_dict() for c in self.coverage],
        }


def _iso_date(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).date().isoformat()


class Reconnaissance:
    """Runs bounded live recon. Client injectable; also captures quota headers.

    ``client_get_with_headers`` (optional) returns (json, headers) so quota can
    be tracked; if absent we use the plain client and cannot read headers.
    """

    def __init__(
        self,
        client: ProspectiveApiClient,
        *,
        budget: int = DEFAULT_RECON_BUDGET,
        clock: Callable[[], float] = None,  # type: ignore[assignment]
        horizon_hours: int = 21 * 24,
    ) -> None:
        import time

        self.client = client
        self.budget = budget
        self.clock = clock or time.time
        self.horizon_hours = horizon_hours
        self._used = 0
        self._monthly_remaining: Optional[int] = None

    def _get(self, endpoint: Endpoint, *, params: Optional[dict] = None, **path: str):
        """One budgeted request. Returns None when budget is exhausted."""
        if self._used >= self.budget:
            return None
        self._used += 1
        result = self.client.get(endpoint, params=params, **path)
        rl = getattr(self.client, "last_rate_limit", None)
        if rl is not None and rl.monthly_remaining is not None:
            self._monthly_remaining = rl.monthly_remaining
        return result

    def recon_competition(self, entry: CrosswalkEntry) -> CompetitionCoverage:
        cov = CompetitionCoverage(
            canonical_name=entry.canonical_name, country=entry.country,
            thestatsapi_competition_id=entry.thestatsapi_competition_id,
        )
        cid = entry.thestatsapi_competition_id
        if cid is None:
            cov.errors = ("no_competition_id",)
            return cov
        start = self._used

        # 1) current season
        try:
            seasons = self._get(Endpoint.COMPETITION_SEASONS, competition_id=cid)
        except Exception as exc:  # noqa: BLE001
            cov.errors = (f"seasons_error:{type(exc).__name__}",)
            cov.requests_used = self._used - start
            return cov
        if seasons is None:
            cov.requests_used = self._used - start
            return cov
        data = seasons.get("data", []) if isinstance(seasons, dict) else []
        cur = next((s for s in data if s.get("is_current")), None)
        if cur:
            cov.thestatsapi_season_id = cur.get("id")
            cov.season_is_current = True

        # 2) scheduled fixtures scan (competition-scoped, horizon-bounded)
        now = self.clock()
        params = {
            "status": "scheduled", "competition_id": cid,
            "date_from": _iso_date(now),
            "date_to": _iso_date(now + self.horizon_hours * 3600),
            "per_page": 50,
        }
        try:
            matches = self._get(Endpoint.MATCHES, params=params)
        except Exception as exc:  # noqa: BLE001
            cov.errors = cov.errors + (f"matches_error:{type(exc).__name__}",)
            cov.requests_used = self._used - start
            return cov
        fixtures = matches.get("data", []) if isinstance(matches, dict) else []
        cov.scheduled_fixtures_in_scan = len(fixtures)
        nearest = None
        for m in fixtures:
            ko = m.get("utc_date")
            if ko and (nearest is None or ko < nearest):
                nearest = ko
        cov.nearest_kickoff_iso = nearest

        # 3) odds probe on the nearest fixture (endpoint support + coverage)
        if fixtures:
            mid = next((m.get("id") for m in fixtures if m.get("id")), None)
            if mid:
                try:
                    odds = self._get(Endpoint.MATCH_ODDS, match_id=mid)
                    cov.odds_fixture_probed = True
                    if odds is None:
                        cov.odds_endpoint_verified = False  # 404 => no odds row yet
                    else:
                        cov.odds_endpoint_verified = True
                        d = odds.get("data", odds) if isinstance(odds, dict) else {}
                        books = []
                        markets: set = set()
                        for bm in (d.get("bookmakers", []) if isinstance(d, dict) else []):
                            if isinstance(bm, dict):
                                books.append(str(bm.get("bookmaker", "")).lower().replace(" ", "-"))
                                mk = bm.get("markets", {})
                                if isinstance(mk, dict):
                                    for k in _CHAMPION_MARKETS:
                                        if isinstance(mk.get(k), dict) and mk.get(k):
                                            markets.add(k)
                        cov.bookmakers_present = tuple(sorted(set(books)))
                        cov.markets_present = tuple(sorted(markets))
                        cov.pinnacle_available = "pinnacle" in cov.bookmakers_present
                        cov.bet365_available = "bet365" in cov.bookmakers_present
                except Exception as exc:  # noqa: BLE001
                    cov.errors = cov.errors + (f"odds_error:{type(exc).__name__}",)

        cov.requests_used = self._used - start
        return cov

    def run(self, entries: list[CrosswalkEntry]) -> ReconResult:
        """Recon only VERIFIED competitions, within the budget."""
        cov: list[CompetitionCoverage] = []
        stopped = False
        for e in entries:
            if e.identity_status != IdentityStatus.VERIFIED:
                continue
            if self._used >= self.budget:
                stopped = True
                break
            cov.append(self.recon_competition(e))
        return ReconResult(
            coverage=cov, total_requests=self._used, budget=self.budget,
            stopped_early=stopped, monthly_quota_remaining=self._monthly_remaining,
        )
