"""Closing Line Value (CLV) — measures prediction quality vs market efficiency.

CLV Methodology (this implementation uses IMPLIED PROBABILITY CLV):

    CLV = (closing_implied_probability - prediction_implied_probability) / prediction_implied_probability

    Or equivalently in odds terms:
    CLV = (prediction_odds / closing_odds) - 1

    Positive CLV: we got better odds than the closing line (good)
    Negative CLV: we got worse odds than the closing line (bad)
    Zero CLV: we got exactly the closing line

Why implied probability CLV:
    - Directly comparable across different odds levels
    - Industry-standard measure of sharp vs recreational
    - Does not require knowing the vig structure
    - Works consistently across markets

CLV is calculated ONLY after closing odds become available.
CLV must NEVER modify:
    - prediction probability
    - prediction odds
    - EV at prediction time
    - paper stake
    - paper trade identity

CLV is a POST-HOC analysis metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CLVResult:
    """Result of a CLV calculation.

    Immutable. Does not modify the original trade.
    """
    trade_id: str
    prediction_odds: float
    closing_odds: float
    clv: float  # (prediction_odds / closing_odds) - 1
    prediction_implied_prob: float  # 1 / prediction_odds
    closing_implied_prob: float  # 1 / closing_odds
    is_positive: bool  # Did we beat the closing line?

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "prediction_odds": self.prediction_odds,
            "closing_odds": self.closing_odds,
            "clv": round(self.clv, 6),
            "prediction_implied_prob": round(self.prediction_implied_prob, 6),
            "closing_implied_prob": round(self.closing_implied_prob, 6),
            "is_positive": self.is_positive,
        }


def compute_clv(
    trade_id: str,
    prediction_odds: float,
    closing_odds: float,
) -> Optional[CLVResult]:
    """Compute Closing Line Value for a trade.

    CLV = (prediction_odds / closing_odds) - 1

    Positive CLV means we got better odds than closing (beat the market).

    Args:
        trade_id: Trade identifier.
        prediction_odds: Decimal odds at prediction time.
        closing_odds: Decimal odds at/near kickoff.

    Returns:
        CLVResult or None if inputs are invalid.
    """
    if prediction_odds is None or closing_odds is None:
        return None

    if prediction_odds < 1.0 or closing_odds < 1.0:
        return None

    if closing_odds == 0:
        return None

    clv = (prediction_odds / closing_odds) - 1.0
    pred_implied = 1.0 / prediction_odds
    closing_implied = 1.0 / closing_odds

    return CLVResult(
        trade_id=trade_id,
        prediction_odds=prediction_odds,
        closing_odds=closing_odds,
        clv=clv,
        prediction_implied_prob=pred_implied,
        closing_implied_prob=closing_implied,
        is_positive=clv > 0,
    )


@dataclass
class CLVSummary:
    """Aggregate CLV statistics for a strategy or portfolio."""
    total_trades: int = 0
    trades_with_clv: int = 0
    positive_clv_count: int = 0
    average_clv: float = 0.0
    median_clv: float = 0.0
    positive_clv_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "trades_with_clv": self.trades_with_clv,
            "positive_clv_count": self.positive_clv_count,
            "average_clv": round(self.average_clv, 6),
            "median_clv": round(self.median_clv, 6),
            "positive_clv_rate": round(self.positive_clv_rate, 4),
        }


def compute_clv_summary(clv_results: list[CLVResult]) -> CLVSummary:
    """Compute aggregate CLV statistics.

    Args:
        clv_results: List of individual CLV calculations.

    Returns:
        CLVSummary with aggregate metrics.
    """
    if not clv_results:
        return CLVSummary()

    clvs = [r.clv for r in clv_results]
    positive_count = sum(1 for c in clvs if c > 0)

    # Median
    sorted_clvs = sorted(clvs)
    n = len(sorted_clvs)
    if n % 2 == 0:
        median = (sorted_clvs[n // 2 - 1] + sorted_clvs[n // 2]) / 2
    else:
        median = sorted_clvs[n // 2]

    return CLVSummary(
        total_trades=len(clv_results),
        trades_with_clv=len(clv_results),
        positive_clv_count=positive_count,
        average_clv=sum(clvs) / len(clvs),
        median_clv=median,
        positive_clv_rate=positive_count / len(clvs),
    )
