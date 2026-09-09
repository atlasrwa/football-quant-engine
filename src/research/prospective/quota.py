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
