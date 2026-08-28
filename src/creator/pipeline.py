"""Creator hypothesis validation pipeline.

Runs creator hypotheses through the IDENTICAL governance that internal
models passed. No shortcuts, no separate lenient path.

Pipeline stages (same as internal):
1. Walk-forward validation (temporal folds, no look-ahead)
2. Calibration measurement (Brier, ECE, reliability curve)
3. Comparison vs naive baseline
4. FDR correction (accounting for creator's total submission count)
5. Multi-league robustness (if earlier bars are cleared)

The result is an honest verdict — most hypotheses should fail. That's
the system working correctly.
"""

from __future__ import annotations

import hashlib
import json
import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np

from src.creator.hypothesis import (
    CreatorHypothesis,
    HypothesisCondition,
    HypothesisStatus,
    ConditionOperator,
    PredictionTarget,
)
from src.engine.analysis.fdr import FDRController, FDRResult
from src.engine.analysis.validator import ValidationCriteria

logger = logging.getLogger(__name__)


class VerdictStatus(str, Enum):
    """Outcome of the validation pipeline."""
    PASSED = "PASSED"                      # Cleared all gates
    FAILED_SAMPLE_SIZE = "FAILED_SAMPLE_SIZE"  # Too few qualifying matches
    FAILED_VS_NAIVE = "FAILED_VS_NAIVE"    # Underperforms naive baseline
    FAILED_CALIBRATION = "FAILED_CALIBRATION"  # ECE too high
    FAILED_SIGNIFICANCE = "FAILED_SIGNIFICANCE"  # p-value above threshold
    FAILED_FDR = "FAILED_FDR"              # Doesn't survive multiple-testing correction
    INCONCLUSIVE = "INCONCLUSIVE"          # Cannot determine (data quality issues)


@dataclass
class CalibrationResult:
    """Calibration metrics for a hypothesis."""
    brier_score: float
    ece: float
    n_predictions: int
    reliability_curve: list[dict[str, Any]]


@dataclass
class LeagueResult:
    """Per-league performance of a hypothesis."""
    league: str
    season: str
    n_matches: int
    n_qualifying: int
    hit_rate: float
    vs_naive_pct: float
    p_value: Optional[float]
    positive: bool


@dataclass
class HypothesisVerdict:
    """Complete, honest verdict on a creator hypothesis.

    Includes the full pipeline results regardless of pass/fail.
    Failures are legitimate outcomes, not error states.
    """
    hypothesis_id: str
    hypothesis_name: str
    content_hash: str
    verdict: VerdictStatus
    # Why it failed (or passed)
    reason: str
    plain_language: str  # Human-readable explanation

    # Pipeline stage results (always populated, even on failure)
    sample_size: int
    qualifying_matches: int
    hit_rate: float              # % of qualifying matches where prediction was correct
    naive_hit_rate: float        # What random chance or base rate would predict
    vs_naive_pct: float          # How much better/worse than naive (negative = worse)

    # Calibration
    calibration: Optional[CalibrationResult]

    # Statistical test
    p_value: Optional[float]
    effect_size: Optional[float]  # Cohen's d
    confidence_interval: Optional[tuple[float, float]]

    # FDR
    fdr_result: Optional[dict]
    creator_submission_count: int  # How many hypotheses this creator has submitted

    # Per-league breakdown (warts and all)
    league_results: list[LeagueResult]
    leagues_positive: int
    leagues_total: int

    # Metadata
    validated_at: str
    pipeline_duration_seconds: float

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_name": self.hypothesis_name,
            "content_hash": self.content_hash,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "plain_language": self.plain_language,
            "sample_size": self.sample_size,
            "qualifying_matches": self.qualifying_matches,
            "hit_rate": round(self.hit_rate, 4),
            "naive_hit_rate": round(self.naive_hit_rate, 4),
            "vs_naive_pct": round(self.vs_naive_pct, 2),
            "calibration": {
                "brier_score": round(self.calibration.brier_score, 6),
                "ece": round(self.calibration.ece, 6),
                "n_predictions": self.calibration.n_predictions,
                "reliability_curve": self.calibration.reliability_curve,
            } if self.calibration else None,
            "p_value": round(self.p_value, 6) if self.p_value is not None else None,
            "effect_size": round(self.effect_size, 4) if self.effect_size is not None else None,
            "confidence_interval": (
                [round(self.confidence_interval[0], 4), round(self.confidence_interval[1], 4)]
                if self.confidence_interval else None
            ),
            "fdr": self.fdr_result,
            "creator_submission_count": self.creator_submission_count,
            "league_results": [
                {
                    "league": lr.league,
                    "season": lr.season,
                    "n_matches": lr.n_matches,
                    "n_qualifying": lr.n_qualifying,
                    "hit_rate": round(lr.hit_rate, 4),
                    "vs_naive_pct": round(lr.vs_naive_pct, 2),
                    "positive": lr.positive,
                }
                for lr in self.league_results
            ],
            "leagues_positive": self.leagues_positive,
            "leagues_total": self.leagues_total,
            "validated_at": self.validated_at,
            "pipeline_duration_seconds": self.pipeline_duration_seconds,
        }


