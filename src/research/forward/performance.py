"""Forward Performance Classification & Reporting.

Classifies forward (paper trading) performance separately from historical evidence.
NEVER silently combines historical and forward results.

Classifications:
    INSUFFICIENT_FORWARD_DATA — Too few settled trades for assessment
    EARLY_SIGNAL             — Small sample, directionally positive
    PROMISING                — Moderate sample, positive metrics
    STABLE                   — Large sample, consistent performance
    DEGRADING                — Performance declining vs historical
    FAILED_FORWARD_VALIDATION — Clearly negative forward performance

These classifications do NOT equal production approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.paper.clv import CLVSummary


class ForwardClassification(Enum):
    """Forward performance classification. NOT production approval."""
    INSUFFICIENT_FORWARD_DATA = "INSUFFICIENT_FORWARD_DATA"
    EARLY_SIGNAL = "EARLY_SIGNAL"
    PROMISING = "PROMISING"
    STABLE = "STABLE"
    DEGRADING = "DEGRADING"
    FAILED_FORWARD_VALIDATION = "FAILED_FORWARD_VALIDATION"


@dataclass(frozen=True)
class ForwardPerformanceReport:
    """Strategy-level forward performance report.

    Compares HISTORICAL EXPECTATION vs FORWARD RESULT explicitly.
    Includes sample-size warnings for small samples.
    """
    strategy_id: str
    market: str = ""

    # ═══ Counts ═══
    prediction_count: int = 0
    paper_trades: int = 0
    settled_trades: int = 0
    open_trades: int = 0

    # ═══ Performance ═══
    win_rate: Optional[float] = None
    average_odds: Optional[float] = None
    average_predicted_probability: Optional[float] = None
    average_market_probability: Optional[float] = None
    average_edge: Optional[float] = None

    # ═══ P&L ═══
    expected_profit: Optional[float] = None
    realized_profit: Optional[float] = None
    roi: Optional[float] = None
    yield_pct: Optional[float] = None
    max_drawdown: Optional[float] = None
    bankroll: Optional[float] = None

    # ═══ CLV ═══
    average_clv: Optional[float] = None
    median_clv: Optional[float] = None
    positive_clv_rate: Optional[float] = None

    # ═══ Calibration ═══
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None

    # ═══ Historical comparison ═══
    historical_expected_roi: Optional[float] = None
    forward_vs_historical_diff: Optional[float] = None

    # ═══ Classification ═══
    classification: ForwardClassification = ForwardClassification.INSUFFICIENT_FORWARD_DATA
    sample_size_warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "market": self.market,
            "classification": self.classification.value,
            "prediction_count": self.prediction_count,
            "paper_trades": self.paper_trades,
            "settled_trades": self.settled_trades,
            "open_trades": self.open_trades,
            "win_rate": self.win_rate,
            "average_odds": self.average_odds,
            "average_predicted_probability": self.average_predicted_probability,
            "average_market_probability": self.average_market_probability,
            "average_edge": self.average_edge,
            "expected_profit": self.expected_profit,
            "realized_profit": self.realized_profit,
            "roi": self.roi,
            "yield_pct": self.yield_pct,
            "max_drawdown": self.max_drawdown,
            "bankroll": self.bankroll,
            "average_clv": self.average_clv,
            "median_clv": self.median_clv,
            "positive_clv_rate": self.positive_clv_rate,
            "brier_score": self.brier_score,
            "historical_expected_roi": self.historical_expected_roi,
            "forward_vs_historical_diff": self.forward_vs_historical_diff,
            "sample_size_warning": self.sample_size_warning,
        }


def classify_forward_performance(
    settled_trades: int,
    roi: Optional[float],
    positive_clv_rate: Optional[float],
    win_rate: Optional[float],
    historical_roi: Optional[float] = None,
    min_trades_for_assessment: int = 20,
    min_trades_for_stable: int = 100,
) -> ForwardClassification:
    """Classify forward performance.

    Args:
        settled_trades: Number of settled paper trades.
        roi: Realized ROI.
        positive_clv_rate: Fraction of trades with positive CLV.
        win_rate: Win rate.
        historical_roi: Expected ROI from historical research.
        min_trades_for_assessment: Minimum trades for any classification.
        min_trades_for_stable: Minimum trades for STABLE classification.

    Returns:
        ForwardClassification.
    """
    if settled_trades < min_trades_for_assessment:
        return ForwardClassification.INSUFFICIENT_FORWARD_DATA

    if roi is None:
        return ForwardClassification.INSUFFICIENT_FORWARD_DATA

    # Check for degradation vs historical
    if historical_roi is not None and roi < (historical_roi * 0.3):
        return ForwardClassification.DEGRADING

    # Failed: significantly negative
    if roi < -0.15:
        return ForwardClassification.FAILED_FORWARD_VALIDATION

    # Stable: large sample, positive
    if settled_trades >= min_trades_for_stable and roi > 0:
        if positive_clv_rate and positive_clv_rate > 0.45:
            return ForwardClassification.STABLE
        return ForwardClassification.PROMISING

    # Promising: moderate sample, positive
    if roi > 0:
        return ForwardClassification.PROMISING if settled_trades >= 50 else ForwardClassification.EARLY_SIGNAL

    # Early signal: small positive or slightly negative
    if roi > -0.05:
        return ForwardClassification.EARLY_SIGNAL

    return ForwardClassification.FAILED_FORWARD_VALIDATION
