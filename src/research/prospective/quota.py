"""Rate-limit / quota economics for the prospective collector.

The live contract exposes two independent budgets on every authenticated
response (success or error):

- Per-minute burst: ``X-RateLimit-Limit`` / ``-Remaining`` / ``-Reset``.
- Monthly billing-cycle quota: ``X-Monthly-Quota-Limit`` / ``-Remaining`` /
  ``-Reset`` (both ``-1`` on uncapped plans).

``Remaining`` already accounts for the request being served, so ``0`` means the
NEXT request is the one that gets rejected. A ``429`` carries ``Retry-After``
and a code (``RATE_LIMITED`` for the minute window, ``USAGE_LIMIT_EXCEEDED`` for
the monthly quota).

This module parses those headers (never anything sensitive) and provides a
conservative budget guard plus a request-budget estimator for a proposed
capture schedule, so we can decide whether a schedule is operationally
sustainable BEFORE running it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


def _int(headers: Mapping[str, str], key: str) -> Optional[int]:
    for k in (key, key.lower()):
        if k in headers:
            try:
                return int(headers[k])
            except (TypeError, ValueError):
                return None
    return None


@dataclass(frozen=True)
class RateLimitState:
    """Parsed budgets from a single response's headers.

    ``-1`` limits/remaining mean "no cap" (uncapped plan). ``None`` means the
    header was absent (we then fail conservatively — treat as unknown, do not
    assume plenty of budget).
    """

    minute_limit: Optional[int]
    minute_remaining: Optional[int]
    minute_reset: Optional[int]
    monthly_limit: Optional[int]
    monthly_remaining: Optional[int]
    monthly_reset: Optional[int]
    retry_after: Optional[float]

    @property
    def minute_uncapped(self) -> bool:
        return self.minute_limit == -1

    @property
    def monthly_uncapped(self) -> bool:
        return self.monthly_limit == -1

    def should_pause(self, *, min_remaining: int = 1) -> bool:
        """Conservatively decide whether to pause before the next request.

        Pauses when a known (capped) budget's remaining is at or below
        ``min_remaining`` — because ``Remaining == 0`` means the next request
        is rejected. Absent headers are treated as unknown => pause (fail safe).
        """
        for remaining, uncapped in (
            (self.minute_remaining, self.minute_uncapped),
            (self.monthly_remaining, self.monthly_uncapped),
        ):
            if remaining is None:
                return True  # unknown budget: be conservative
            if not uncapped and remaining <= min_remaining:
                return True
        return False


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimitState:
    """Parse rate-limit / quota headers into a :class:`RateLimitState`."""
    retry = headers.get("Retry-After", headers.get("retry-after"))
    try:
        retry_after = float(retry) if retry is not None else None
    except (TypeError, ValueError):
        retry_after = None
    return RateLimitState(
        minute_limit=_int(headers, "X-RateLimit-Limit"),
        minute_remaining=_int(headers, "X-RateLimit-Remaining"),
        minute_reset=_int(headers, "X-RateLimit-Reset"),
        monthly_limit=_int(headers, "X-Monthly-Quota-Limit"),
        monthly_remaining=_int(headers, "X-Monthly-Quota-Remaining"),
        monthly_reset=_int(headers, "X-Monthly-Quota-Reset"),
        retry_after=retry_after,
    )


@dataclass(frozen=True)
class ScheduleBudget:
    """Estimated request budget for a proposed capture schedule.

    Attributes:
        requests_per_fixture: Total requests to fully capture one fixture
            across all vintages + lineup polling + context.
        fixtures_per_day: Expected supported fixtures per day.
        requests_per_day: requests_per_fixture * fixtures_per_day.
        requests_per_month: requests_per_day * 30.
        monthly_limit: The plan's monthly cap (None if unknown, -1 uncapped).
        sustainable: Whether the monthly estimate fits the cap (True if
            uncapped; None if the cap is unknown).
    """

    requests_per_fixture: int
    fixtures_per_day: int
    requests_per_day: int
    requests_per_month: int
    monthly_limit: Optional[int]
    sustainable: Optional[bool]

    def to_dict(self) -> dict:
        return {
            "requests_per_fixture": self.requests_per_fixture,
            "fixtures_per_day": self.fixtures_per_day,
            "requests_per_day": self.requests_per_day,
            "requests_per_month": self.requests_per_month,
            "monthly_limit": self.monthly_limit,
            "sustainable": self.sustainable,
        }


def estimate_budget(
    *,
    odds_snapshots_per_fixture: int,
    lineup_polls_per_fixture: int,
    context_requests_per_fixture: int,
    fixtures_per_day: int,
    monthly_limit: Optional[int] = None,
    days_per_month: int = 30,
) -> ScheduleBudget:
    """Estimate the request budget for a proposed schedule.

    ``requests_per_fixture`` = odds snapshots + lineup polls + context
    (match detail / referee / injuries) requests. Sustainability is judged
    against the monthly cap: uncapped => True; unknown => None; else compare.
    """
    per_fixture = (
        odds_snapshots_per_fixture + lineup_polls_per_fixture + context_requests_per_fixture
    )
    per_day = per_fixture * fixtures_per_day
    per_month = per_day * days_per_month
    if monthly_limit is None:
        sustainable: Optional[bool] = None
    elif monthly_limit == -1:
        sustainable = True
    else:
        sustainable = per_month <= monthly_limit
    return ScheduleBudget(
        requests_per_fixture=per_fixture,
        fixtures_per_day=fixtures_per_day,
        requests_per_day=per_day,
        requests_per_month=per_month,
        monthly_limit=monthly_limit,
        sustainable=sustainable,
    )


# ---------------------------------------------------------------------------
# Reserve-aware allocation planner (full-universe design)
# ---------------------------------------------------------------------------

#: Per-fixture request cost model for the FULL capture lifecycle.
#: Discovery is amortised per fixture (one competition-scoped query yields many
#: fixtures), but polling/retries/monitoring are per-fixture and must be counted
#: so the estimate is not the naive monthly_limit / odds_snapshots.
@dataclass(frozen=True)
class FixtureCostModel:
    """Per-fixture request cost across the whole capture lifecycle."""

    odds_snapshots: int = 8          # EARLY..FINAL + approach-window snapshots
    lineup_polls: int = 4            # polling from LATE window until first seen
    injury_snapshots: int = 2        # one per team, near lineup window
    referee_requests: int = 1        # match context
    discovery_amortised: float = 0.5  # shared competition-scoped discovery query
    monitoring_amortised: float = 0.2  # quality-report / health probes
    retry_overhead_rate: float = 0.10  # +10% for retries/backoff re-requests

    def requests_per_fixture(self) -> float:
        base = (
            self.odds_snapshots + self.lineup_polls + self.injury_snapshots
            + self.referee_requests + self.discovery_amortised + self.monitoring_amortised
        )
        return base * (1.0 + self.retry_overhead_rate)


@dataclass(frozen=True)
class AllocationPlan:
    """Reserve-aware monthly allocation plan for the active universe."""

    monthly_limit: Optional[int]
    reserve_fraction: float
    usable_monthly: Optional[int]        # limit * (1 - reserve)
    requests_per_fixture: float
    fixtures_per_month_capacity: Optional[int]  # usable / per-fixture
    projected_fixtures_per_month: int    # expected active fixtures
    projected_requests_per_month: float
    within_usable: Optional[bool]
    headroom_requests: Optional[float]

    def to_dict(self) -> dict:
        return {
            "monthly_limit": self.monthly_limit,
            "reserve_fraction": self.reserve_fraction,
            "usable_monthly": self.usable_monthly,
            "requests_per_fixture": round(self.requests_per_fixture, 2),
            "fixtures_per_month_capacity": self.fixtures_per_month_capacity,
            "projected_fixtures_per_month": self.projected_fixtures_per_month,
            "projected_requests_per_month": round(self.projected_requests_per_month, 1),
            "within_usable": self.within_usable,
            "headroom_requests": (round(self.headroom_requests, 1)
                                  if self.headroom_requests is not None else None),
        }


def plan_allocation(
    *,
    monthly_limit: Optional[int],
    projected_fixtures_per_month: int,
    cost_model: Optional[FixtureCostModel] = None,
    reserve_fraction: float = 0.20,
) -> AllocationPlan:
    """Plan monthly allocation with a hard reserve (default 20%).

    Never targets the full quota: usable = limit * (1 - reserve). Capacity and
    headroom are computed from the FULL per-fixture cost (incl. discovery,
    polling, retries, monitoring) — not the naive limit / odds_snapshots.
    """
    cm = cost_model or FixtureCostModel()
    rpf = cm.requests_per_fixture()
    projected_requests = rpf * projected_fixtures_per_month

    if monthly_limit is None or monthly_limit == -1:
        return AllocationPlan(
            monthly_limit=monthly_limit, reserve_fraction=reserve_fraction,
            usable_monthly=None, requests_per_fixture=rpf,
            fixtures_per_month_capacity=None,
            projected_fixtures_per_month=projected_fixtures_per_month,
            projected_requests_per_month=projected_requests,
            within_usable=None if monthly_limit is None else True,
            headroom_requests=None,
        )

    usable = int(monthly_limit * (1.0 - reserve_fraction))
    capacity = int(usable / rpf) if rpf > 0 else 0
    headroom = usable - projected_requests
    return AllocationPlan(
        monthly_limit=monthly_limit, reserve_fraction=reserve_fraction,
        usable_monthly=usable, requests_per_fixture=rpf,
        fixtures_per_month_capacity=capacity,
        projected_fixtures_per_month=projected_fixtures_per_month,
        projected_requests_per_month=projected_requests,
        within_usable=projected_requests <= usable,
        headroom_requests=headroom,
    )


class QuotaGuard:
    """Runtime guard: decides whether the collector may issue another request.

    Reserve-aware: refuses new work once the live monthly remaining falls below
    the reserve floor, and pauses on the per-minute budget. Fails safe when the
    budget is unknown.
    """

    def __init__(self, *, monthly_limit: Optional[int], reserve_fraction: float = 0.20) -> None:
        self.monthly_limit = monthly_limit
        self.reserve_floor = (
            int(monthly_limit * reserve_fraction)
            if (monthly_limit is not None and monthly_limit != -1)
            else 0
        )

    def may_request(self, state: Optional[RateLimitState]) -> bool:
        """Whether another request is allowed given the latest budget state."""
        if state is None:
            return True  # no observation yet; the client throttle still applies
        if state.should_pause():
            return False
        if (
            self.monthly_limit not in (None, -1)
            and state.monthly_remaining is not None
            and state.monthly_remaining <= self.reserve_floor
        ):
            return False  # protect the reserve
        return True
