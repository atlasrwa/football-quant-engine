"""Metric screening on the discovery set.

Scores each candidate metric by predictive value across a range of targets.
A metric that improves prediction across several targets is more valuable.

Targets (the measuring instruments, not the product):
- Corners (multiple lines: 7.5, 8.5, 9.5, 10.5, 11.5)
- Cards (multiple lines: 2.5, 3.5, 4.5)
- Goals (over 2.5)
- BTTS (both teams to score)
- Clean sheet
- Shots on target (over 4.5, over 5.5 per side)

Note on correlated lines: corners 7.5/8.5/9.5/10.5/11.5 are correlated
(a match with 11 corners is over on all of them). They are NOT counted
as independent tests. We use the Bonferroni-adjusted family across lines
within a target, then BH across candidates.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from scipy import stats as sp_stats

from src.discovery.generator import CandidateMetric, compute_metric_value

logger = logging.getLogger(__name__)


@dataclass
class TargetResult:
    """Performance of a metric on a single prediction target."""
    target: str
    line: Optional[float]
    n_qualifying: int
    hit_rate_with_metric: float
    naive_rate: float
    vs_naive_pct: float
    p_value: float
    effect_size: float  # Cohen's h
    positive: bool


@dataclass
class ScreeningResult:
    """Full screening result for one candidate metric."""
    metric_id: str
    metric_name: str
    targets_tested: int
    targets_positive: int
    breadth_score: float        # Fraction of targets where metric adds value
    best_vs_naive_pct: float
    mean_vs_naive_pct: float
    min_p_value: float
    target_results: list[TargetResult]
    overall_p_value: float      # Combined (Fisher's method across targets)
    passed_screen: bool         # Minimum bar to proceed to FDR


# Prediction targets — each (name, line, outcome_fn)
# The line variants within a target are CORRELATED, not independent
TARGET_GROUPS = {
    "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
    "cards": [2.5, 3.5, 4.5],
    "goals": [2.5],
    "btts": [None],
    "clean_sheet": [None],
}


def compute_outcome(match: dict, target: str, line: Optional[float]) -> Optional[float]:
    """Compute outcome for a match and target. Returns 1.0 (over/yes) or 0.0."""
    if target == "corners":
        a = match.get("team_a_corners", -1)
        b = match.get("team_b_corners", -1)
        if a < 0 or b < 0:
            return None
        return 1.0 if (a + b) > line else 0.0
    elif target == "cards":
        yc = (match.get("team_a_yellow_cards", -1) or 0) + (match.get("team_b_yellow_cards", -1) or 0)
        rc = (match.get("team_a_red_cards", -1) or 0) + (match.get("team_b_red_cards", -1) or 0)
        if match.get("team_a_yellow_cards", -1) < 0:
            return None
        return 1.0 if (yc + rc) > line else 0.0
    elif target == "goals":
        total = match.get("overallGoalCount", -1)
        if total < 0:
            return None
        return 1.0 if total > line else 0.0
    elif target == "btts":
        hg = match.get("homeGoalCount", -1)
        ag = match.get("awayGoalCount", -1)
        if hg < 0 or ag < 0:
            return None
        return 1.0 if (hg > 0 and ag > 0) else 0.0
    elif target == "clean_sheet":
        hg = match.get("homeGoalCount", -1)
        ag = match.get("awayGoalCount", -1)
        if hg < 0 or ag < 0:
            return None
        return 1.0 if (hg == 0 or ag == 0) else 0.0
    return None


class MetricScreener:
    """Screens candidate metrics for predictive value.

    For each metric, computes its rolling value for each match in the
    discovery set, then tests whether matches where the metric is high
    (above median) have different outcome rates than matches where it's low.

    This is a simple split test — "does knowing this metric's value help
    predict the outcome?" — applied across all targets.
    """

    def __init__(self, discovery_matches: list[dict[str, Any]]) -> None:
        """Initialize with discovery set matches (sorted chronologically).

        Args:
            discovery_matches: Completed matches from the discovery set.
                Must be sorted by date_unix within each league.
        """
        self._matches = sorted(discovery_matches, key=lambda m: m.get("date_unix", 0))
        self._n = len(self._matches)
        logger.info("Screener initialized with %d discovery matches", self._n)

    def screen(self, metric: CandidateMetric) -> ScreeningResult:
        """Screen a single metric across all targets.

        Returns ScreeningResult with per-target performance.
        """
        # Compute metric values for all matches
        values = []
        valid_indices = []
        for i in range(self._n):
            v = compute_metric_value(metric, self._matches, i)
            if v is not None and not math.isnan(v) and not math.isinf(v):
                values.append(v)
                valid_indices.append(i)

        if len(values) < 100:
            return ScreeningResult(
                metric_id=metric.metric_id,
                metric_name=metric.name,
                targets_tested=0,
                targets_positive=0,
                breadth_score=0.0,
                best_vs_naive_pct=0.0,
                mean_vs_naive_pct=0.0,
                min_p_value=1.0,
                target_results=[],
                overall_p_value=1.0,
                passed_screen=False,
            )

        # Split by median
        median_val = float(np.median(values))
        high_indices = [valid_indices[i] for i, v in enumerate(values) if v > median_val]
        low_indices = [valid_indices[i] for i, v in enumerate(values) if v <= median_val]

        if len(high_indices) < 50 or len(low_indices) < 50:
            return ScreeningResult(
                metric_id=metric.metric_id,
                metric_name=metric.name,
                targets_tested=0,
                targets_positive=0,
                breadth_score=0.0,
                best_vs_naive_pct=0.0,
                mean_vs_naive_pct=0.0,
                min_p_value=1.0,
                target_results=[],
                overall_p_value=1.0,
                passed_screen=False,
            )

        # Test across all targets
        target_results = []
        p_values_for_fisher = []

        for target_name, lines in TARGET_GROUPS.items():
            # For correlated lines within a target, take the BEST result but
            # apply Bonferroni correction within the group.
            line_results = []
            for line in lines:
                tr = self._test_target(high_indices, low_indices, target_name, line)
                if tr is not None:
                    line_results.append(tr)

            if line_results:
                # Bonferroni within correlated lines
                n_lines = len(lines)
                for lr in line_results:
                    lr.p_value = min(1.0, lr.p_value * n_lines)

                # Take best (lowest p) after correction
                best = min(line_results, key=lambda r: r.p_value)
                target_results.append(best)
                p_values_for_fisher.append(best.p_value)

        if not target_results:
            return ScreeningResult(
                metric_id=metric.metric_id,
                metric_name=metric.name,
                targets_tested=0,
                targets_positive=0,
                breadth_score=0.0,
                best_vs_naive_pct=0.0,
                mean_vs_naive_pct=0.0,
                min_p_value=1.0,
                target_results=[],
                overall_p_value=1.0,
                passed_screen=False,
            )

        # Aggregate
        targets_positive = sum(1 for t in target_results if t.positive)
        targets_tested = len(target_results)
        breadth = targets_positive / targets_tested if targets_tested > 0 else 0.0
        best_vs_naive = max(t.vs_naive_pct for t in target_results)
        mean_vs_naive = float(np.mean([t.vs_naive_pct for t in target_results]))
        min_p = min(t.p_value for t in target_results)

        # Combined p-value (Fisher's method)
        # Only use p-values from independent target GROUPS (not correlated lines)
        if len(p_values_for_fisher) >= 2:
            chi2 = -2 * sum(math.log(max(p, 1e-300)) for p in p_values_for_fisher)
            df = 2 * len(p_values_for_fisher)
            overall_p = float(sp_stats.chi2.sf(chi2, df))
        else:
            overall_p = min_p

        # Passed screen: at least 2 targets positive AND overall p < 0.10
        passed = targets_positive >= 2 and overall_p < 0.10

        return ScreeningResult(
            metric_id=metric.metric_id,
            metric_name=metric.name,
            targets_tested=targets_tested,
            targets_positive=targets_positive,
            breadth_score=breadth,
            best_vs_naive_pct=best_vs_naive,
            mean_vs_naive_pct=mean_vs_naive,
            min_p_value=min_p,
            target_results=target_results,
            overall_p_value=overall_p,
            passed_screen=passed,
        )

    def _test_target(
        self,
        high_indices: list[int],
        low_indices: list[int],
        target: str,
        line: Optional[float],
    ) -> Optional[TargetResult]:
        """Test whether high-metric matches differ from low-metric on a target."""
        high_outcomes = []
        for idx in high_indices:
            o = compute_outcome(self._matches[idx], target, line)
            if o is not None:
                high_outcomes.append(o)

        low_outcomes = []
        for idx in low_indices:
            o = compute_outcome(self._matches[idx], target, line)
            if o is not None:
                low_outcomes.append(o)

        if len(high_outcomes) < 30 or len(low_outcomes) < 30:
            return None

        high_rate = float(np.mean(high_outcomes))
        low_rate = float(np.mean(low_outcomes))
        naive_rate = float(np.mean(high_outcomes + low_outcomes))

        # Is high_rate significantly different from naive?
        n_high = len(high_outcomes)
        n_hits = int(sum(high_outcomes))

        try:
            result = sp_stats.binomtest(n_hits, n_high, naive_rate, alternative="greater")
            p_value = float(result.pvalue)
        except Exception:
            p_value = 1.0

        vs_naive_pct = ((high_rate - naive_rate) / naive_rate * 100) if naive_rate > 0 else 0.0

        # Effect size (Cohen's h)
        try:
            effect_size = 2 * (math.asin(math.sqrt(high_rate)) - math.asin(math.sqrt(naive_rate)))
        except (ValueError, ZeroDivisionError):
            effect_size = 0.0

        return TargetResult(
            target=target,
            line=line,
            n_qualifying=n_high,
            hit_rate_with_metric=high_rate,
            naive_rate=naive_rate,
            vs_naive_pct=vs_naive_pct,
            p_value=p_value,
            effect_size=effect_size,
            positive=vs_naive_pct > 0 and p_value < 0.10,
        )