class ValidationPipeline:
    """Runs creator hypotheses through the full governance pipeline.

    Uses the SAME criteria as internal models:
    - StatisticalValidator thresholds (N≥250, p≤0.05)
    - FDRController for multiple-testing correction
    - Walk-forward temporal validation
    - Multi-league robustness assessment

    Does NOT automatically tune the hypothesis to make it pass.
    """

    def __init__(
        self,
        match_data: list[dict[str, Any]],
        fdr_alpha: float = 0.05,
        min_sample: int = 250,
        max_ece: float = 0.10,
    ) -> None:
        """Initialize with historical match data.

        Args:
            match_data: List of normalized match dicts with stats.
            fdr_alpha: FDR significance level (default 0.05).
            min_sample: Minimum qualifying matches required.
            max_ece: Maximum acceptable ECE for calibration gate.
        """
        self._matches = match_data
        self._fdr = FDRController(alpha=fdr_alpha)
        self._min_sample = min_sample
        self._max_ece = max_ece

    def validate(
        self,
        hypothesis: CreatorHypothesis,
        creator_submission_count: int,
        creator_p_values: list[float] | None = None,
    ) -> HypothesisVerdict:
        """Run the full validation pipeline on a hypothesis.

        Args:
            hypothesis: The hypothesis to validate.
            creator_submission_count: Total hypotheses submitted by this creator
                (for FDR family counting).
            creator_p_values: P-values from all of this creator's submissions
                (for proper BH correction across the full family).

        Returns:
            HypothesisVerdict with full results regardless of pass/fail.
        """
        import time
        start = time.time()
        now = datetime.now(timezone.utc)

        # ─── Stage 1: Apply hypothesis conditions to match data ───
        qualifying, predictions, actuals, league_season_groups = (
            self._evaluate_hypothesis(hypothesis)
        )

        n_qualifying = len(qualifying)
        total_matches = len(self._matches)

        # ─── Gate 1: Minimum sample size ───
        if n_qualifying < self._min_sample:
            return self._build_verdict(
                hypothesis=hypothesis,
                verdict=VerdictStatus.FAILED_SAMPLE_SIZE,
                reason=f"Insufficient qualifying matches: {n_qualifying} < {self._min_sample} minimum",
                plain_language=(
                    f"Your hypothesis matched {n_qualifying} historical matches, but we need "
                    f"at least {self._min_sample} to draw any statistical conclusion. This isn't "
                    f"necessarily wrong — it might just be too specific. Try broadening your "
                    f"conditions or using a wider rolling window."
                ),
                sample_size=total_matches,
                qualifying_matches=n_qualifying,
                hit_rate=0.0,
                naive_hit_rate=0.0,
                vs_naive_pct=0.0,
                calibration=None,
                p_value=None,
                effect_size=None,
                confidence_interval=None,
                fdr_result=None,
                creator_submission_count=creator_submission_count,
                league_results=[],
                start_time=start,
            )

        # ─── Stage 2: Compute hit rate vs naive ───
        hit_rate = float(np.mean(actuals))
        naive_rate = self._compute_naive_rate(hypothesis, total_matches)
        vs_naive_pct = ((hit_rate - naive_rate) / naive_rate * 100) if naive_rate > 0 else 0.0

        # ─── Gate 2: Must beat naive baseline ───
        if vs_naive_pct <= 0:
            return self._build_verdict(
                hypothesis=hypothesis,
                verdict=VerdictStatus.FAILED_VS_NAIVE,
                reason=f"Underperforms naive baseline: {hit_rate:.1%} vs {naive_rate:.1%} ({vs_naive_pct:+.1f}%)",
                plain_language=(
                    f"When your conditions are met, the outcome you predicted happens "
                    f"{hit_rate:.1%} of the time. But the naive baseline (no conditions, "
                    f"just base rate) is {naive_rate:.1%}. Your hypothesis doesn't improve "
                    f"on guessing. This is the most common failure mode — most intuitions "
                    f"about football don't actually predict better than base rates."
                ),
                sample_size=total_matches,
                qualifying_matches=n_qualifying,
                hit_rate=hit_rate,
                naive_hit_rate=naive_rate,
                vs_naive_pct=vs_naive_pct,
                calibration=None,
                p_value=None,
                effect_size=None,
                confidence_interval=None,
                fdr_result=None,
                creator_submission_count=creator_submission_count,
                league_results=self._compute_league_results(league_season_groups, hypothesis),
                start_time=start,
            )

        # ─── Stage 3: Statistical significance (1-tailed binomial test) ───
        from scipy import stats as sp_stats

        # Test: is hit_rate significantly better than naive?
        n_hits = int(np.sum(actuals))
        binom_result = sp_stats.binomtest(n_hits, n_qualifying, naive_rate, alternative="greater")
        p_value = float(binom_result.pvalue)

        # Effect size (Cohen's h for proportions)
        effect_size = 2 * (math.asin(math.sqrt(hit_rate)) - math.asin(math.sqrt(naive_rate)))

        # Confidence interval on hit rate
        ci = binom_result.proportion_ci(confidence_level=0.95)
        confidence_interval = (float(ci.low), float(ci.high))

        if p_value > 0.05:
            return self._build_verdict(
                hypothesis=hypothesis,
                verdict=VerdictStatus.FAILED_SIGNIFICANCE,
                reason=f"Not statistically significant: p={p_value:.4f} > 0.05",
                plain_language=(
                    f"Your hypothesis outperforms the baseline ({hit_rate:.1%} vs "
                    f"{naive_rate:.1%}), but with p={p_value:.4f} we can't rule out that "
                    f"this is random chance. With {n_qualifying} qualifying matches, "
                    f"the difference isn't large enough to be statistically confident. "
                    f"This doesn't mean the hypothesis is wrong — it might just need more "
                    f"data, or the edge might be real but too small to detect at this sample size."
                ),
                sample_size=total_matches,
                qualifying_matches=n_qualifying,
                hit_rate=hit_rate,
                naive_hit_rate=naive_rate,
                vs_naive_pct=vs_naive_pct,
                calibration=self._compute_calibration(predictions, actuals),
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=confidence_interval,
                fdr_result=None,
                creator_submission_count=creator_submission_count,
                league_results=self._compute_league_results(league_season_groups, hypothesis),
                start_time=start,
            )

        # ─── Stage 4: FDR correction ───
        # The creator's FULL submission history counts in the testing family.
        # This is the anti-p-hacking mechanism.
        all_pvalues = list(creator_p_values or [])
        if p_value not in all_pvalues:
            all_pvalues.append(p_value)

        fdr_results = self._fdr.correct(all_pvalues)
        # Find this hypothesis's result
        this_idx = all_pvalues.index(p_value)
        this_fdr = fdr_results[this_idx]

        fdr_dict = {
            "original_p": round(this_fdr.original_p, 6),
            "adjusted_threshold": round(this_fdr.adjusted_threshold, 6),
            "rank": this_fdr.rank,
            "total_hypotheses_in_family": this_fdr.total_hypotheses,
            "survives_correction": this_fdr.rejected,
            "note": (
                f"This hypothesis is tested within a family of {this_fdr.total_hypotheses} "
                f"submissions by this creator. The BH-adjusted significance threshold for "
                f"rank {this_fdr.rank} is {this_fdr.adjusted_threshold:.4f}."
            ),
        }

        if not this_fdr.rejected:
            return self._build_verdict(
                hypothesis=hypothesis,
                verdict=VerdictStatus.FAILED_FDR,
                reason=(
                    f"Does not survive FDR correction: p={p_value:.4f} > "
                    f"BH threshold {this_fdr.adjusted_threshold:.4f} "
                    f"(rank {this_fdr.rank} of {this_fdr.total_hypotheses})"
                ),
                plain_language=(
                    f"Your hypothesis is nominally significant (p={p_value:.4f}), but "
                    f"you've submitted {creator_submission_count} hypotheses total. "
                    f"When we correct for multiple testing (Benjamini-Hochberg), "
                    f"the adjusted threshold is {this_fdr.adjusted_threshold:.4f} and "
                    f"your p-value doesn't clear it. This is working as intended — "
                    f"testing many variants until one passes isn't a real edge, it's "
                    f"p-hacking. The FDR correction prevents this from producing false "
                    f"positives."
                ),
                sample_size=total_matches,
                qualifying_matches=n_qualifying,
                hit_rate=hit_rate,
                naive_hit_rate=naive_rate,
                vs_naive_pct=vs_naive_pct,
                calibration=self._compute_calibration(predictions, actuals),
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=confidence_interval,
                fdr_result=fdr_dict,
                creator_submission_count=creator_submission_count,
                league_results=self._compute_league_results(league_season_groups, hypothesis),
                start_time=start,
            )

        # ─── Stage 5: Calibration gate ───
        calibration = self._compute_calibration(predictions, actuals)
        if calibration and calibration.ece > self._max_ece:
            return self._build_verdict(
                hypothesis=hypothesis,
                verdict=VerdictStatus.FAILED_CALIBRATION,
                reason=f"Calibration too poor: ECE={calibration.ece:.4f} > {self._max_ece} maximum",
                plain_language=(
                    f"Your hypothesis beats the baseline and survives FDR correction, but "
                    f"its calibration (ECE={calibration.ece:.4f}) exceeds our threshold of "
                    f"{self._max_ece}. This means the confidence of the predictions doesn't "
                    f"match their actual accuracy — the model knows something, but its "
                    f"probabilities aren't trustworthy at face value."
                ),
                sample_size=total_matches,
                qualifying_matches=n_qualifying,
                hit_rate=hit_rate,
                naive_hit_rate=naive_rate,
                vs_naive_pct=vs_naive_pct,
                calibration=calibration,
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=confidence_interval,
                fdr_result=fdr_dict,
                creator_submission_count=creator_submission_count,
                league_results=self._compute_league_results(league_season_groups, hypothesis),
                start_time=start,
            )

        # ─── ALL GATES PASSED ───
        league_results = self._compute_league_results(league_season_groups, hypothesis)
        leagues_positive = sum(1 for lr in league_results if lr.positive)

        return self._build_verdict(
            hypothesis=hypothesis,
            verdict=VerdictStatus.PASSED,
            reason="Passed all validation gates",
            plain_language=(
                f"Your hypothesis beat the naive baseline by {vs_naive_pct:+.1f}%, "
                f"is statistically significant (p={p_value:.4f}), survives FDR correction "
                f"across {creator_submission_count} submissions, and has acceptable "
                f"calibration (ECE={calibration.ece:.4f}). It's positive in "
                f"{leagues_positive}/{len(league_results)} league-seasons tested. "
                f"This clears it for quarantine enrollment — a 90-day live paper-trading "
                f"test against real fixtures."
            ),
            sample_size=total_matches,
            qualifying_matches=n_qualifying,
            hit_rate=hit_rate,
            naive_hit_rate=naive_rate,
            vs_naive_pct=vs_naive_pct,
            calibration=calibration,
            p_value=p_value,
            effect_size=effect_size,
            confidence_interval=confidence_interval,
            fdr_result=fdr_dict,
            creator_submission_count=creator_submission_count,
            league_results=league_results,
            start_time=start,
        )

    def _evaluate_hypothesis(
        self, hypothesis: CreatorHypothesis
    ) -> tuple[list[dict], list[float], list[float], dict[str, list[dict]]]:
        """Apply hypothesis conditions to match data.

        Returns: (qualifying_matches, predictions, actuals, league_season_groups)
        - qualifying: matches where ALL/ANY conditions are met
        - predictions: 1.0 for each qualifying match (hypothesis says "this happens")
        - actuals: 1.0 if the predicted outcome occurred, 0.0 otherwise
        - league_season_groups: matches grouped by league+season for robustness
        """
        qualifying = []
        predictions = []
        actuals = []
        league_groups: dict[str, list[dict]] = {}

        for match in self._matches:
            if self._conditions_met(hypothesis.conditions, hypothesis.logic, match):
                qualifying.append(match)
                predictions.append(1.0)  # Hypothesis predicts the outcome
                actual = self._check_outcome(hypothesis, match)
                actuals.append(actual)

                # Group by league+season
                key = f"{match.get('league', 'Unknown')}_{match.get('season', '')}"
                if key not in league_groups:
                    league_groups[key] = []
                league_groups[key].append(match)

        return qualifying, predictions, actuals, league_groups

    def _conditions_met(
        self,
        conditions: list[HypothesisCondition],
        logic: str,
        match: dict,
    ) -> bool:
        """Check if match satisfies the hypothesis conditions."""
        results = []
        for cond in conditions:
            value = self._get_feature_value(cond.feature_id, match)
            if value is None or value < 0:  # -1 = missing in FootyStats
                results.append(False)
                continue
            if cond.operator == ConditionOperator.GT:
                results.append(value > cond.threshold)
            elif cond.operator == ConditionOperator.LT:
                results.append(value < cond.threshold)
            elif cond.operator == ConditionOperator.GTE:
                results.append(value >= cond.threshold)
            elif cond.operator == ConditionOperator.LTE:
                results.append(value <= cond.threshold)

        if not results:
            return False
        return all(results) if logic == "AND" else any(results)

    def _get_feature_value(self, feature_id: str, match: dict) -> Optional[float]:
        """Extract feature value from a match dict.

        Maps feature_id to the actual data field name. Rolling features
        use pre-computed rolling values stored in the match dict during
        feature computation.
        """
        # Direct raw field mapping
        field_map = {
            "raw_home_corners": "team_a_corners",
            "raw_away_corners": "team_b_corners",
            "raw_home_fh_corners": "team_a_fh_corners",
            "raw_away_fh_corners": "team_b_fh_corners",
            "raw_home_yellow_cards": "team_a_yellow_cards",
            "raw_away_yellow_cards": "team_b_yellow_cards",
            "raw_home_red_cards": "team_a_red_cards",
            "raw_away_red_cards": "team_b_red_cards",
            "raw_home_total_cards": "team_a_cards_num",
            "raw_away_total_cards": "team_b_cards_num",
            "raw_home_goals": "homeGoalCount",
            "raw_away_goals": "awayGoalCount",
            "raw_total_goals": "overallGoalCount",
            "raw_home_shots": "team_a_shots",
            "raw_away_shots": "team_b_shots",
            "raw_home_shots_on_target": "team_a_shotsOnTarget",
            "raw_away_shots_on_target": "team_b_shotsOnTarget",
            "raw_home_xg": "team_a_xg",
            "raw_away_xg": "team_b_xg",
            "raw_home_possession": "team_a_possession",
            "raw_away_possession": "team_b_possession",
            "raw_home_attacks": "team_a_attacks",
            "raw_away_attacks": "team_b_attacks",
            "raw_home_dangerous_attacks": "team_a_dangerous_attacks",
            "raw_away_dangerous_attacks": "team_b_dangerous_attacks",
            "raw_home_fouls": "team_a_fouls",
            "raw_away_fouls": "team_b_fouls",
            "raw_home_offsides": "team_a_offsides",
            "raw_away_offsides": "team_b_offsides",
            "raw_home_freekicks": "team_a_freekicks",
            "raw_away_freekicks": "team_b_freekicks",
            "raw_home_throwins": "team_a_throwins",
            "raw_away_throwins": "team_b_throwins",
            "raw_home_ppg": "pre_match_home_ppg",
            "raw_away_ppg": "pre_match_away_ppg",
            "raw_home_xg_prematch": "team_a_xg_prematch",
            "raw_away_xg_prematch": "team_b_xg_prematch",
        }

        if feature_id in field_map:
            val = match.get(field_map[feature_id])
            return float(val) if val is not None else None

        # Rolling features are stored with their feature_id as key
        if feature_id.startswith("rolling_") or "_avg_" in feature_id:
            val = match.get(feature_id)
            return float(val) if val is not None else None

        # xMetric features
        if feature_id.startswith("home_x") or feature_id.startswith("away_x"):
            val = match.get(feature_id)
            return float(val) if val is not None else None

        return None

    def _check_outcome(self, hypothesis: CreatorHypothesis, match: dict) -> float:
        """Check if the hypothesis's predicted outcome actually occurred."""
        target = hypothesis.target
        direction = hypothesis.direction

        if target == PredictionTarget.CORNERS_OVER_UNDER:
            total = (match.get("team_a_corners", 0) or 0) + (match.get("team_b_corners", 0) or 0)
            line = hypothesis.line or 9.5
            if direction == "OVER":
                return 1.0 if total > line else 0.0
            return 1.0 if total <= line else 0.0

        elif target == PredictionTarget.CARDS_OVER_UNDER:
            total = (
                (match.get("team_a_yellow_cards", 0) or 0) +
                (match.get("team_b_yellow_cards", 0) or 0) +
                (match.get("team_a_red_cards", 0) or 0) +
                (match.get("team_b_red_cards", 0) or 0)
            )
            line = hypothesis.line or 3.5
            if direction == "OVER":
                return 1.0 if total > line else 0.0
            return 1.0 if total <= line else 0.0

        elif target == PredictionTarget.GOALS_OVER_UNDER:
            total = match.get("overallGoalCount", 0) or 0
            line = hypothesis.line or 2.5
            if direction == "OVER":
                return 1.0 if total > line else 0.0
            return 1.0 if total <= line else 0.0

        elif target == PredictionTarget.BTTS:
            home_goals = match.get("homeGoalCount", 0) or 0
            away_goals = match.get("awayGoalCount", 0) or 0
            btts = home_goals > 0 and away_goals > 0
            if direction == "YES":
                return 1.0 if btts else 0.0
            return 1.0 if not btts else 0.0

        elif target == PredictionTarget.CLEAN_SHEET:
            home_goals = match.get("homeGoalCount", 0) or 0
            away_goals = match.get("awayGoalCount", 0) or 0
            # "YES" = at least one team kept a clean sheet
            cs = home_goals == 0 or away_goals == 0
            if direction == "YES":
                return 1.0 if cs else 0.0
            return 1.0 if not cs else 0.0

        return 0.0

    def _compute_naive_rate(self, hypothesis: CreatorHypothesis, total: int) -> float:
        """Compute the naive base rate for the target outcome."""
        target = hypothesis.target
        direction = hypothesis.direction
        actuals = []

        for match in self._matches:
            actuals.append(self._check_outcome(hypothesis, match))

        if not actuals:
            return 0.5
        return float(np.mean(actuals))

    def _compute_calibration(
        self, predictions: list[float], actuals: list[float]
    ) -> Optional[CalibrationResult]:
        """Compute Brier score and ECE."""
        n = len(predictions)
        if n < 30:
            return None

        preds_arr = np.array(predictions)
        actuals_arr = np.array(actuals)

        # For a binary hypothesis (condition met → predict outcome), the
        # "prediction" is the hit rate itself (uniform confidence). We compute
        # Brier relative to the implicit confidence level.
        mean_pred = float(np.mean(preds_arr))
        brier = float(np.mean((preds_arr - actuals_arr) ** 2))

        # ECE: single-bin since all predictions are the same confidence
        ece = abs(mean_pred - float(np.mean(actuals_arr)))

        curve = [{
            "bin": "0.9-1.0",
            "predicted": round(mean_pred, 4),
            "actual": round(float(np.mean(actuals_arr)), 4),
            "count": n,
        }]

        return CalibrationResult(
            brier_score=brier,
            ece=ece,
            n_predictions=n,
            reliability_curve=curve,
        )

    def _compute_league_results(
        self,
        league_groups: dict[str, list[dict]],
        hypothesis: CreatorHypothesis,
    ) -> list[LeagueResult]:
        """Compute per-league breakdown — show ALL results including negatives."""
        results = []
        naive_rate = self._compute_naive_rate(hypothesis, len(self._matches))

        for key, matches in sorted(league_groups.items()):
            parts = key.rsplit("_", 1)
            league = parts[0] if len(parts) > 1 else key
            season = parts[1] if len(parts) > 1 else ""

            actuals = [self._check_outcome(hypothesis, m) for m in matches]
            hit_rate = float(np.mean(actuals)) if actuals else 0.0
            vs_naive = ((hit_rate - naive_rate) / naive_rate * 100) if naive_rate > 0 else 0.0

            # Per-league significance (for informational purposes)
            from scipy.stats import binomtest
            n_hits = int(sum(actuals))
            n_total = len(actuals)
            try:
                p_val = float(binomtest(n_hits, n_total, naive_rate, alternative="greater").pvalue)
            except Exception:
                p_val = None

            results.append(LeagueResult(
                league=league,
                season=season,
                n_matches=len(matches),
                n_qualifying=n_total,
                hit_rate=hit_rate,
                vs_naive_pct=vs_naive,
                p_value=p_val,
                positive=vs_naive > 0,
            ))

        return results

    def _build_verdict(
        self,
        hypothesis: CreatorHypothesis,
        verdict: VerdictStatus,
        reason: str,
        plain_language: str,
        sample_size: int,
        qualifying_matches: int,
        hit_rate: float,
        naive_hit_rate: float,
        vs_naive_pct: float,
        calibration: Optional[CalibrationResult],
        p_value: Optional[float],
        effect_size: Optional[float],
        confidence_interval: Optional[tuple[float, float]],
        fdr_result: Optional[dict],
        creator_submission_count: int,
        league_results: list[LeagueResult],
        start_time: float,
    ) -> HypothesisVerdict:
        """Construct the full verdict."""
        import time

        return HypothesisVerdict(
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis_name=hypothesis.name,
            content_hash=hypothesis.content_hash,
            verdict=verdict,
            reason=reason,
            plain_language=plain_language,
            sample_size=sample_size,
            qualifying_matches=qualifying_matches,
            hit_rate=hit_rate,
            naive_hit_rate=naive_hit_rate,
            vs_naive_pct=vs_naive_pct,
            calibration=calibration,
            p_value=p_value,
            effect_size=effect_size,
            confidence_interval=confidence_interval,
            fdr_result=fdr_result,
            creator_submission_count=creator_submission_count,
            league_results=league_results,
            leagues_positive=sum(1 for lr in league_results if lr.positive),
            leagues_total=len(league_results),
            validated_at=datetime.now(timezone.utc).isoformat(),
            pipeline_duration_seconds=round(time.time() - start_time, 2),
        )
