"""Quantitative performance metrics for backtest evaluation.

Computes Net ROI %, Win Rate %, Max Drawdown %, Sharpe Ratio, and p-value.
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Optional

import numpy as np
from scipy import stats

from src.models.results import BetRecord

logger = logging.getLogger(__name__)


class MetricsSummary(NamedTuple):
    """Container for all computed backtest metrics."""

    net_roi_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    p_value: float
    total_bets: int
    total_staked: float
    total_profit: float


class MetricsAggregator:
    """Computes aggregate performance metrics from bet records.

    Metrics:
    - Net ROI %: (total_profit / total_staked) * 100
    - Win Rate %: (winning_bets / total_bets) * 100
    - Max Drawdown %: Peak-to-trough decline in cumulative P&L as % of peak
    - Sharpe Ratio: mean(returns) / std(returns) * sqrt(n) [annualized proxy]
    - p-value: One-sample t-test of per-bet returns vs null mean of zero
    """

    def compute(self, records: List[BetRecord]) -> MetricsSummary:
        """Compute all metrics from a list of bet records.

        Args:
            records: List of BetRecord instances.

        Returns:
            MetricsSummary with all computed values.
        """
        if not records:
            return MetricsSummary(
                net_roi_pct=0.0,
                win_rate_pct=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                p_value=1.0,
                total_bets=0,
                total_staked=0.0,
                total_profit=0.0,
            )

        total_staked = sum(r.stake for r in records)
        total_profit = sum(r.profit_loss for r in records)
        wins = sum(1 for r in records if r.is_win)
        total_bets = len(records)

        net_roi_pct = (total_profit / total_staked) * 100.0 if total_staked > 0 else 0.0
        win_rate_pct = (wins / total_bets) * 100.0

        # Per-bet returns (profit_loss / stake)
        returns = [r.profit_loss / r.stake for r in records]

        max_drawdown_pct = self._compute_max_drawdown(records)
        sharpe_ratio = self._compute_sharpe(returns)
        p_value = self._compute_pvalue(returns)

        summary = MetricsSummary(
            net_roi_pct=round(net_roi_pct, 4),
            win_rate_pct=round(win_rate_pct, 2),
            max_drawdown_pct=round(max_drawdown_pct, 4),
            sharpe_ratio=round(sharpe_ratio, 4),
            p_value=round(p_value, 6),
            total_bets=total_bets,
            total_staked=round(total_staked, 6),
            total_profit=round(total_profit, 6),
        )

        logger.info(
            "Metrics: ROI=%.2f%%, WR=%.1f%%, MDD=%.2f%%, Sharpe=%.2f, p=%.4f (%d bets)",
            summary.net_roi_pct, summary.win_rate_pct,
            summary.max_drawdown_pct, summary.sharpe_ratio,
            summary.p_value, summary.total_bets,
        )
        return summary

    @staticmethod
    def _compute_max_drawdown(records: List[BetRecord]) -> float:
        """Compute maximum drawdown as percentage of peak cumulative P&L.

        Drawdown is measured from the peak equity to the lowest trough.
        Expressed as a positive percentage of the peak.

        Args:
            records: List of BetRecord instances.

        Returns:
            Max drawdown percentage (0.0 if no drawdown or no bets).
        """
        if not records:
            return 0.0

        # Build cumulative P&L curve (starting from initial bankroll of total_staked)
        cumulative_pnl: List[float] = []
        running = 0.0
        for r in records:
            running += r.profit_loss
            cumulative_pnl.append(running)

        # Use total staked as the reference base for drawdown percentage
        total_staked = sum(r.stake for r in records)
        if total_staked == 0:
            return 0.0

        # Find max drawdown from peak
        peak = 0.0
        max_dd = 0.0
        for pnl in cumulative_pnl:
            if pnl > peak:
                peak = pnl
            drawdown = peak - pnl
            if drawdown > max_dd:
                max_dd = drawdown

        # Express as percentage of total staked
        return (max_dd / total_staked) * 100.0

    @staticmethod
    def _compute_sharpe(returns: List[float]) -> float:
        """Compute Sharpe ratio of per-bet returns.

        Uses mean/std with no risk-free rate adjustment (simplified).

        Args:
            returns: List of per-bet return ratios.

        Returns:
            Sharpe ratio. Returns 0.0 if std is zero or insufficient data.
        """
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=np.float64)
        std = float(np.std(arr, ddof=1))
        if std == 0.0:
            return 0.0
        mean = float(np.mean(arr))
        return mean / std

    @staticmethod
    def _compute_pvalue(returns: List[float]) -> float:
        """Compute p-value via one-sample t-test against zero mean.

        Tests whether the mean per-bet return is significantly different
        from zero (null hypothesis: no edge).

        Args:
            returns: List of per-bet return ratios.

        Returns:
            Two-tailed p-value. Returns 1.0 if insufficient data.
        """
        if len(returns) < 2:
            return 1.0
        _, p_value = stats.ttest_1samp(returns, 0.0)
        return float(p_value)
