"""Research market abstraction.

Defines markets as economic targets rather than classification targets.
Each market specifies what is being predicted, how it settles, and how
to compare model probability against market price.

Supports:
- Over/Under total markets (goals, corners, cards, offsides)
- Team-specific over/under markets (team goals, team corners, team cards)
- Both Teams To Score (BTTS)
- 1X2 (match result)

Each market is a self-contained definition that knows:
- what it predicts (target variable)
- how it settles (outcome resolution)
- what data it requires (required fields)
- what models it's compatible with
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MarketType(Enum):
    """Supported research market types."""

    GOALS_TOTAL = "GOALS_TOTAL"
    CORNERS_TOTAL = "CORNERS_TOTAL"
    CARDS_TOTAL = "CARDS_TOTAL"
    OFFSIDES_TOTAL = "OFFSIDES_TOTAL"
    HOME_GOALS = "HOME_GOALS"
    AWAY_GOALS = "AWAY_GOALS"
    HOME_CORNERS = "HOME_CORNERS"
    AWAY_CORNERS = "AWAY_CORNERS"
    HOME_CARDS = "HOME_CARDS"
    AWAY_CARDS = "AWAY_CARDS"
    BTTS = "BTTS"
    MATCH_RESULT_1X2 = "MATCH_RESULT_1X2"


class MarketDirection(Enum):
    """Betting direction for over/under markets."""

    OVER = "OVER"
    UNDER = "UNDER"


class MarketOutcome(Enum):
    """Generalized market outcome for multi-way markets."""

    OVER = "OVER"
    UNDER = "UNDER"
    YES = "YES"
    NO = "NO"
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    PUSH = "PUSH"


class MarketCategory(Enum):
    """Category of market structure."""

    OVER_UNDER = "OVER_UNDER"      # Two-way: over or under a line
    YES_NO = "YES_NO"              # Two-way: yes or no (BTTS)
    THREE_WAY = "THREE_WAY"        # Three-way: home/draw/away (1X2)


class ProbabilityModelType(Enum):
    """Types of probability models compatible with a market."""

    HISTORICAL_FREQUENCY = "HISTORICAL_FREQUENCY"
    LOGISTIC_REGRESSION = "LOGISTIC_REGRESSION"
    POISSON = "POISSON"
    ALL = "ALL"


@dataclass(frozen=True, slots=True)
class ResearchMarket:
    """A betting market definition for research.

    Attributes:
        market_type: The market category.
        target_field: Field in match data containing the actual outcome.
        line: The market line (e.g., 9.5 for corners O/U 9.5). None for non-line markets.
        odds_over_field: Field containing over/yes/home odds.
        odds_under_field: Field containing under/no/draw odds.
        category: The structural category (OVER_UNDER, YES_NO, THREE_WAY).
        required_fields: Fields that must be present in match data for settlement.
        compatible_models: Probability model types that can estimate this market.
        description: Human-readable description of the market.
        odds_third_field: For three-way markets, the third odds field (e.g., away odds).
    """

    market_type: MarketType
    target_field: str
    line: Optional[float]
    odds_over_field: str
    odds_under_field: str
    category: MarketCategory = MarketCategory.OVER_UNDER
    required_fields: tuple[str, ...] = ()
    compatible_models: tuple[ProbabilityModelType, ...] = (ProbabilityModelType.ALL,)
    description: str = ""
    odds_third_field: Optional[str] = None

    @property
    def market_id(self) -> str:
        """Deterministic identifier for this market definition."""
        canonical = json.dumps({
            "market_type": self.market_type.value,
            "line": self.line,
            "target_field": self.target_field,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def is_over_under(self) -> bool:
        """Whether this is a standard over/under market."""
        return self.category == MarketCategory.OVER_UNDER

    @property
    def is_yes_no(self) -> bool:
        """Whether this is a yes/no market (e.g., BTTS)."""
        return self.category == MarketCategory.YES_NO

    @property
    def is_three_way(self) -> bool:
        """Whether this is a three-way market (e.g., 1X2)."""
        return self.category == MarketCategory.THREE_WAY

    def resolve_outcome(self, actual_value: float) -> Optional[MarketDirection]:
        """Determine whether OVER or UNDER won (for over/under markets).

        Returns None for PUSH (actual == line).
        For non-over/under markets, use resolve_outcome_general().
        """
        if self.line is None:
            return None
        if actual_value > self.line:
            return MarketDirection.OVER
        elif actual_value < self.line:
            return MarketDirection.UNDER
        else:
            return None  # PUSH

    def resolve_outcome_general(self, match_data: dict[str, Any]) -> Optional[MarketOutcome]:
        """Resolve outcome for any market type.

        Args:
            match_data: Dictionary of match fields.

        Returns:
            MarketOutcome or None if data insufficient/push.
        """
        if self.category == MarketCategory.OVER_UNDER:
            target = match_data.get(self.target_field)
            if target is None or self.line is None:
                return None
            if target > self.line:
                return MarketOutcome.OVER
            elif target < self.line:
                return MarketOutcome.UNDER
            else:
                return MarketOutcome.PUSH

        elif self.category == MarketCategory.YES_NO:
            # BTTS: both teams scored at least 1
            home_goals = match_data.get("home_goals")
            away_goals = match_data.get("away_goals")
            if home_goals is None or away_goals is None:
                return None
            if home_goals >= 1 and away_goals >= 1:
                return MarketOutcome.YES
            else:
                return MarketOutcome.NO

        elif self.category == MarketCategory.THREE_WAY:
            # 1X2: home win, draw, away win
            home_goals = match_data.get("home_goals")
            away_goals = match_data.get("away_goals")
            if home_goals is None or away_goals is None:
                return None
            if home_goals > away_goals:
                return MarketOutcome.HOME
            elif home_goals == away_goals:
                return MarketOutcome.DRAW
            else:
                return MarketOutcome.AWAY

        return None

    def get_outcome_count(self) -> int:
        """Number of possible outcomes for this market."""
        if self.category == MarketCategory.THREE_WAY:
            return 3
        return 2

    def implied_probability(self, odds: float) -> float:
        """Convert decimal odds to implied probability.

        Does NOT strip margin — returns raw implied probability.
        """
        if odds <= 1.0:
            return 1.0
        return 1.0 / odds

    def fair_probability(self, over_odds: float, under_odds: float) -> tuple[float, float]:
        """Strip bookmaker margin to get fair probabilities (two-way markets).

        Uses multiplicative margin removal.

        Returns:
            (fair_over_probability, fair_under_probability) summing to 1.0
        """
        raw_over = 1.0 / over_odds if over_odds > 1.0 else 0.5
        raw_under = 1.0 / under_odds if under_odds > 1.0 else 0.5
        total = raw_over + raw_under
        if total == 0:
            return 0.5, 0.5
        return raw_over / total, raw_under / total

    def fair_probability_three_way(
        self, home_odds: float, draw_odds: float, away_odds: float
    ) -> tuple[float, float, float]:
        """Strip bookmaker margin for three-way markets.

        Returns:
            (fair_home, fair_draw, fair_away) summing to 1.0
        """
        raw_home = 1.0 / home_odds if home_odds > 1.0 else 0.33
        raw_draw = 1.0 / draw_odds if draw_odds > 1.0 else 0.33
        raw_away = 1.0 / away_odds if away_odds > 1.0 else 0.33
        total = raw_home + raw_draw + raw_away
        if total == 0:
            return 1 / 3, 1 / 3, 1 / 3
        return raw_home / total, raw_draw / total, raw_away / total

    def validate_match_data(self, match_data: dict[str, Any]) -> bool:
        """Check whether match data has all required fields for settlement.

        Args:
            match_data: Dictionary of match fields.

        Returns:
            True if all required fields are present and non-None.
        """
        for field_name in self.required_fields:
            if match_data.get(field_name) is None:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize market definition for storage/provenance."""
        return {
            "market_type": self.market_type.value,
            "target_field": self.target_field,
            "line": self.line,
            "category": self.category.value,
            "market_id": self.market_id,
            "description": self.description,
        }


