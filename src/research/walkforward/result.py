"""Walk-Forward Result structures.

Contains:
- FoldResult: Per-fold evidence from a single walk-forward evaluation
- WalkForwardResult: Aggregated evidence across all folds

IMPORTANT: Aggregation does NOT simply concatenate folds.
Each fold is treated as semi-independent evidence.
The aggregation methodology is documented explicitly.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import numpy as np

from src.research.experiment_engine.result import (
    BaselineComparison,
    EconomicMetrics,
    EvidenceClassification,
    ExperimentResult,
    ExperimentResultStatus,
    PredictiveMetrics,
    StatisticalEvidence,
)
from src.research.walkforward.folds import FoldSpec


class FoldStatus(Enum):
    """Status of a single fold evaluation."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_TRAINING_DATA = "INSUFFICIENT_TRAINING_DATA"
    INSUFFICIENT_TEST_DATA = "INSUFFICIENT_TEST_DATA"
    MODEL_FAILURE = "MODEL_FAILURE"
    NO_PREDICTIONS = "NO_PREDICTIONS"
    TEMPORAL_VIOLATION = "TEMPORAL_VIOLATION"
    SKIPPED = "SKIPPED"


class WalkForwardStatus(Enum):
    """Overall walk-forward validation status."""

    COMPLETED = "COMPLETED"
    INSUFFICIENT_FOLDS = "INSUFFICIENT_FOLDS"
    ALL_FOLDS_FAILED = "ALL_FOLDS_FAILED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


@dataclass(frozen=True)
class FoldResult:
    """Result of evaluating one walk-forward fold.

    Contains complete evidence for a single temporal period,
    including the model refitted on that fold's training data.

    Attributes:
        fold_spec: The fold boundaries used.
        status: Outcome status of this fold.
        experiment_result: Full ExperimentResult (None if fold failed).
        model_identity: Identity of the model fitted for this fold.
        training_observations: Number of training matches available.
        test_observations: Number of test matches available.
        validation_observations: Number of validation matches (0 if no validation).
    """

    fold_spec: FoldSpec
    status: FoldStatus
    experiment_result: Optional[ExperimentResult] = None
    model_identity: str = ""
    training_observations: int = 0
    test_observations: int = 0
    validation_observations: int = 0

    @property
    def fold_index(self) -> int:
        return self.fold_spec.fold_index

    @property
    def is_successful(self) -> bool:
        return self.status == FoldStatus.COMPLETED and self.experiment_result is not None

    @property
    def p_value(self) -> Optional[float]:
        """Extract p-value for FDR consumption."""
        if self.experiment_result is None:
            return None
        return self.experiment_result.statistical_evidence.p_value

    @property
    def roi_pct(self) -> Optional[float]:
        """Extract ROI for fold consistency analysis."""
        if self.experiment_result is None:
            return None
        if not self.experiment_result.economic_metrics.odds_available:
            return None
        return self.experiment_result.economic_metrics.roi_pct

    @property
    def hit_rate(self) -> Optional[float]:
        """Extract hit rate."""
        if self.experiment_result is None:
            return None
        return self.experiment_result.predictive_metrics.hit_rate

    @property
    def ev(self) -> Optional[float]:
        """Extract mean EV."""
        if self.experiment_result is None:
            return None
        return self.experiment_result.economic_metrics.mean_ev

    @property
    def effect_size(self) -> Optional[float]:
        """Extract effect size."""
        if self.experiment_result is None:
            return None
        return self.experiment_result.statistical_evidence.effect_size

    @property
    def brier_score(self) -> Optional[float]:
        """Extract Brier score."""
        if self.experiment_result is None:
            return None
        return self.experiment_result.predictive_metrics.brier_score

    @property
    def sample_size(self) -> int:
        """Number of eligible predictions in this fold."""
        if self.experiment_result is None:
            return 0
        return self.experiment_result.predictive_metrics.sample_size

    def to_dict(self) -> dict[str, Any]:
        """Serialize for provenance."""
        return {
            "fold_index": self.fold_index,
            "status": self.status.value,
            "model_identity": self.model_identity,
            "training_observations": self.training_observations,
            "test_observations": self.test_observations,
            "validation_observations": self.validation_observations,
            "p_value": self.p_value,
            "roi_pct": self.roi_pct,
            "hit_rate": self.hit_rate,
            "effect_size": self.effect_size,
            "brier_score": self.brier_score,
            "sample_size": self.sample_size,
            "train_start": self.fold_spec.train_start,
            "train_end": self.fold_spec.train_end,
            "test_start": self.fold_spec.test_start,
            "test_end": self.fold_spec.test_end,
        }


