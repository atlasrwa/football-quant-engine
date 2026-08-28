"""Beat the Bookie metric calculations.

Translates complex quant statistics into high-impact metrics for retail
and crypto bettors: BTBR %, Vig-Adjusted Edge, and Confidence Index.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import numpy as np

from src.engine.backtest import XBetRecord
from src.engine.friction import MarketFrictionConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BookieMetrics:
    """Aggregate Beat the Bookie metrics."""

    btbr_pct: float  # Beat the Bookie Rate %
    vig_adjusted_edge_pct: float  # Expected ROI after vig deduction
    confidence_index: float  # 0-100 (from FDR p-value)
    total_signals: int
    signals_beating_close: int
    raw_edge_pct: float  # Pre-vig edge

    def summary(self) -> dict:
        """Serializable summary."""
        return {
            "btbr_pct": round(self.btbr_pct, 2),
            "vig_adjusted_edge_pct": round(self.vig_adjusted_edge_pct, 2),
            "confidence_index": round(self.confidence_index, 1),
            "total_signals": self.total_signals,
            "signals_beating_close": self.signals_beating_close,
            "raw_edge_pct": round(self.raw_edge_pct, 2),
        }


class BookieMetricsCalculator:
    """Computes Beat the Bookie metrics from bet records and signals.

    Three core metrics:
    1. BTBR %: fraction of signals beating the closing line
    2. Vig-Adjusted Edge %: ROI minus bookmaker margin
    3. Confidence Index: 100*(1 - p_adjusted) transformed to 0-100 scale
    """

    def __init__(self, friction_config: MarketFrictionConfig | None = None) -> None:
        self.friction = friction_config or MarketFrictionConfig()

    def compute(
        self,
        bet_records: List[XBetRecord],
        closing_odds: List[float] | None = None,
        fdr_p_value: float = 0.05,
        market: str = "match_odds",
    ) -> BookieMetrics:
        """Compute all Beat the Bookie metrics.

        Args:
            bet_records: List of settled bet records.
            closing_odds: Closing line odds for each bet (parallel list).
                          If None, uses bet odds as closing (BTBR=0%).
            fdr_p_value: FDR-adjusted p-value for confidence calculation.
            market: Market type for vig calculation.

        Returns:
            BookieMetrics with all three metrics.
        """
        if not bet_records:
            return BookieMetrics(
                btbr_pct=0.0,
                vig_adjusted_edge_pct=0.0,
                confidence_index=0.0,
                total_signals=0,
                signals_beating_close=0,
                raw_edge_pct=0.0,
            )

        # Extract entry odds
        entry_odds = [b.odds for b in bet_records]

        # BTBR
        if closing_odds and len(closing_odds) == len(entry_odds):
            btbr = self.compute_btbr(entry_odds, closing_odds)
            signals_beating = sum(
                1 for e, c in zip(entry_odds, closing_odds) if e > c
            )
        else:
            btbr = 0.0
            signals_beating = 0

        # Raw ROI
        settled = [b for b in bet_records if b.outcome != "VOID"]
        if settled:
            total_staked = sum(b.stake for b in settled)
            total_pl = sum(b.profit_loss for b in settled)
            raw_roi = (total_pl / total_staked * 100.0) if total_staked > 0 else 0.0
        else:
            raw_roi = 0.0

        # Vig-adjusted edge
        vig_edge = self.compute_vig_adjusted_edge(raw_roi, market)

        # Confidence index
        confidence = self.compute_confidence_index(fdr_p_value)

        metrics = BookieMetrics(
            btbr_pct=btbr,
            vig_adjusted_edge_pct=vig_edge,
            confidence_index=confidence,
            total_signals=len(bet_records),
            signals_beating_close=signals_beating,
            raw_edge_pct=raw_roi,
        )

        logger.info(
            "BookieMetrics: BTBR=%.1f%%, VigEdge=%.2f%%, Confidence=%.0f",
            btbr, vig_edge, confidence,
        )
        return metrics

    def compute_btbr(
        self, entry_odds: List[float], closing_odds: List[float]
    ) -> float:
        """Compute Beat the Bookie Rate.

        BTBR = (signals where entry_odds > closing_odds) / total_signals * 100

        Args:
            entry_odds: Odds at signal generation time.
            closing_odds: Odds at market close.

        Returns:
            BTBR as percentage (0-100).
        """
        if not entry_odds or not closing_odds:
            return 0.0

        n = min(len(entry_odds), len(closing_odds))
        beating = sum(1 for i in range(n) if entry_odds[i] > closing_odds[i])
        return (beating / n) * 100.0

    def compute_vig_adjusted_edge(self, roi_pct: float, market: str) -> float:
        """Compute vig-adjusted edge percentage.

        vig_edge = roi - (margin * 100)

        This represents the true edge after accounting for the bookmaker's
        built-in margin on the specific market.

        Args:
            roi_pct: Raw ROI percentage.
            market: Market type for margin lookup.

        Returns:
            Vig-adjusted edge as percentage.
        """
        margin_pct = self.friction.get_margin(market) * 100.0
        return roi_pct - margin_pct

    def compute_confidence_index(self, fdr_p_value: float) -> float:
        """Compute confidence index from FDR-adjusted p-value.

        confidence = 100 * (1 - p_adjusted), clamped to [0, 100].

        Args:
            fdr_p_value: FDR-adjusted p-value.

        Returns:
            Confidence index (0-100).
        """
        confidence = 100.0 * (1.0 - fdr_p_value)
        return max(0.0, min(100.0, confidence))