# ═══════════════════════════════════════════════════════════════
# SETTLEMENT ADAPTER INTERFACE
# ═══════════════════════════════════════════════════════════════


class SettlementAdapter(ABC):
    """Interface for resolving market outcomes from match data.

    Adapts the frozen settlement architecture to research markets.
    Implementations bridge to the existing SettlementFactory without
    modifying it.
    """

    @abstractmethod
    def settle(
        self, market: ResearchMarket, match_data: dict[str, Any]
    ) -> Optional[MarketOutcome]:
        """Settle a market against match data.

        Args:
            market: The market to settle.
            match_data: Full match data dictionary.

        Returns:
            MarketOutcome or None if settlement impossible.
        """
        ...

    @abstractmethod
    def can_settle(self, market: ResearchMarket, match_data: dict[str, Any]) -> bool:
        """Check if this adapter can settle the given market with available data."""
        ...


class DefaultSettlementAdapter(SettlementAdapter):
    """Default settlement adapter using market.resolve_outcome_general().

    This works for all markets where the target field is directly available
    in match data. It does NOT depend on the frozen SettlementFactory.
    """

    def settle(
        self, market: ResearchMarket, match_data: dict[str, Any]
    ) -> Optional[MarketOutcome]:
        """Settle using the market's own resolution logic."""
        return market.resolve_outcome_general(match_data)

    def can_settle(self, market: ResearchMarket, match_data: dict[str, Any]) -> bool:
        """Check all required fields are present."""
        return market.validate_match_data(match_data)


