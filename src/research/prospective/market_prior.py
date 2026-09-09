"""Market prior abstraction.

For each (fixture, forecast vintage, market, line) the market prior is the
no-vig bookmaker probability at a specific *observed* timestamp, with an
explicit availability status. Stale observations are never used silently:
the age relative to the forecast cutoff is always reported.

The market is the PRIOR. Downstream, the residual model applies a delta on top
of ``logit(market_prior.fair_probability)``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.research.prospective.odds_capture import (
    BENCHMARK_HIERARCHY,
    CapturedPrice,
    devig_two_way,
    select_benchmark_bookmaker,
)


class MarketAvailability(str, Enum):
    NO_MARKET = "NO_MARKET"
    STALE_MARKET = "STALE_MARKET"
    VALID_MARKET = "VALID_MARKET"


@dataclass(frozen=True)
class MarketPrior:
    """No-vig market prior for one (fixture, vintage, market, line).

    Attributes:
        fixture_id: Canonical fixture id.
        market: Market key (e.g. "match_corners").
        line: The over/under line, or None for two-/three-way markets.
        selection: The selection this probability is FOR (e.g. "over").
        fair_probability: De-vigged probability of ``selection``, or None when
            NO_MARKET.
        bookmaker: The benchmark bookmaker slug used, or None.
        raw_odds: The raw decimal odds of ``selection`` (pre de-vig), or None.
        vig_method: De-vig method applied ("multiplicative"/"shin").
        observed_at: When the underlying price was observed (unix), or None.
        age_seconds: cutoff_ts - observed_at (>=0), or None when unknown.
        source: Provider id.
        availability_status: NO_MARKET / STALE_MARKET / VALID_MARKET.
    """

    fixture_id: str
    market: str
    line: Optional[float]
    selection: str
    fair_probability: Optional[float]
    bookmaker: Optional[str]
    raw_odds: Optional[float]
    vig_method: str
    observed_at: Optional[float]
    age_seconds: Optional[float]
    source: str
    availability_status: MarketAvailability

    @property
    def logit(self) -> Optional[float]:
        """logit(fair_probability), or None when unavailable/degenerate."""
        p = self.fair_probability
        if p is None or not (0.0 < p < 1.0):
            return None
        return math.log(p / (1.0 - p))


def build_market_prior(
    *,
    fixture_id: str,
    market: str,
    line: Optional[float],
    selection: str,
    over_price: Optional[CapturedPrice],
    under_price: Optional[CapturedPrice],
    cutoff_ts: float,
    source: str = "thestatsapi",
    vig_method: str = "multiplicative",
    stale_after_seconds: float = 48 * 3600,
    hierarchy: tuple[str, ...] = BENCHMARK_HIERARCHY,
) -> MarketPrior:
    """Construct a :class:`MarketPrior` from a paired over/under capture.

    The two prices must be for the SAME bookmaker/market/line (they form the
    two-way de-vig set). ``selection`` picks which side's fair probability is
    reported. Availability:

    - NO_MARKET   : either side missing, or no benchmark bookmaker present.
    - STALE_MARKET: observed_at is older than ``stale_after_seconds`` before
      the cutoff, or observed_at is after the cutoff (not yet available), or
      observed_at is unknown.
    - VALID_MARKET: a fresh, PIT-consultable, de-viggable pair.
    """
    if over_price is None or under_price is None:
        return MarketPrior(
            fixture_id=fixture_id, market=market, line=line, selection=selection,
            fair_probability=None, bookmaker=None, raw_odds=None, vig_method=vig_method,
            observed_at=None, age_seconds=None, source=source,
            availability_status=MarketAvailability.NO_MARKET,
        )

    benchmark = select_benchmark_bookmaker([over_price.bookmaker], hierarchy=hierarchy)
    if benchmark is None or over_price.bookmaker != under_price.bookmaker:
        return MarketPrior(
            fixture_id=fixture_id, market=market, line=line, selection=selection,
            fair_probability=None, bookmaker=None, raw_odds=None, vig_method=vig_method,
            observed_at=None, age_seconds=None, source=source,
            availability_status=MarketAvailability.NO_MARKET,
        )

    observed_at = over_price.observed_at
    age = None if observed_at is None else cutoff_ts - observed_at

    result = devig_two_way(over_price.decimal_odds, under_price.decimal_odds, method=vig_method)
    fair = result.fair_probabilities["OVER" if selection == "over" else "UNDER"]
    raw = over_price.decimal_odds if selection == "over" else under_price.decimal_odds

    # Staleness: unknown time, future time (not yet observable), or too old.
    if observed_at is None or age is None or age < 0 or age > stale_after_seconds:
        status = MarketAvailability.STALE_MARKET
    else:
        status = MarketAvailability.VALID_MARKET

    return MarketPrior(
        fixture_id=fixture_id, market=market, line=line, selection=selection,
        fair_probability=fair, bookmaker=benchmark, raw_odds=raw, vig_method=result.method,
        observed_at=observed_at, age_seconds=age, source=source,
        availability_status=status,
    )