@dataclass(frozen=True)
class StabilityMetrics:
    """Metrics quantifying fold-to-fold stability.

    A robust candidate should show consistent performance,
    not one lucky period.
    """

    positive_fold_ratio: float = 0.0  # fraction of folds with positive outcome
    roi_std: Optional[float] = None   # std dev of fold ROIs
    roi_iqr: Optional[float] = None   # interquartile range
    roi_mad: Optional[float] = None   # median absolute deviation
    hit_rate_std: Optional[float] = None
    worst_fold_roi: Optional[float] = None
    best_fold_roi: Optional[float] = None
    max_consecutive_negative: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive_fold_ratio": self.positive_fold_ratio,
            "roi_std": self.roi_std,
            "roi_iqr": self.roi_iqr,
            "roi_mad": self.roi_mad,
            "hit_rate_std": self.hit_rate_std,
            "worst_fold_roi": self.worst_fold_roi,
            "best_fold_roi": self.best_fold_roi,
            "max_consecutive_negative": self.max_consecutive_negative,
        }


@dataclass(frozen=True)
class AggregateStatisticalEvidence:
    """Aggregated statistical evidence across folds.

    Aggregation method: Fisher's combined probability test
    on fold-level p-values. This is more conservative than
    concatenating all predictions and running a single test.

    The aggregate p-value is what feeds into FDR correction.
    """

    fold_p_values: tuple[Optional[float], ...] = ()
    valid_p_value_count: int = 0
    combined_p_value: Optional[float] = None  # Fisher's method
    median_p_value: Optional[float] = None
    mean_effect_size: Optional[float] = None
    median_effect_size: Optional[float] = None
    mean_sample_size: float = 0.0
    total_sample_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_p_value_count": self.valid_p_value_count,
            "combined_p_value": self.combined_p_value,
            "median_p_value": self.median_p_value,
            "mean_effect_size": self.mean_effect_size,
            "median_effect_size": self.median_effect_size,
            "mean_sample_size": self.mean_sample_size,
            "total_sample_size": self.total_sample_size,
        }


