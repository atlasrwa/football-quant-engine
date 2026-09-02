"""Expected Value calculator and research prediction layer.

.. deprecated::
    **DEPRECATED — EV / edge / market-comparison layer.** The market-beating
    objective is closed: the edge ceiling was *measured* (median edge 0-1pp vs a
    2-4pp requirement; market realized rate inside the 95% CI of its price in
    every well-populated bucket). This module is retained, NOT deleted, for
    Pilot C's pre-registered forward experiment and for internal research only —
    it is **not a product claim**. Do not build new user-facing features on it,
    and never present EV/edge/value/"beats the market" framing. The supported
    deliverable is the calibrated prediction engine in
    :mod:`src.research.prediction_engine`. See :mod:`src.research._ev_deprecation`.

Implements: EV = P(model outcome) × decimal_odds - 1

Clearly distinguishes:
- Feature: raw input data
- Signal: model output (direction + strength)
- Model probability: P(outcome | features) from ProbabilityModel
- Fair odds: 1/P(model) — what odds SHOULD be if model is correct
- Market odds: externally observed bookmaker price
- Implied probability: 1/market_odds (includes margin)
- Fair probability: margin-stripped from market odds (de-vigged)
- Edge: P(model) - P(fair) — probability advantage
- EV: P(model) × market_odds - 1 — expected economic profit

Does NOT claim profitability. Provides the mathematical framework
for evaluating whether a model has edge over the market.

Supports:
- Two-way markets (OVER/UNDER, YES/NO)
- Three-way markets (HOME/DRAW/AWAY)
- De-vigging / margin removal (multiple methods)
- Fair odds conversion from probabilities
- Kelly criterion sizing (not execution)
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.research.market import MarketDirection, MarketOutcome, ResearchMarket
from src.research.probability import (
    ModelIdentity,
    PredictionStatus,
    ProbabilityEstimate,
    ThreeWayProbabilityEstimate,
    TrainingMetadata,
)


# ═══════════════════════════════════════════════════════════════
# EV STATUS
# ═══════════════════════════════════════════════════════════════


class EVStatus(Enum):
    """Status of an EV calculation attempt."""

    VALID = "VALID"
    MISSING_ODDS = "MISSING_ODDS"
    INVALID_ODDS = "INVALID_ODDS"
    INVALID_PROBABILITY = "INVALID_PROBABILITY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ═══════════════════════════════════════════════════════════════
# FAIR ODDS CONVERSION
# ═══════════════════════════════════════════════════════════════


def probability_to_fair_odds(probability: float) -> Optional[float]:
    """Convert a probability to fair decimal odds.

    fair_odds = 1 / P

    Args:
        probability: Must be in (0, 1).

    Returns:
        Fair decimal odds, or None if probability is invalid.
    """
    if probability <= 0.0 or probability >= 1.0:
        return None
    return 1.0 / probability


def fair_odds_to_probability(odds: float) -> Optional[float]:
    """Convert fair decimal odds to probability.

    P = 1 / odds

    Args:
        odds: Must be > 1.0 for a valid market.

    Returns:
        Probability, or None if odds are invalid.
    """
    if odds <= 1.0:
        return None
    return 1.0 / odds


# ═══════════════════════════════════════════════════════════════
# DE-VIGGING / MARGIN REMOVAL
# ═══════════════════════════════════════════════════════════════


class DevigMethod(Enum):
    """Method for removing bookmaker margin from odds."""

    MULTIPLICATIVE = "MULTIPLICATIVE"  # Proportional: P_fair = P_raw / sum(P_raw)
    ADDITIVE = "ADDITIVE"             # Subtract equal margin from each side
    POWER = "POWER"                   # Power method (odds-ratio): find k where sum(p_i^k) = 1


class MarketProbabilityNormalizer:
    """Strips bookmaker margin to derive fair probabilities from market odds.

    The bookmaker's overround means implied probabilities sum to > 1.
    De-vigging removes this margin to recover fair probabilities.

    Methods:
    - MULTIPLICATIVE (default): Each probability scaled proportionally.
      Simple, widely used. Assumes margin is proportional to probability.
    - ADDITIVE: Equal margin subtracted from each side.
      Better for heavily-skewed markets.
    - POWER: Odds-ratio power method.
      More theoretically justified for efficient markets — finds k where sum(p_i^k) = 1.
    """

    def __init__(self, method: DevigMethod = DevigMethod.MULTIPLICATIVE) -> None:
        self._method = method

    @property
    def method(self) -> DevigMethod:
        """Current de-vigging method."""
        return self._method

    def normalize_two_way(
        self, over_odds: float, under_odds: float
    ) -> Optional[tuple[float, float]]:
        """Remove margin from a two-way market.

        Args:
            over_odds: Decimal odds for OVER side.
            under_odds: Decimal odds for UNDER side.

        Returns:
            (fair_over_prob, fair_under_prob) summing to 1.0,
            or None if odds are invalid.
        """
        if over_odds <= 1.0 or under_odds <= 1.0:
            return None

        raw_over = 1.0 / over_odds
        raw_under = 1.0 / under_odds

        if self._method == DevigMethod.MULTIPLICATIVE:
            total = raw_over + raw_under
            if total == 0:
                return None
            return raw_over / total, raw_under / total

        elif self._method == DevigMethod.ADDITIVE:
            overround = raw_over + raw_under - 1.0
            margin_per_side = overround / 2.0
            fair_over = raw_over - margin_per_side
            fair_under = raw_under - margin_per_side
            # Ensure valid probabilities
            if fair_over <= 0 or fair_under <= 0:
                # Fall back to multiplicative
                total = raw_over + raw_under
                return raw_over / total, raw_under / total
            total = fair_over + fair_under
            return fair_over / total, fair_under / total

        elif self._method == DevigMethod.POWER:
            # Power method: find exponent k such that sum(p_i^k) = 1
            # where p_i are raw implied probabilities. Uses bisection.
            overround = raw_over + raw_under
            if overround <= 1.0:
                return raw_over, raw_under

            def _target(k: float) -> float:
                return raw_over ** k + raw_under ** k - 1.0

            # Bisect: k=1 gives overround-1 > 0; as k→∞, target→0 (max(p)^k→0)
            lo, hi = 1.0, 20.0
            for _ in range(64):  # Converges in ~50 iterations to machine precision
                mid = (lo + hi) / 2.0
                if _target(mid) > 0:
                    lo = mid
                else:
                    hi = mid

            k = (lo + hi) / 2.0
            fair_over = raw_over ** k
            fair_under = raw_under ** k
            total = fair_over + fair_under
            return fair_over / total, fair_under / total

        return None

    def normalize_three_way(
        self, home_odds: float, draw_odds: float, away_odds: float
    ) -> Optional[tuple[float, float, float]]:
        """Remove margin from a three-way market.

        Args:
            home_odds: Decimal odds for HOME.
            draw_odds: Decimal odds for DRAW.
            away_odds: Decimal odds for AWAY.

        Returns:
            (fair_home, fair_draw, fair_away) summing to 1.0,
            or None if odds are invalid.
        """
        if home_odds <= 1.0 or draw_odds <= 1.0 or away_odds <= 1.0:
            return None

        raw_home = 1.0 / home_odds
        raw_draw = 1.0 / draw_odds
        raw_away = 1.0 / away_odds

        if self._method == DevigMethod.MULTIPLICATIVE:
            total = raw_home + raw_draw + raw_away
            if total == 0:
                return None
            return raw_home / total, raw_draw / total, raw_away / total

        elif self._method == DevigMethod.ADDITIVE:
            overround = raw_home + raw_draw + raw_away - 1.0
            margin_each = overround / 3.0
            fair_home = raw_home - margin_each
            fair_draw = raw_draw - margin_each
            fair_away = raw_away - margin_each
            if fair_home <= 0 or fair_draw <= 0 or fair_away <= 0:
                total = raw_home + raw_draw + raw_away
                return raw_home / total, raw_draw / total, raw_away / total
            total = fair_home + fair_draw + fair_away
            return fair_home / total, fair_draw / total, fair_away / total

        elif self._method == DevigMethod.POWER:
            # Power method: find exponent k such that sum(p_i^k) = 1
            overround = raw_home + raw_draw + raw_away
            if overround <= 1.0:
                return raw_home, raw_draw, raw_away

            def _target(k: float) -> float:
                return raw_home ** k + raw_draw ** k + raw_away ** k - 1.0

            lo, hi = 1.0, 20.0
            for _ in range(64):
                mid = (lo + hi) / 2.0
                if _target(mid) > 0:
                    lo = mid
                else:
                    hi = mid

            k = (lo + hi) / 2.0
            fair_home = raw_home ** k
            fair_draw = raw_draw ** k
            fair_away = raw_away ** k
            total = fair_home + fair_draw + fair_away
            return fair_home / total, fair_draw / total, fair_away / total

        return None

    def compute_overround(self, *odds: float) -> Optional[float]:
        """Calculate the overround (margin) from a set of odds.

        Returns the percentage above 100% that implied probabilities sum to.
        E.g., odds of 1.90 / 2.00 have overround = 1/1.9 + 1/2.0 - 1 = 0.026 (2.6%)

        Returns None if any odds are invalid.
        """
        if any(o <= 1.0 for o in odds):
            return None
        total = sum(1.0 / o for o in odds)
        return total - 1.0


# ═══════════════════════════════════════════════════════════════
# EV RESULT TYPES
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class EVResult:
    """Expected value calculation result for a single prediction.

    Attributes:
        direction: OVER or UNDER.
        model_probability: P(outcome) from the model.
        market_odds: Decimal odds for this direction.
        implied_probability: 1/odds (includes margin).
        fair_probability: Margin-stripped market probability.
        expected_value: P(model) × odds - 1.
        edge: Model probability - fair probability.
        kelly_fraction: Optimal Kelly bet fraction: (p*odds - 1) / (odds - 1).
    """

    direction: MarketDirection
    model_probability: float
    market_odds: float
    implied_probability: float
    fair_probability: float
    expected_value: float
    edge: float
    kelly_fraction: float


@dataclass(frozen=True, slots=True)
class ThreeWayEVResult:
    """Expected value calculation for a three-way market (1X2).

    Attributes:
        ev_home: EV for backing HOME.
        ev_draw: EV for backing DRAW.
        ev_away: EV for backing AWAY.
        best_outcome: Which outcome has the highest EV.
        best_ev: The highest EV value.
        model_probs: The model's three-way probabilities.
        market_odds: (home_odds, draw_odds, away_odds).
        fair_probs: Margin-stripped probabilities.
        edges: (edge_home, edge_draw, edge_away).
        kelly_fractions: (kelly_home, kelly_draw, kelly_away).
    """

    ev_home: float
    ev_draw: float
    ev_away: float
    best_outcome: MarketOutcome
    best_ev: float
    model_probs: tuple[float, float, float]
    market_odds: tuple[float, float, float]
    fair_probs: tuple[float, float, float]
    edges: tuple[float, float, float]
    kelly_fractions: tuple[float, float, float]


# ═══════════════════════════════════════════════════════════════
# RESEARCH PREDICTION
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ResearchPrediction:
    """A complete research prediction with all derived values.

    Contains everything needed to evaluate a prediction:
    probability, fair odds, market odds, EV, edge, and provenance.

    This is a RESEARCH object. It does NOT authorize execution.
    """

    # Identity
    market_type: str
    line: Optional[float]
    direction: Optional[str]  # OVER/UNDER/HOME/DRAW/AWAY

    # Model output
    model_probability: float
    model_id: Optional[str] = None
    model_version: Optional[int] = None

    # Fair value
    fair_odds: Optional[float] = None

    # Market
    market_odds: Optional[float] = None
    implied_probability: Optional[float] = None
    normalized_implied_probability: Optional[float] = None

    # Edge and EV
    edge: Optional[float] = None
    expected_value: Optional[float] = None
    kelly_fraction: Optional[float] = None

    # Status
    ev_status: EVStatus = EVStatus.VALID

    # Temporal
    prediction_timestamp: Optional[int] = None
    information_timestamp: Optional[int] = None

    # Provenance
    feature_version: Optional[str] = None
    dataset_version: Optional[str] = None

    @property
    def is_ev_positive(self) -> bool:
        """Whether this prediction has positive expected value."""
        return (
            self.ev_status == EVStatus.VALID
            and self.expected_value is not None
            and self.expected_value > 0
        )

    @property
    def is_kelly_positive(self) -> bool:
        """Whether Kelly criterion suggests a positive allocation."""
        return (
            self.kelly_fraction is not None
            and self.kelly_fraction > 0
        )


# ═══════════════════════════════════════════════════════════════
# EV CALCULATOR
# ═══════════════════════════════════════════════════════════════


class EVCalculator:
    """Computes expected value for market predictions.

    EV = P(model) × odds - 1

    Positive EV indicates the model believes the true probability
    exceeds what the market implies.

    Supports:
    - Two-way markets (OVER/UNDER)
    - Three-way markets (HOME/DRAW/AWAY)
    - Multiple de-vigging methods
    - Research prediction generation
    """

    def __init__(
        self, normalizer: Optional[MarketProbabilityNormalizer] = None
    ) -> None:
        """Initialize with an optional de-vigging normalizer.

        Args:
            normalizer: Method for margin removal. Defaults to multiplicative.

        .. deprecated::
            The EV layer is deprecated (market-beating objective closed). Retained
            for Pilot C and internal research only — not a product claim.
        """
        from src.research._ev_deprecation import warn_ev_layer_deprecated

        warn_ev_layer_deprecated("EVCalculator")
        self._normalizer = normalizer or MarketProbabilityNormalizer()

    @staticmethod
    def compute(
        estimate: ProbabilityEstimate,
        market: ResearchMarket,
        over_odds: float,
        under_odds: float,
        direction: Optional[MarketDirection] = None,
    ) -> Optional[EVResult]:
        """Compute EV for a prediction.

        If direction is None, evaluates both sides and returns
        the one with higher EV (if positive).

        Args:
            estimate: Model probability estimate.
            market: Market definition.
            over_odds: Decimal odds for OVER.
            under_odds: Decimal odds for UNDER.
            direction: Forced direction (None = pick best).

        Returns:
            EVResult if computable, None if odds invalid.
        """
        if over_odds <= 1.0 or under_odds <= 1.0:
            return None

        # Fair probabilities (margin-stripped)
        fair_over, fair_under = market.fair_probability(over_odds, under_odds)

        # Compute EV for both sides
        ev_over = estimate.p_over * over_odds - 1.0
        ev_under = estimate.p_under * under_odds - 1.0

        if direction == MarketDirection.OVER:
            chosen_dir = MarketDirection.OVER
        elif direction == MarketDirection.UNDER:
            chosen_dir = MarketDirection.UNDER
        else:
            # Pick the side with higher EV
            chosen_dir = MarketDirection.OVER if ev_over >= ev_under else MarketDirection.UNDER

        if chosen_dir == MarketDirection.OVER:
            p_model = estimate.p_over
            odds = over_odds
            fair_p = fair_over
            ev = ev_over
        else:
            p_model = estimate.p_under
            odds = under_odds
            fair_p = fair_under
            ev = ev_under

        implied_p = 1.0 / odds
        edge = p_model - fair_p

        # Kelly criterion: f* = (p * odds - 1) / (odds - 1) = EV / (odds - 1)
        kelly = ev / (odds - 1.0) if odds > 1.0 else 0.0
        kelly = max(0.0, kelly)

        return EVResult(
            direction=chosen_dir,
            model_probability=p_model,
            market_odds=odds,
            implied_probability=implied_p,
            fair_probability=fair_p,
            expected_value=ev,
            edge=edge,
            kelly_fraction=kelly,
        )

    @staticmethod
    def compute_both_sides(
        estimate: ProbabilityEstimate,
        market: ResearchMarket,
        over_odds: float,
        under_odds: float,
    ) -> tuple[Optional[EVResult], Optional[EVResult]]:
        """Compute EV for both OVER and UNDER sides.

        Returns:
            (over_result, under_result)
        """
        over_ev = EVCalculator.compute(
            estimate, market, over_odds, under_odds, MarketDirection.OVER
        )
        under_ev = EVCalculator.compute(
            estimate, market, over_odds, under_odds, MarketDirection.UNDER
        )
        return over_ev, under_ev

    def compute_three_way(
        self,
        estimate: ThreeWayProbabilityEstimate,
        home_odds: float,
        draw_odds: float,
        away_odds: float,
    ) -> Optional[ThreeWayEVResult]:
        """Compute EV for a three-way market (1X2).

        Evaluates HOME, DRAW, and AWAY independently.

        Args:
            estimate: Three-way probability estimate.
            home_odds: Decimal odds for HOME win.
            draw_odds: Decimal odds for DRAW.
            away_odds: Decimal odds for AWAY win.

        Returns:
            ThreeWayEVResult or None if odds invalid.
        """
        if home_odds <= 1.0 or draw_odds <= 1.0 or away_odds <= 1.0:
            return None

        # De-vig to get fair probabilities
        fair = self._normalizer.normalize_three_way(home_odds, draw_odds, away_odds)
        if fair is None:
            return None
        fair_home, fair_draw, fair_away = fair

        # EV for each outcome
        ev_home = estimate.p_home * home_odds - 1.0
        ev_draw = estimate.p_draw * draw_odds - 1.0
        ev_away = estimate.p_away * away_odds - 1.0

        # Edges
        edge_home = estimate.p_home - fair_home
        edge_draw = estimate.p_draw - fair_draw
        edge_away = estimate.p_away - fair_away

        # Kelly fractions: f* = (p * odds - 1) / (odds - 1) = EV / (odds - 1)
        kelly_home = max(0.0, ev_home / (home_odds - 1.0)) if home_odds > 1.0 else 0.0
        kelly_draw = max(0.0, ev_draw / (draw_odds - 1.0)) if draw_odds > 1.0 else 0.0
        kelly_away = max(0.0, ev_away / (away_odds - 1.0)) if away_odds > 1.0 else 0.0

        # Best outcome
        evs = {
            MarketOutcome.HOME: ev_home,
            MarketOutcome.DRAW: ev_draw,
            MarketOutcome.AWAY: ev_away,
        }
        best_outcome = max(evs, key=evs.get)
        best_ev = evs[best_outcome]

        return ThreeWayEVResult(
            ev_home=ev_home,
            ev_draw=ev_draw,
            ev_away=ev_away,
            best_outcome=best_outcome,
            best_ev=best_ev,
            model_probs=(estimate.p_home, estimate.p_draw, estimate.p_away),
            market_odds=(home_odds, draw_odds, away_odds),
            fair_probs=(fair_home, fair_draw, fair_away),
            edges=(edge_home, edge_draw, edge_away),
            kelly_fractions=(kelly_home, kelly_draw, kelly_away),
        )

    def create_research_prediction(
        self,
        estimate: ProbabilityEstimate,
        market: ResearchMarket,
        over_odds: Optional[float] = None,
        under_odds: Optional[float] = None,
        direction: Optional[MarketDirection] = None,
        model_identity: Optional[ModelIdentity] = None,
        prediction_timestamp: Optional[int] = None,
        information_timestamp: Optional[int] = None,
        feature_version: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> ResearchPrediction:
        """Create a complete ResearchPrediction with all derived values.

        Handles missing odds gracefully — returns prediction with MISSING_ODDS status
        rather than fabricating values.

        Args:
            estimate: Model probability estimate.
            market: Market definition.
            over_odds: Decimal odds for OVER (None if unavailable).
            under_odds: Decimal odds for UNDER (None if unavailable).
            direction: Forced direction.
            model_identity: Model identity for provenance.
            prediction_timestamp: When prediction was made.
            information_timestamp: Latest data used.
            feature_version: Feature definition version.
            dataset_version: Dataset version hash.

        Returns:
            ResearchPrediction with appropriate status.
        """
        # Determine direction
        if direction is None:
            direction = MarketDirection.OVER  # Default

        p_model = estimate.p_over if direction == MarketDirection.OVER else estimate.p_under
        fair_odds_val = probability_to_fair_odds(p_model)

        # Handle missing odds
        if over_odds is None or under_odds is None:
            return ResearchPrediction(
                market_type=market.market_type.value,
                line=market.line,
                direction=direction.value,
                model_probability=p_model,
                model_id=model_identity.content_hash if model_identity else None,
                model_version=model_identity.model_version if model_identity else None,
                fair_odds=fair_odds_val,
                ev_status=EVStatus.MISSING_ODDS,
                prediction_timestamp=prediction_timestamp,
                information_timestamp=information_timestamp,
                feature_version=feature_version,
                dataset_version=dataset_version,
            )

        # Handle invalid odds
        if over_odds <= 1.0 or under_odds <= 1.0:
            return ResearchPrediction(
                market_type=market.market_type.value,
                line=market.line,
                direction=direction.value,
                model_probability=p_model,
                model_id=model_identity.content_hash if model_identity else None,
                model_version=model_identity.model_version if model_identity else None,
                fair_odds=fair_odds_val,
                ev_status=EVStatus.INVALID_ODDS,
                prediction_timestamp=prediction_timestamp,
                information_timestamp=information_timestamp,
                feature_version=feature_version,
                dataset_version=dataset_version,
            )

        # Compute full EV
        odds = over_odds if direction == MarketDirection.OVER else under_odds
        implied_p = 1.0 / odds

        fair_result = self._normalizer.normalize_two_way(over_odds, under_odds)
        if fair_result is None:
            normalized_p = implied_p
        else:
            normalized_p = fair_result[0] if direction == MarketDirection.OVER else fair_result[1]

        edge = p_model - normalized_p
        ev = p_model * odds - 1.0
        kelly = max(0.0, ev / (odds - 1.0)) if odds > 1.0 else 0.0

        return ResearchPrediction(
            market_type=market.market_type.value,
            line=market.line,
            direction=direction.value,
            model_probability=p_model,
            model_id=model_identity.content_hash if model_identity else None,
            model_version=model_identity.model_version if model_identity else None,
            fair_odds=fair_odds_val,
            market_odds=odds,
            implied_probability=implied_p,
            normalized_implied_probability=normalized_p,
            edge=edge,
            expected_value=ev,
            kelly_fraction=kelly,
            ev_status=EVStatus.VALID,
            prediction_timestamp=prediction_timestamp,
            information_timestamp=information_timestamp,
            feature_version=feature_version,
            dataset_version=dataset_version,
        )