# ═══════════════════════════════════════════════════════════════
# MARKET REGISTRY
# ═══════════════════════════════════════════════════════════════


class MarketRegistry:
    """Registry of available research markets.

    Provides extensible market lookup and validation.
    Markets are registered once and looked up by type.
    """

    def __init__(self) -> None:
        self._markets: dict[MarketType, ResearchMarket] = {}
        self._settlement_adapters: dict[MarketType, SettlementAdapter] = {}
        self._default_adapter = DefaultSettlementAdapter()

    def register(
        self,
        market: ResearchMarket,
        adapter: Optional[SettlementAdapter] = None,
    ) -> None:
        """Register a market definition.

        Args:
            market: The market definition to register.
            adapter: Optional custom settlement adapter (uses default if None).
        """
        self._markets[market.market_type] = market
        if adapter is not None:
            self._settlement_adapters[market.market_type] = adapter

    def get(self, market_type: MarketType) -> Optional[ResearchMarket]:
        """Look up a registered market by type."""
        return self._markets.get(market_type)

    def get_settlement_adapter(self, market_type: MarketType) -> SettlementAdapter:
        """Get the settlement adapter for a market type."""
        return self._settlement_adapters.get(market_type, self._default_adapter)

    def settle(
        self, market_type: MarketType, match_data: dict[str, Any]
    ) -> Optional[MarketOutcome]:
        """Settle a market using the registered adapter.

        Args:
            market_type: The market to settle.
            match_data: Full match data dictionary.

        Returns:
            MarketOutcome or None.
        """
        market = self.get(market_type)
        if market is None:
            return None
        adapter = self.get_settlement_adapter(market_type)
        return adapter.settle(market, match_data)

    @property
    def all_markets(self) -> list[ResearchMarket]:
        """All registered markets."""
        return list(self._markets.values())

    @property
    def market_types(self) -> list[MarketType]:
        """All registered market types."""
        return list(self._markets.keys())

    def get_by_category(self, category: MarketCategory) -> list[ResearchMarket]:
        """Get all markets of a given category."""
        return [m for m in self._markets.values() if m.category == category]

    def get_compatible_with_model(
        self, model_type: ProbabilityModelType
    ) -> list[ResearchMarket]:
        """Get markets compatible with a given model type."""
        result = []
        for market in self._markets.values():
            if ProbabilityModelType.ALL in market.compatible_models:
                result.append(market)
            elif model_type in market.compatible_models:
                result.append(market)
        return result


# ═══════════════════════════════════════════════════════════════
# DEFAULT MARKET DEFINITIONS
# ═══════════════════════════════════════════════════════════════

GOALS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.GOALS_TOTAL,
    target_field="total_goals",
    line=2.5,
    odds_over_field="odds_over_goals",
    odds_under_field="odds_under_goals",
    category=MarketCategory.OVER_UNDER,
    required_fields=("total_goals",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Total goals over/under 2.5",
)

CORNERS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.CORNERS_TOTAL,
    target_field="total_corners",
    line=9.5,
    odds_over_field="odds_over_corners",
    odds_under_field="odds_under_corners",
    category=MarketCategory.OVER_UNDER,
    required_fields=("total_corners",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Total corners over/under 9.5",
)

CARDS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.CARDS_TOTAL,
    target_field="total_cards",
    line=3.5,
    odds_over_field="odds_over_cards",
    odds_under_field="odds_under_cards",
    category=MarketCategory.OVER_UNDER,
    required_fields=("total_cards",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Total cards over/under 3.5",
)

OFFSIDES_OVER_UNDER = ResearchMarket(
    market_type=MarketType.OFFSIDES_TOTAL,
    target_field="total_offsides",
    line=4.5,
    odds_over_field="odds_over_offsides",
    odds_under_field="odds_under_offsides",
    category=MarketCategory.OVER_UNDER,
    required_fields=("total_offsides",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Total offsides over/under 4.5",
)

HOME_GOALS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.HOME_GOALS,
    target_field="home_goals",
    line=1.5,
    odds_over_field="odds_home_goals_over",
    odds_under_field="odds_home_goals_under",
    category=MarketCategory.OVER_UNDER,
    required_fields=("home_goals",),
    compatible_models=(
        ProbabilityModelType.POISSON,
        ProbabilityModelType.LOGISTIC_REGRESSION,
        ProbabilityModelType.HISTORICAL_FREQUENCY,
    ),
    description="Home team goals over/under 1.5",
)

