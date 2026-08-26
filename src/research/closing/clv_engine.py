"""CLV Engine — genuine Closing Line Value calculation.

Methodology: PRICE-BASED CLV (documented, single convention)

    CLV = (entry_odds / closing_odds) - 1

Interpretation:
    Positive CLV: Entry odds were better than closing (market moved against us = sharp)
    Negative CLV: Entry odds were worse than closing
    Zero: Exactly at closing line

For overround-adjusted CLV (where data allows):
    fair_closing_prob = closing_implied_prob / overround_factor
    CLV_adjusted = fair_closing_prob - entry_implied_prob

This module:
- Calculates CLV only from validated genuine closing observations
- Supports raw and optionally overround-adjusted calculations
- Is deterministic and reproducible
- Never fabricates CLV from estimated/unknown data
- Clearly distinguishes genuine from estimated CLV

CLV is EVALUATION-ONLY. It must NEVER influence predictions or staking.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.research.closing.provider import ClosingOddsObservation, ClosingOddsStatus
from src.research.closing.validation import ClosingLineValidator, ClosingValidationResult


class CLVMethodology(Enum):
    """CLV calculation methodology."""
    PRICE_BASED = "PRICE_BASED"          # (entry_odds / closing_odds) - 1
    PROBABILITY_BASED = "PROBABILITY_BASED"  # closing_implied - entry_implied
    OVERROUND_ADJUSTED = "OVERROUND_ADJUSTED"  # With overround normalization


@dataclass(frozen=True)
class CLVCalculation:
    """Immutable result of a CLV calculation.

    Once computed, this is NEVER modified.
    """
    trade_id: str
    entry_odds: float
    closing_odds: float
    clv: float
    methodology: CLVMethodology
    entry_implied_prob: float
    closing_implied_prob: float
    is_positive: bool
    is_genuine: bool  # Whether closing odds were verified genuine
    closing_source: str = ""
    closing_bookmaker: str = ""
    overround: Optional[float] = None  # If overround adjustment applied
    status: ClosingOddsStatus = ClosingOddsStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "entry_odds": self.entry_odds,
            "closing_odds": self.closing_odds,
            "clv": round(self.clv, 6),
            "methodology": self.methodology.value,
            "entry_implied_prob": round(self.entry_implied_prob, 6),
            "closing_implied_prob": round(self.closing_implied_prob, 6),
            "is_positive": self.is_positive,
            "is_genuine": self.is_genuine,
            "closing_source": self.closing_source,
            "closing_bookmaker": self.closing_bookmaker,
            "overround": self.overround,
            "status": self.status.value,
        }


class CLVEngine:
    """Calculates CLV from validated closing odds observations.

    Uses PRICE-BASED methodology by default:
        CLV = (entry_odds / closing_odds) - 1

    Only computes from validated observations.
    Never fabricates CLV from unavailable or invalid data.
    """

    def __init__(
        self,
        methodology: CLVMethodology = CLVMethodology.PRICE_BASED,
        validator: Optional[ClosingLineValidator] = None,
        require_genuine: bool = True,
    ) -> None:
        """Initialize CLV engine.

        Args:
            methodology: Which CLV formula to use.
            validator: Closing line validator (default creates one).
            require_genuine: If True, only compute from genuine closing data.
        """
        self._methodology = methodology
        self._validator = validator or ClosingLineValidator()
        self._require_genuine = require_genuine

    @property
    def methodology(self) -> CLVMethodology:
        return self._methodology

    def calculate(
        self,
        trade_id: str,
        entry_odds: float,
        closing_observation: ClosingOddsObservation,
        trade_fixture_id: str,
        trade_market: str,
        trade_selection: str,
        trade_entry_timestamp: float,
        trade_kickoff_timestamp: float,
    ) -> Optional[CLVCalculation]:
        """Calculate CLV for a paper trade using a closing observation.

        Returns None if:
        - Validation fails
        - Closing data is not genuine (when require_genuine=True)
        - Odds are invalid

        Args:
            trade_id: Paper trade identifier.
            entry_odds: Decimal odds at entry/prediction time.
            closing_observation: The closing odds observation.
            trade_fixture_id: Fixture ID from the trade.
            trade_market: Market from the trade.
            trade_selection: Selection from the trade.
            trade_entry_timestamp: When the trade was generated.
            trade_kickoff_timestamp: Fixture kickoff time.

        Returns:
            CLVCalculation or None if cannot be computed.
        """
        # Validate the closing observation
        validation = self._validator.validate(
            observation=closing_observation,
            trade_fixture_id=trade_fixture_id,
            trade_market=trade_market,
            trade_selection=trade_selection,
            trade_entry_timestamp=trade_entry_timestamp,
            trade_kickoff_timestamp=trade_kickoff_timestamp,
        )

        if not validation.valid:
            return None

        # Check genuine requirement
        if self._require_genuine and not closing_observation.is_genuine:
            return None

        # Validate inputs
        if entry_odds < 1.0 or closing_observation.decimal_odds < 1.0:
            return None

        # Calculate CLV
        closing_odds = closing_observation.decimal_odds
        entry_implied = 1.0 / entry_odds
        closing_implied = 1.0 / closing_odds

        if self._methodology == CLVMethodology.PRICE_BASED:
            clv = (entry_odds / closing_odds) - 1.0
        elif self._methodology == CLVMethodology.PROBABILITY_BASED:
            clv = closing_implied - entry_implied
        else:
            clv = (entry_odds / closing_odds) - 1.0  # Default to price-based

        return CLVCalculation(
            trade_id=trade_id,
            entry_odds=entry_odds,
            closing_odds=closing_odds,
            clv=clv,
            methodology=self._methodology,
            entry_implied_prob=entry_implied,
            closing_implied_prob=closing_implied,
            is_positive=clv > 0,
            is_genuine=closing_observation.is_genuine,
            closing_source=closing_observation.source,
            closing_bookmaker=closing_observation.bookmaker,
            status=validation.status,
        )

    def calculate_with_overround(
        self,
        trade_id: str,
        entry_odds: float,
        closing_over_odds: float,
        closing_under_odds: float,
        closing_observation: ClosingOddsObservation,
    ) -> Optional[CLVCalculation]:
        """Calculate overround-adjusted CLV for over/under markets.

        Uses both sides of the market to compute overround, then
        calculates fair closing probability.

        Args:
            trade_id: Paper trade ID.
            entry_odds: Entry decimal odds.
            closing_over_odds: Closing odds for OVER.
            closing_under_odds: Closing odds for UNDER.
            closing_observation: The validated observation.

        Returns:
            CLVCalculation with overround adjustment, or None.
        """
        if closing_over_odds < 1.0 or closing_under_odds < 1.0 or entry_odds < 1.0:
            return None

        if not closing_observation.is_genuine:
            return None

        # Compute overround
        over_implied = 1.0 / closing_over_odds
        under_implied = 1.0 / closing_under_odds
        overround = over_implied + under_implied  # > 1.0 means vig exists

        if overround <= 0:
            return None

        # Fair closing probability (remove vig)
        closing_odds = closing_observation.decimal_odds
        closing_implied = 1.0 / closing_odds
        fair_closing_prob = closing_implied / overround

        entry_implied = 1.0 / entry_odds
        clv = (entry_odds / closing_odds) - 1.0  # Still price-based

        return CLVCalculation(
            trade_id=trade_id,
            entry_odds=entry_odds,
            closing_odds=closing_odds,
            clv=clv,
            methodology=CLVMethodology.OVERROUND_ADJUSTED,
            entry_implied_prob=entry_implied,
            closing_implied_prob=fair_closing_prob,
            is_positive=clv > 0,
            is_genuine=closing_observation.is_genuine,
            closing_source=closing_observation.source,
            closing_bookmaker=closing_observation.bookmaker,
            overround=overround,
            status=closing_observation.status,
        )
