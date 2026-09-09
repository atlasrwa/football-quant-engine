"""Price-discovery research row schema and market-movement diagnostics.

The first research target of this phase is NOT match outcome. It is:

    Does information available at time t predict subsequent SHARP-MARKET
    movement (e.g. logit(Pinnacle FINAL) - logit(Pinnacle LATE))?

This module builds the leakage-safe research row and the descriptive
diagnostics that can run on small samples, always reporting sample size and
never claiming alpha from tiny N.

Hard constraints enforced here:
- Market movement is computed in LOGIT probability space AFTER de-vig.
- A direct price movement requires the SAME bookmaker, market, selection AND
  line. Cross-bookmaker or cross-line "movement" is refused (returns None).
- Line movement is tracked SEPARATELY from price movement; the two are never
  conflated.
- ``outcome`` is optional: a row is valid without it (outcome fills in later).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

_EPS = 1e-9


def _logit(p: Optional[float]) -> Optional[float]:
    if p is None or not (0.0 < p < 1.0):
        return None
    return math.log(p / (1.0 - p))


@dataclass(frozen=True)
class PriceDiscoveryRow:
    """One research-ready row for the price-discovery dataset.

    Outcome and later-market fields may be absent when the row is first
    created; they are filled as later snapshots / results arrive.
    """

    fixture_id: str
    league: Optional[str]
    kickoff_ts: Optional[float]

    market: str
    selection: str
    line: Optional[float]
    bookmaker: str

    forecast_vintage: str
    observed_at: float
    seconds_to_kickoff: Optional[float]

    p_market: Optional[float]
    p_fundamental: Optional[float] = None

    lineup_available: bool = False
    lineup_first_observed_at: Optional[float] = None
    lineup_delta_features: dict = field(default_factory=dict)

    injury_snapshot_available: bool = False
    injury_delta_features: dict = field(default_factory=dict)

    referee_available: bool = False

    later_market_probability: Optional[float] = None
    final_pre_kickoff_probability: Optional[float] = None

    outcome: Optional[bool] = None

    @property
    def market_logit(self) -> Optional[float]:
        return _logit(self.p_market)

    @property
    def fundamental_logit(self) -> Optional[float]:
        return _logit(self.p_fundamental)

    @property
    def fundamental_minus_market(self) -> Optional[float]:
        fl, ml = self.fundamental_logit, self.market_logit
        return None if fl is None or ml is None else fl - ml

    @property
    def later_market_logit(self) -> Optional[float]:
        return _logit(self.later_market_probability)

    @property
    def market_move_target(self) -> Optional[float]:
        """logit(later) - logit(current): the primary price-discovery target."""
        lm, ml = self.later_market_logit, self.market_logit
        return None if lm is None or ml is None else lm - ml

    def to_dict(self) -> dict:
        return {
            "fixture_id": self.fixture_id,
            "league": self.league,
            "kickoff_ts": self.kickoff_ts,
            "market": self.market,
            "selection": self.selection,
            "line": self.line,
            "bookmaker": self.bookmaker,
            "forecast_vintage": self.forecast_vintage,
            "observed_at": self.observed_at,
            "seconds_to_kickoff": self.seconds_to_kickoff,
            "p_market": self.p_market,
            "market_logit": self.market_logit,
            "p_fundamental": self.p_fundamental,
            "fundamental_logit": self.fundamental_logit,
            "fundamental_minus_market": self.fundamental_minus_market,
            "lineup_available": self.lineup_available,
            "lineup_first_observed_at": self.lineup_first_observed_at,
            "lineup_delta_features": self.lineup_delta_features,
            "injury_snapshot_available": self.injury_snapshot_available,
            "injury_delta_features": self.injury_delta_features,
            "referee_available": self.referee_available,
            "later_market_probability": self.later_market_probability,
            "later_market_logit": self.later_market_logit,
            "market_move_target": self.market_move_target,
            "final_pre_kickoff_probability": self.final_pre_kickoff_probability,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class PriceObservation:
    """A de-vigged probability at a point in time for a specific key."""

    bookmaker: str
    market: str
    selection: str
    line: Optional[float]
    observed_at: float
    p_fair: float


def same_key(a: PriceObservation, b: PriceObservation) -> bool:
    """Whether two observations share bookmaker+market+selection+line."""
    return (
        a.bookmaker == b.bookmaker
        and a.market == b.market
        and a.selection == b.selection
        and a.line == b.line
    )


def price_movement_logit(
    earlier: PriceObservation, later: PriceObservation
) -> Optional[float]:
    """logit(p_later) - logit(p_earlier) for the SAME key, else None.

    Refuses cross-bookmaker and cross-line comparisons (returns None) so no fake
    continuity is created.
    """
    if not same_key(earlier, later):
        return None
    le, ll = _logit(earlier.p_fair), _logit(later.p_fair)
    if le is None or ll is None:
        return None
    return ll - le


@dataclass(frozen=True)
class LineMovement:
    """Line movement kept SEPARATE from price movement."""

    bookmaker: str
    market: str
    selection: str
    earlier_line: Optional[float]
    later_line: Optional[float]

    @property
    def changed(self) -> bool:
        return self.earlier_line != self.later_line


def line_movement(
    earlier: PriceObservation, later: PriceObservation
) -> Optional[LineMovement]:
    """Track offered-line change for same book/market/selection (any line)."""
    if not (
        earlier.bookmaker == later.bookmaker
        and earlier.market == later.market
        and earlier.selection == later.selection
    ):
        return None
    return LineMovement(
        bookmaker=earlier.bookmaker, market=earlier.market, selection=earlier.selection,
        earlier_line=earlier.line, later_line=later.line,
    )


def signed_clv_direction(
    *,
    model_disagreement: Optional[float],
    current_market_logit: Optional[float],
    later_market_logit: Optional[float],
) -> Optional[float]:
    """signed_clv = sign(disagreement) * (later_market_logit - current_market_logit).

    Positive = favourable price discovery (the market moved toward the model's
    disagreement direction). None when any input is missing. This is research
    evidence, NOT betting profit.
    """
    if model_disagreement is None or current_market_logit is None or later_market_logit is None:
        return None
    move = later_market_logit - current_market_logit
    sign = 0.0 if model_disagreement == 0 else math.copysign(1.0, model_disagreement)
    return sign * move
