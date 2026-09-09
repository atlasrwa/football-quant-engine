"""Neutral wrapper around the champion / fundamental signal.

The champion model (``src/research/models/hierarchical_market_model.py``) is
NOT modified. This module only *wraps* a champion probability into a neutral
research object and computes the disagreement between fundamental and market
in log-odds space. Disagreement is a FEATURE, not a claim of superiority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from src.research.prospective.market_prior import MarketPrior

_EPS = 1e-9


def _logit(p: float) -> float:
    p = min(max(p, _EPS), 1.0 - _EPS)
    return math.log(p / (1.0 - p))


@dataclass(frozen=True)
class FundamentalForecast:
    """Champion output wrapped for research, provenance intact.

    Attributes:
        fixture_id: Canonical fixture id.
        market: Market key.
        line: Over/under line (or None).
        selection: Selection this probability is for (e.g. "over").
        probability: Champion probability of ``selection``.
        forecast_cutoff: The PIT cutoff at which this forecast was produced.
        model_version: Champion model version tag.
        provenance: Opaque provenance dict from the champion (never mutated).
    """

    fixture_id: str
    market: str
    line: Optional[float]
    selection: str
    probability: float
    forecast_cutoff: float
    model_version: str
    provenance: dict[str, Any]

    @property
    def logit(self) -> float:
        return _logit(self.probability)


@dataclass(frozen=True)
class Disagreement:
    """Fundamental-vs-market disagreement in log-odds space.

    ``fundamental_minus_market`` > 0 means the fundamental model is MORE
    bullish on ``selection`` than the market. This is the primary residual
    feature. ``available`` is False when the market prior is unusable, in which
    case the residual must shrink to the market (handled downstream).
    """

    fixture_id: str
    market: str
    line: Optional[float]
    selection: str
    fundamental_logit: float
    market_logit: Optional[float]
    fundamental_minus_market: Optional[float]
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "market": self.market,
            "line": self.line,
            "selection": self.selection,
            "fundamental_logit": self.fundamental_logit,
            "market_logit": self.market_logit,
            "fundamental_minus_market": self.fundamental_minus_market,
            "available": self.available,
        }


def compute_disagreement(
    fundamental: FundamentalForecast,
    market: MarketPrior,
) -> Disagreement:
    """Compute the disagreement feature between a fundamental and a market prior.

    Alignment on (fixture, market, line, selection) is asserted so we never
    compare mismatched quantities.
    """
    if (
        fundamental.fixture_id != market.fixture_id
        or fundamental.market != market.market
        or fundamental.line != market.line
        or fundamental.selection != market.selection
    ):
        raise ValueError("fundamental / market prior misaligned; refusing to compare")

    m_logit = market.logit
    delta = None if m_logit is None else fundamental.logit - m_logit
    return Disagreement(
        fixture_id=fundamental.fixture_id,
        market=fundamental.market,
        line=fundamental.line,
        selection=fundamental.selection,
        fundamental_logit=fundamental.logit,
        market_logit=m_logit,
        fundamental_minus_market=delta,
        available=delta is not None,
    )