@dataclass(frozen=True)
class WalkForwardResult:
    """Complete walk-forward validation result.

    Aggregates evidence across multiple temporal folds.
    Ready for FDR correction integration.

    AGGREGATION METHODOLOGY:
    - Statistical: Fisher's combined probability test on fold p-values
    - Economic: Median/mean of fold-level metrics (NOT concatenated)
    - Stability: Dispersion metrics across folds
    - This approach treats each fold as semi-independent evidence
    """

    experiment_id: str = ""
    candidate_hash: str = ""
    hypothesis_hash: str = ""
    market_type: str = ""

    status: WalkForwardStatus = WalkForwardStatus.COMPLETED

    # Fold details
    folds: tuple[FoldResult, ...] = ()
    fold_count: int = 0
    successful_folds: int = 0
    failed_folds: int = 0

    # Prediction counts
    total_predictions: int = 0
    total_eligible_predictions: int = 0

    # Aggregate metrics (from successful folds only)
    median_fold_roi: Optional[float] = None
    mean_fold_roi: Optional[float] = None
    median_fold_ev: Optional[float] = None
    mean_fold_ev: Optional[float] = None
    aggregate_hit_rate: Optional[float] = None
    aggregate_brier_score: Optional[float] = None

    # Statistical evidence
    aggregate_evidence: AggregateStatisticalEvidence = field(
        default_factory=AggregateStatisticalEvidence
    )

    # Stability
    stability: StabilityMetrics = field(default_factory=StabilityMetrics)

    # Maximum drawdown across all folds
    max_drawdown: Optional[float] = None

    # Configuration provenance
    walkforward_config_hash: str = ""

    @property
    def p_value_for_fdr(self) -> Optional[float]:
        """The p-value to feed into FDR correction.

        Uses Fisher's combined probability from fold-level p-values.
        This is the critical interface point for FDR integration.
        """
        return self.aggregate_evidence.combined_p_value

    @property
    def positive_fold_ratio(self) -> float:
        """Fraction of successful folds with positive outcome."""
        return self.stability.positive_fold_ratio

    @property
    def is_valid(self) -> bool:
        """Whether the result has enough evidence for further evaluation."""
        return self.status == WalkForwardStatus.COMPLETED and self.successful_folds > 0

    @property
    def content_hash(self) -> str:
        """Deterministic hash of the result content.

        Excludes runtime metadata (created_at, etc.)
        """
        canonical = json.dumps(
            {
                "experiment_id": self.experiment_id,
                "candidate_hash": self.candidate_hash,
                "hypothesis_hash": self.hypothesis_hash,
                "market_type": self.market_type,
                "status": self.status.value,
                "fold_count": self.fold_count,
                "successful_folds": self.successful_folds,
                "total_predictions": self.total_predictions,
                "combined_p_value": self.aggregate_evidence.combined_p_value,
                "walkforward_config_hash": self.walkforward_config_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Full serialization for storage/audit."""
        return {
            "experiment_id": self.experiment_id,
            "candidate_hash": self.candidate_hash,
            "hypothesis_hash": self.hypothesis_hash,
            "market_type": self.market_type,
            "status": self.status.value,
            "fold_count": self.fold_count,
            "successful_folds": self.successful_folds,
            "failed_folds": self.failed_folds,
            "total_predictions": self.total_predictions,
            "total_eligible_predictions": self.total_eligible_predictions,
            "median_fold_roi": self.median_fold_roi,
            "mean_fold_roi": self.mean_fold_roi,
            "median_fold_ev": self.median_fold_ev,
            "mean_fold_ev": self.mean_fold_ev,
            "aggregate_hit_rate": self.aggregate_hit_rate,
            "aggregate_brier_score": self.aggregate_brier_score,
            "aggregate_evidence": self.aggregate_evidence.to_dict(),
            "stability": self.stability.to_dict(),
            "max_drawdown": self.max_drawdown,
            "walkforward_config_hash": self.walkforward_config_hash,
            "p_value_for_fdr": self.p_value_for_fdr,
            "folds": [f.to_dict() for f in self.folds],
        }


def aggregate_fold_results(
    folds: list[FoldResult],
    experiment_id: str,
    candidate_hash: str,
    hypothesis_hash: str,
    market_type: str,
    walkforward_config_hash: str,
    minimum_folds: int = 3,
) -> WalkForwardResult:
    """Aggregate individual fold results into a WalkForwardResult.

    Aggregation methodology:
    - Statistical evidence: Fisher's combined probability test
    - Economic metrics: Median of fold-level metrics
    - Stability: Dispersion across folds
    - Each fold is treated as semi-independent evidence

    Args:
        folds: List of completed FoldResults.
        experiment_id: Parent experiment identifier.
        candidate_hash: Source candidate hash.
        hypothesis_hash: Source hypothesis hash.
        market_type: Target market.
        walkforward_config_hash: Config identity.
        minimum_folds: Minimum successful folds required.

    Returns:
        WalkForwardResult with aggregated evidence.
    """
    if not folds:
        return WalkForwardResult(
            experiment_id=experiment_id,
            candidate_hash=candidate_hash,
            hypothesis_hash=hypothesis_hash,
            market_type=market_type,
            status=WalkForwardStatus.INSUFFICIENT_FOLDS,
            walkforward_config_hash=walkforward_config_hash,
        )

    successful = [f for f in folds if f.is_successful]
    failed = [f for f in folds if not f.is_successful]

    if len(successful) < minimum_folds:
        return WalkForwardResult(
            experiment_id=experiment_id,
            candidate_hash=candidate_hash,
            hypothesis_hash=hypothesis_hash,
            market_type=market_type,
            status=WalkForwardStatus.INSUFFICIENT_FOLDS,
            folds=tuple(folds),
            fold_count=len(folds),
            successful_folds=len(successful),
            failed_folds=len(failed),
            walkforward_config_hash=walkforward_config_hash,
        )

    if not successful:
        return WalkForwardResult(
            experiment_id=experiment_id,
            candidate_hash=candidate_hash,
            hypothesis_hash=hypothesis_hash,
            market_type=market_type,
            status=WalkForwardStatus.ALL_FOLDS_FAILED,
            folds=tuple(folds),
            fold_count=len(folds),
            successful_folds=0,
            failed_folds=len(failed),
            walkforward_config_hash=walkforward_config_hash,
        )

    # Aggregate predictions
    total_preds = sum(f.sample_size for f in successful)

    # Aggregate economic metrics
    rois = [f.roi_pct for f in successful if f.roi_pct is not None]
    evs = [f.ev for f in successful if f.ev is not None]
    hit_rates = [f.hit_rate for f in successful if f.hit_rate is not None]
    brier_scores = [f.brier_score for f in successful if f.brier_score is not None]

    median_roi = float(np.median(rois)) if rois else None
    mean_roi = float(np.mean(rois)) if rois else None
    median_ev = float(np.median(evs)) if evs else None
    mean_ev = float(np.mean(evs)) if evs else None
    agg_hit_rate = float(np.mean(hit_rates)) if hit_rates else None
    agg_brier = float(np.mean(brier_scores)) if brier_scores else None

    # Aggregate statistical evidence using Fisher's method
    agg_evidence = _compute_aggregate_evidence(successful)

    # Stability metrics
    stability = _compute_stability(successful)

    # Max drawdown
    drawdowns = []
    for f in successful:
        if f.experiment_result and f.experiment_result.economic_metrics.max_drawdown is not None:
            drawdowns.append(f.experiment_result.economic_metrics.max_drawdown)
    max_dd = max(drawdowns) if drawdowns else None

    return WalkForwardResult(
        experiment_id=experiment_id,
        candidate_hash=candidate_hash,
        hypothesis_hash=hypothesis_hash,
        market_type=market_type,
        status=WalkForwardStatus.COMPLETED,
        folds=tuple(folds),
        fold_count=len(folds),
        successful_folds=len(successful),
        failed_folds=len(failed),
        total_predictions=total_preds,
        total_eligible_predictions=total_preds,
        median_fold_roi=median_roi,
        mean_fold_roi=mean_roi,
        median_fold_ev=median_ev,
        mean_fold_ev=mean_ev,
        aggregate_hit_rate=agg_hit_rate,
        aggregate_brier_score=agg_brier,
        aggregate_evidence=agg_evidence,
        stability=stability,
        max_drawdown=max_dd,
        walkforward_config_hash=walkforward_config_hash,
    )


def _compute_aggregate_evidence(
    successful_folds: list[FoldResult],
) -> AggregateStatisticalEvidence:
    """Compute aggregate statistical evidence using Fisher's combined test.

    Fisher's method combines p-values from independent tests:
    X = -2 * sum(ln(p_i))
    X ~ chi-squared with 2k degrees of freedom

    This is more conservative than concatenating predictions.
    """
    from scipy import stats as sp_stats

    p_values = [f.p_value for f in successful_folds]
    valid_ps = [p for p in p_values if p is not None and 0 < p <= 1]

    effect_sizes = [f.effect_size for f in successful_folds if f.effect_size is not None]
    sample_sizes = [f.sample_size for f in successful_folds]

    combined_p: Optional[float] = None
    if len(valid_ps) >= 2:
        # Fisher's method
        chi2_stat = -2.0 * sum(math.log(p) for p in valid_ps)
        df = 2 * len(valid_ps)
        combined_p = float(1.0 - sp_stats.chi2.cdf(chi2_stat, df))
    elif len(valid_ps) == 1:
        combined_p = valid_ps[0]

    median_p = float(np.median(valid_ps)) if valid_ps else None
    mean_es = float(np.mean(effect_sizes)) if effect_sizes else None
    median_es = float(np.median(effect_sizes)) if effect_sizes else None
    mean_ss = float(np.mean(sample_sizes)) if sample_sizes else 0.0
    total_ss = sum(sample_sizes)

    return AggregateStatisticalEvidence(
        fold_p_values=tuple(p_values),
        valid_p_value_count=len(valid_ps),
        combined_p_value=combined_p,
        median_p_value=median_p,
        mean_effect_size=mean_es,
        median_effect_size=median_es,
        mean_sample_size=mean_ss,
        total_sample_size=total_ss,
    )


def _compute_stability(successful_folds: list[FoldResult]) -> StabilityMetrics:
    """Compute stability metrics across folds.

    Detects:
    - One lucky period
    - Structural instability
    - Regime dependence
    """
    rois = [f.roi_pct for f in successful_folds if f.roi_pct is not None]
    hit_rates = [f.hit_rate for f in successful_folds if f.hit_rate is not None]

    # Positive fold ratio (based on ROI if available, else hit rate vs 0.5)
    if rois:
        positive_count = sum(1 for r in rois if r > 0)
        positive_ratio = positive_count / len(rois)
        roi_std = float(np.std(rois, ddof=1)) if len(rois) > 1 else None
        q75, q25 = np.percentile(rois, [75, 25]) if len(rois) >= 4 else (None, None)
        roi_iqr = float(q75 - q25) if q75 is not None and q25 is not None else None
        roi_mad = float(np.median(np.abs(np.array(rois) - np.median(rois)))) if rois else None
        worst_roi = float(min(rois))
        best_roi = float(max(rois))
    else:
        # Fall back to hit rate
        if hit_rates:
            positive_count = sum(1 for h in hit_rates if h > 0.5)
            positive_ratio = positive_count / len(hit_rates)
        else:
            positive_ratio = 0.0
        roi_std = None
        roi_iqr = None
        roi_mad = None
        worst_roi = None
        best_roi = None

    hit_rate_std = float(np.std(hit_rates, ddof=1)) if len(hit_rates) > 1 else None

    # Max consecutive negative folds
    max_consec_neg = 0
    current_neg = 0
    for f in successful_folds:
        roi = f.roi_pct
        if roi is not None and roi <= 0:
            current_neg += 1
            max_consec_neg = max(max_consec_neg, current_neg)
        else:
            current_neg = 0

    return StabilityMetrics(
        positive_fold_ratio=positive_ratio,
        roi_std=roi_std,
        roi_iqr=roi_iqr,
        roi_mad=roi_mad,
        hit_rate_std=hit_rate_std,
        worst_fold_roi=worst_roi,
        best_fold_roi=best_roi,
        max_consecutive_negative=max_consec_neg,
    )