AWAY_GOALS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.AWAY_GOALS,
    target_field="away_goals",
    line=1.5,
    odds_over_field="odds_away_goals_over",
    odds_under_field="odds_away_goals_under",
    category=MarketCategory.OVER_UNDER,
    required_fields=("away_goals",),
    compatible_models=(
        ProbabilityModelType.POISSON,
        ProbabilityModelType.LOGISTIC_REGRESSION,
        ProbabilityModelType.HISTORICAL_FREQUENCY,
    ),
    description="Away team goals over/under 1.5",
)

HOME_CORNERS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.HOME_CORNERS,
    target_field="corners_home",
    line=4.5,
    odds_over_field="odds_home_corners_over",
    odds_under_field="odds_home_corners_under",
    category=MarketCategory.OVER_UNDER,
    required_fields=("corners_home",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Home team corners over/under 4.5",
)

AWAY_CORNERS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.AWAY_CORNERS,
    target_field="corners_away",
    line=4.5,
    odds_over_field="odds_away_corners_over",
    odds_under_field="odds_away_corners_under",
    category=MarketCategory.OVER_UNDER,
    required_fields=("corners_away",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Away team corners over/under 4.5",
)

HOME_CARDS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.HOME_CARDS,
    target_field="yellow_cards_home",
    line=1.5,
    odds_over_field="odds_home_cards_over",
    odds_under_field="odds_home_cards_under",
    category=MarketCategory.OVER_UNDER,
    required_fields=("yellow_cards_home",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Home team cards over/under 1.5",
)

AWAY_CARDS_OVER_UNDER = ResearchMarket(
    market_type=MarketType.AWAY_CARDS,
    target_field="yellow_cards_away",
    line=1.5,
    odds_over_field="odds_away_cards_over",
    odds_under_field="odds_away_cards_under",
    category=MarketCategory.OVER_UNDER,
    required_fields=("yellow_cards_away",),
    compatible_models=(ProbabilityModelType.ALL,),
    description="Away team cards over/under 1.5",
)

BTTS_MARKET = ResearchMarket(
    market_type=MarketType.BTTS,
    target_field="btts",  # Computed: home_goals >= 1 and away_goals >= 1
    line=None,
    odds_over_field="odds_btts_yes",
    odds_under_field="odds_btts_no",
    category=MarketCategory.YES_NO,
    required_fields=("home_goals", "away_goals"),
    compatible_models=(
        ProbabilityModelType.LOGISTIC_REGRESSION,
        ProbabilityModelType.HISTORICAL_FREQUENCY,
    ),
    description="Both Teams To Score",
)

MATCH_RESULT_1X2 = ResearchMarket(
    market_type=MarketType.MATCH_RESULT_1X2,
    target_field="match_result",  # Computed: HOME/DRAW/AWAY
    line=None,
    odds_over_field="odds_home_win",
    odds_under_field="odds_draw",
    odds_third_field="odds_away_win",
    category=MarketCategory.THREE_WAY,
    required_fields=("home_goals", "away_goals"),
    compatible_models=(
        ProbabilityModelType.LOGISTIC_REGRESSION,
        ProbabilityModelType.HISTORICAL_FREQUENCY,
    ),
    description="Match Result 1X2 (Home/Draw/Away)",
)

# Original 4 markets (backward compatible)
ALL_MARKETS = [GOALS_OVER_UNDER, CORNERS_OVER_UNDER, CARDS_OVER_UNDER, OFFSIDES_OVER_UNDER]

# Extended market list including team-specific and new types
ALL_RESEARCH_MARKETS = [
    GOALS_OVER_UNDER,
    CORNERS_OVER_UNDER,
    CARDS_OVER_UNDER,
    OFFSIDES_OVER_UNDER,
    HOME_GOALS_OVER_UNDER,
    AWAY_GOALS_OVER_UNDER,
    HOME_CORNERS_OVER_UNDER,
    AWAY_CORNERS_OVER_UNDER,
    HOME_CARDS_OVER_UNDER,
    AWAY_CARDS_OVER_UNDER,
    BTTS_MARKET,
    MATCH_RESULT_1X2,
]


def create_default_registry() -> MarketRegistry:
    """Create a MarketRegistry pre-loaded with all research markets.

    Returns:
        MarketRegistry with all defined markets registered.
    """
    registry = MarketRegistry()
    for market in ALL_RESEARCH_MARKETS:
        registry.register(market)
    return registry
