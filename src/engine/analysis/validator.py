"""Statistical validation and promotion gate for x-Metric strategies.

Runs hypothesis tests to determine if a strategy has genuine predictive
edge, enforcing minimum sample sizes and significance thresholds before
promoting to the leaderboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from scipy import stats

from src.engine.analysis.backtest import XBetRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValidationCriteria:
    """Thresholds for strategy promotion."""

    min_sample_size: int = 250
    max_p_value: float = 0.05
    min_roi_pct: float = 3.0


@dataclass(frozen=True, slots=True)
class ValidationVerdict:
    """Complete validation result for a strategy."""

    passed: bool
    p_value: float
    mean_profit: float
    roi_pct: float
    sample_size: int
    confidence_interval: Tuple[float, float]
    effect_size: float  # Cohen's d
    reason: str


class StatisticalValidator:
    """Validates strategy profitability using frequentist hypothesis testing.

    Applies three gates:
    1. Minimum sample size (N >= 250)
    2. Minimum ROI (>= 3%)
    3. Statistical significance (1-tailed t-test, p <= 0.05)
    """

    def __init__(self, criteria: ValidationCriteria | None = None) -> None:
        self.criteria = criteria or ValidationCriteria()

    def validate(self, bet_records: List[XBetRecord]) -> ValidationVerdict:
        """Run full validation pipeline on a set of bet records.

        Returns a ValidationVerdict with pass/fail decision and full stats.
        """
        # Filter out VOID bets
        settled = [b for b in bet_records if b.outcome != "VOID"]
        n = len(settled)

        # Gate 1: Sample size
        if n < self.criteria.min_sample_size:
            return ValidationVerdict(
                passed=False,
                p_value=1.0,
                mean_profit=0.0,
                roi_pct=0.0,
                sample_size=n,
                confidence_interval=(0.0, 0.0),
                effect_size=0.0,
                reason=(
                    f"Insufficient sample size: {n} < {self.criteria.min_sample_size} "
                    f"settled bets required"
                ),
            )

        profits = np.array([b.profit_loss for b in settled], dtype=np.float64)
        total_staked = sum(b.stake for b in settled)
        total_pl = float(np.sum(profits))
        mean_profit = float(np.mean(profits))
        roi_pct = (total_pl / total_staked * 100.0) if total_staked > 0 else 0.0

        # Gate 2: Minimum ROI
        if roi_pct < self.criteria.min_roi_pct:
            p_value, _ = self._t_test(profits)
            ci = self._confidence_interval(profits)
            effect = self._cohens_d(profits)
            return ValidationVerdict(
                passed=False,
                p_value=p_value,
                mean_profit=mean_profit,
                roi_pct=roi_pct,
                sample_size=n,
                confidence_interval=ci,
                effect_size=effect,
                reason=(
                    f"ROI too low: {roi_pct:.2f}% < {self.criteria.min_roi_pct}% minimum"
                ),
            )

        # Gate 3: Statistical significance
        p_value, t_stat = self._t_test(profits)
        ci = self._confidence_interval(profits)
        effect = self._cohens_d(profits)

        if p_value > self.criteria.max_p_value:
            return ValidationVerdict(
                passed=False,
                p_value=p_value,
                mean_profit=mean_profit,
                roi_pct=roi_pct,
                sample_size=n,
                confidence_interval=ci,
                effect_size=effect,
                reason=(
                    f"Not statistically significant: p={p_value:.4f} > "
                    f"{self.criteria.max_p_value} threshold"
                ),
            )

        # All gates passed
        verdict = ValidationVerdict(
            passed=True,
            p_value=p_value,
            mean_profit=mean_profit,
            roi_pct=roi_pct,
            sample_size=n,
            confidence_interval=ci,
            effect_size=effect,
            reason=(
                f"PROMOTED: ROI={roi_pct:.2f}%, p={p_value:.4f}, "
                f"N={n}, Cohen's d={effect:.3f}"
            ),
        )

        logger.info(
            "Strategy validated: %s (ROI=%.2f%%, p=%.4f, N=%d, d=%.3f)",
            verdict.reason,
            roi_pct,
            p_value,
            n,
            effect,
        )
        return verdict

    def _t_test(self, profits: np.ndarray) -> Tuple[float, float]:
        """1-sample 1-tailed t-test.

        H0: mean_profit <= 0
        H1: mean_profit > 0

        Returns (p_value, t_statistic).
        """
        if len(profits) < 2:
            return 1.0, 0.0

        # scipy ttest_1samp gives 2-tailed p-value
        t_stat, p_two_tailed = stats.ttest_1samp(profits, 0.0)

        # Convert to 1-tailed (right tail: H1 is mean > 0)
        if t_stat > 0:
            p_one_tailed = p_two_tailed / 2.0
        else:
            p_one_tailed = 1.0 - p_two_tailed / 2.0

        return float(p_one_tailed), float(t_stat)

    def _cohens_d(self, profits: np.ndarray) -> float:
        """Compute Cohen's d effect size (mean / std)."""
        if len(profits) < 2:
            return 0.0

        std = float(np.std(profits, ddof=1))
        if std == 0:
            return 0.0

        return float(np.mean(profits)) / std

    def _confidence_interval(
        self, profits: np.ndarray, alpha: float = 0.05
    ) -> Tuple[float, float]:
        """Compute confidence interval for mean profit.

        Returns (lower_bound, upper_bound) at (1-alpha) confidence level.
        """
        n = len(profits)
        if n < 2:
            return (0.0, 0.0)

        mean = float(np.mean(profits))
        se = float(np.std(profits, ddof=1)) / np.sqrt(n)
        t_crit = stats.t.ppf(1.0 - alpha / 2.0, df=n - 1)

        lower = mean - t_crit * se
        upper = mean + t_crit * se

        return (float(lower), float(upper))
