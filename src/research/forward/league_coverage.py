"""Multi-League Support & Market Readiness — coverage assessment for forward research.

Determines whether a league/market combination has sufficient data
for forward predictions and paper trading.

Does NOT assume every league has identical field coverage.
Missing coverage is explicit — never silently processed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MarketReadiness(Enum):
    """Market readiness for forward trading."""
    READY = "READY"                # All requirements met
    PARTIAL = "PARTIAL"            # Some data available but gaps exist
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # Not enough historical data
    UNAVAILABLE = "UNAVAILABLE"    # Market not supported for this league


@dataclass(frozen=True)
class LeagueCoverageReport:
    """Coverage report for a single league.

    Explicit about what IS and ISN'T available.
    """
    league_id: int
    league_name: str = ""
    season_id: int = 0

    # Fixture availability
    total_fixtures: int = 0
    upcoming_fixtures: int = 0
    completed_fixtures: int = 0

    # Historical data
    historical_matches: int = 0
    historical_date_range: tuple[int, int] = (0, 0)  # (earliest, latest)

    # Odds coverage
    odds_available: bool = False
    goals_odds_coverage: float = 0.0  # Fraction of matches with goals odds
    corners_odds_coverage: float = 0.0
    match_result_odds_coverage: float = 0.0

    # Feature coverage
    feature_coverage: dict[str, float] = field(default_factory=dict)
    missing_fields: tuple[str, ...] = ()

    # Markets
    supported_markets: tuple[str, ...] = ()

    # Quality
    data_quality_score: float = 0.0  # 0-1

    def to_dict(self) -> dict[str, Any]:
        return {
            "league_id": self.league_id,
            "league_name": self.league_name,
            "season_id": self.season_id,
            "total_fixtures": self.total_fixtures,
            "upcoming_fixtures": self.upcoming_fixtures,
            "completed_fixtures": self.completed_fixtures,
            "historical_matches": self.historical_matches,
            "odds_available": self.odds_available,
            "goals_odds_coverage": round(self.goals_odds_coverage, 3),
            "corners_odds_coverage": round(self.corners_odds_coverage, 3),
            "match_result_odds_coverage": round(self.match_result_odds_coverage, 3),
            "supported_markets": list(self.supported_markets),
            "missing_fields": list(self.missing_fields),
            "data_quality_score": round(self.data_quality_score, 3),
        }


@dataclass(frozen=True)
class MarketReadinessResult:
    """Readiness assessment for a specific market in a specific league."""
    league_id: int
    market: str
    readiness: MarketReadiness
    fixture_coverage: float = 0.0
    odds_coverage: float = 0.0
    feature_coverage: float = 0.0
    historical_sample: int = 0
    min_required_sample: int = 50
    settlement_supported: bool = True
    clv_available: bool = False  # FootyStats has no closing odds
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "league_id": self.league_id,
            "market": self.market,
            "readiness": self.readiness.value,
            "fixture_coverage": round(self.fixture_coverage, 3),
            "odds_coverage": round(self.odds_coverage, 3),
            "feature_coverage": round(self.feature_coverage, 3),
            "historical_sample": self.historical_sample,
            "min_required_sample": self.min_required_sample,
            "settlement_supported": self.settlement_supported,
            "clv_available": self.clv_available,
            "reasons": list(self.reasons),
        }


class MarketReadinessAssessor:
    """Assesses whether a market is ready for paper trading.

    Prevents paper trade generation for markets that fail readiness.
    """

    def __init__(
        self,
        min_historical_sample: int = 50,
        min_odds_coverage: float = 0.5,
        min_feature_coverage: float = 0.6,
    ) -> None:
        self._min_sample = min_historical_sample
        self._min_odds = min_odds_coverage
        self._min_features = min_feature_coverage

    def assess(
        self,
        league_id: int,
        market: str,
        historical_sample: int = 0,
        odds_coverage: float = 0.0,
        feature_coverage: float = 0.0,
        has_settlement_logic: bool = True,
        has_closing_odds: bool = False,
    ) -> MarketReadinessResult:
        """Assess market readiness for a league.

        Args:
            league_id: League identifier.
            market: Market type (e.g., "CORNERS_TOTAL").
            historical_sample: Number of historical matches with this market.
            odds_coverage: Fraction of matches with odds available.
            feature_coverage: Fraction of required features available.
            has_settlement_logic: Whether settlement is implemented.
            has_closing_odds: Whether closing odds source exists.

        Returns:
            MarketReadinessResult with assessment.
        """
        reasons: list[str] = []

        if historical_sample < self._min_sample:
            reasons.append(
                f"Insufficient history: {historical_sample} < {self._min_sample}"
            )

        if odds_coverage < self._min_odds:
            reasons.append(
                f"Low odds coverage: {odds_coverage:.1%} < {self._min_odds:.1%}"
            )

        if feature_coverage < self._min_features:
            reasons.append(
                f"Low feature coverage: {feature_coverage:.1%} < {self._min_features:.1%}"
            )

        if not has_settlement_logic:
            reasons.append("Settlement not supported for this market")

        # Determine readiness level
        if not reasons:
            readiness = MarketReadiness.READY
        elif len(reasons) == 1 and "closing" not in reasons[0].lower():
            readiness = MarketReadiness.PARTIAL
        elif historical_sample == 0:
            readiness = MarketReadiness.UNAVAILABLE
        else:
            readiness = MarketReadiness.INSUFFICIENT_DATA

        return MarketReadinessResult(
            league_id=league_id,
            market=market,
            readiness=readiness,
            fixture_coverage=1.0 if historical_sample > 0 else 0.0,
            odds_coverage=odds_coverage,
            feature_coverage=feature_coverage,
            historical_sample=historical_sample,
            min_required_sample=self._min_sample,
            settlement_supported=has_settlement_logic,
            clv_available=has_closing_odds,
            reasons=tuple(reasons),
        )


# Well-known league season IDs (configurable, not hardcoded)
KNOWN_LEAGUES: dict[str, dict[str, Any]] = {
    "EPL": {"name": "English Premier League", "country": "England"},
    "LA_LIGA": {"name": "La Liga", "country": "Spain"},
    "SERIE_A": {"name": "Serie A", "country": "Italy"},
    "BUNDESLIGA": {"name": "Bundesliga", "country": "Germany"},
    "LIGUE_1": {"name": "Ligue 1", "country": "France"},
}
