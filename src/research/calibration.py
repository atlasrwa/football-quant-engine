"""Probability calibration metrics for the research laboratory.

Evaluates how well a model's predicted probabilities match observed
frequencies. A well-calibrated model predicting 60% should have outcomes
occurring approximately 60% of the time.

Key metrics:
- Brier score: Mean squared error of probabilities (lower = better)
- Log loss: Logarithmic scoring rule (lower = better)
- Expected Calibration Error (ECE): Weighted average bin deviation
- Reliability diagram data: Predicted vs actual frequencies per bin

CRITICAL: All calibration must be evaluated on OUT-OF-SAMPLE data.
In-sample calibration is meaningless for research validation.

The distinction between calibration and profitability is fundamental:
- A perfectly calibrated model may not be profitable (market is efficient)
- A profitable model may not be well-calibrated (lucky outliers)
- Good calibration is NECESSARY but not SUFFICIENT for systematic edge
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CalibrationStatus(Enum):
    """Status of calibration evaluation."""

    VALID = "VALID"
    INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"
    NO_PREDICTIONS = "NO_PREDICTIONS"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    """A single bin in a reliability diagram.

    Attributes:
        bin_start: Lower bound of probability range (inclusive).
        bin_end: Upper bound of probability range (exclusive).
        predicted_mean: Mean predicted probability in this bin.
        actual_frequency: Actual frequency of outcomes in this bin.
        count: Number of predictions falling in this bin.
        deviation: predicted_mean - actual_frequency (signed error).
    """

    bin_start: float
    bin_end: float
    predicted_mean: float
    actual_frequency: float
    count: int
    deviation: float


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Complete calibration evaluation result.

    Attributes:
        status: Whether calibration could be computed.
        brier_score: Mean squared error of probabilities (0=perfect, 1=worst).
        log_loss: Logarithmic loss (lower is better, 0=perfect).
        ece: Expected Calibration Error (0=perfect).
        mce: Maximum Calibration Error across all bins.
        bins: Reliability diagram bin data.
        n_predictions: Total predictions evaluated.
        reason: Explanation if status != VALID.
    """

    status: CalibrationStatus
    brier_score: Optional[float] = None
    log_loss: Optional[float] = None
    ece: Optional[float] = None
    mce: Optional[float] = None
    bins: tuple[CalibrationBin, ...] = ()
    n_predictions: int = 0
    reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Whether calibration metrics are available."""
        return self.status == CalibrationStatus.VALID


class CalibrationEvaluator:
    """Evaluates probability calibration on out-of-sample predictions.

    Usage:
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=20)
        result = evaluator.evaluate(predictions, outcomes)

    Predictions and outcomes MUST come from OUT-OF-SAMPLE data.
    Using in-sample data produces meaningless calibration scores.
    """

    def __init__(
        self,
        n_bins: int = 10,
        min_samples: int = 10,
        min_bin_count: int = 1,
    ) -> None:
        """Initialize calibration evaluator.

        Args:
            n_bins: Number of bins for reliability diagram (default 10).
            min_samples: Minimum total predictions to produce valid calibration.
            min_bin_count: Minimum observations per bin to include it in ECE.
        """
        if n_bins < 2:
            raise ValueError(f"n_bins must be >= 2, got {n_bins}")
        if min_samples < 1:
            raise ValueError(f"min_samples must be >= 1, got {min_samples}")
        self._n_bins = n_bins
        self._min_samples = min_samples
        self._min_bin_count = min_bin_count

    def evaluate(
        self,
        predicted_probabilities: list[float],
        actual_outcomes: list[bool],
    ) -> CalibrationResult:
        """Evaluate calibration of predicted probabilities against outcomes.

        Args:
            predicted_probabilities: Model P(positive outcome) for each prediction.
                Must be in [0, 1].
            actual_outcomes: True if positive outcome occurred, False otherwise.

        Returns:
            CalibrationResult with all metrics.
        """
        n = len(predicted_probabilities)

        if n == 0:
            return CalibrationResult(
                status=CalibrationStatus.NO_PREDICTIONS,
                reason="No predictions to evaluate.",
            )

        if n != len(actual_outcomes):
            return CalibrationResult(
                status=CalibrationStatus.INVALID_INPUT,
                reason=f"Length mismatch: {n} predictions vs {len(actual_outcomes)} outcomes.",
            )

        # Validate probabilities
        for i, p in enumerate(predicted_probabilities):
            if not (0.0 <= p <= 1.0):
                return CalibrationResult(
                    status=CalibrationStatus.INVALID_INPUT,
                    reason=f"Probability at index {i} is {p}, must be in [0, 1].",
                )

        if n < self._min_samples:
            return CalibrationResult(
                status=CalibrationStatus.INSUFFICIENT_SAMPLES,
                n_predictions=n,
                reason=f"Only {n} predictions, need at least {self._min_samples}.",
            )

        # Compute metrics
        brier = self._brier_score(predicted_probabilities, actual_outcomes)
        logloss = self._log_loss(predicted_probabilities, actual_outcomes)
        bins = self._compute_bins(predicted_probabilities, actual_outcomes)
        ece = self._expected_calibration_error(bins, n)
        mce = self._maximum_calibration_error(bins)

        return CalibrationResult(
            status=CalibrationStatus.VALID,
            brier_score=brier,
            log_loss=logloss,
            ece=ece,
            mce=mce,
            bins=tuple(bins),
            n_predictions=n,
        )

    def _brier_score(
        self, predictions: list[float], outcomes: list[bool]
    ) -> float:
        """Compute Brier score: mean((p - y)^2).

        Range: [0, 1] where 0 is perfect.
        """
        n = len(predictions)
        total = 0.0
        for p, y in zip(predictions, outcomes):
            y_val = 1.0 if y else 0.0
            total += (p - y_val) ** 2
        return total / n

    def _log_loss(
        self, predictions: list[float], outcomes: list[bool]
    ) -> float:
        """Compute log loss (cross-entropy).

        log_loss = -1/n * sum(y*log(p) + (1-y)*log(1-p))

        Clips probabilities to avoid log(0).
        """
        eps = 1e-15
        n = len(predictions)
        total = 0.0
        for p, y in zip(predictions, outcomes):
            p_clipped = max(eps, min(1 - eps, p))
            if y:
                total += math.log(p_clipped)
            else:
                total += math.log(1 - p_clipped)
        return -total / n

    def _compute_bins(
        self, predictions: list[float], outcomes: list[bool]
    ) -> list[CalibrationBin]:
        """Compute reliability diagram bins."""
        bin_width = 1.0 / self._n_bins
        bins: list[CalibrationBin] = []

        for b in range(self._n_bins):
            bin_start = b * bin_width
            bin_end = (b + 1) * bin_width

            # Collect predictions in this bin
            bin_preds: list[float] = []
            bin_outcomes: list[bool] = []

            for p, y in zip(predictions, outcomes):
                # Last bin is inclusive on the right: [start, end]
                if b == self._n_bins - 1:
                    in_bin = bin_start <= p <= bin_end
                else:
                    in_bin = bin_start <= p < bin_end

                if in_bin:
                    bin_preds.append(p)
                    bin_outcomes.append(y)

            count = len(bin_preds)
            if count < self._min_bin_count:
                # Empty or insufficient bin
                bins.append(CalibrationBin(
                    bin_start=bin_start,
                    bin_end=bin_end,
                    predicted_mean=bin_start + bin_width / 2,
                    actual_frequency=0.0,
                    count=0,
                    deviation=0.0,
                ))
                continue

            predicted_mean = sum(bin_preds) / count
            actual_freq = sum(bin_outcomes) / count
            deviation = predicted_mean - actual_freq

            bins.append(CalibrationBin(
                bin_start=bin_start,
                bin_end=bin_end,
                predicted_mean=predicted_mean,
                actual_frequency=actual_freq,
                count=count,
                deviation=deviation,
            ))

        return bins

    def _expected_calibration_error(
        self, bins: list[CalibrationBin], n: int
    ) -> float:
        """Compute ECE: weighted average of bin deviations.

        ECE = sum(count_b / n * |predicted_b - actual_b|)

        Only includes bins with count >= min_bin_count.
        """
        if n == 0:
            return 0.0
        ece = 0.0
        for b in bins:
            if b.count >= self._min_bin_count:
                ece += (b.count / n) * abs(b.deviation)
        return ece

    def _maximum_calibration_error(self, bins: list[CalibrationBin]) -> float:
        """Compute MCE: maximum absolute deviation across bins.

        Only includes bins with observations.
        """
        max_dev = 0.0
        for b in bins:
            if b.count >= self._min_bin_count:
                max_dev = max(max_dev, abs(b.deviation))
        return max_dev


# ═══════════════════════════════════════════════════════════════
# MODEL COMPARISON
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ModelComparisonEntry:
    """Calibration metrics for one model in a comparison.

    Attributes:
        model_name: Model identifier.
        brier_score: Lower is better.
        log_loss: Lower is better.
        ece: Lower is better.
        n_predictions: Sample size used.
    """

    model_name: str
    brier_score: float
    log_loss: float
    ece: float
    n_predictions: int


@dataclass(frozen=True, slots=True)
class ModelComparisonResult:
    """Result of comparing multiple models on calibration.

    Attributes:
        entries: Per-model calibration metrics.
        best_brier: Model with lowest Brier score.
        best_log_loss: Model with lowest log loss.
        best_ece: Model with lowest ECE.
    """

    entries: tuple[ModelComparisonEntry, ...]
    best_brier: Optional[str] = None
    best_log_loss: Optional[str] = None
    best_ece: Optional[str] = None


def compare_models(
    models: dict[str, tuple[list[float], list[bool]]],
    n_bins: int = 10,
    min_samples: int = 10,
) -> ModelComparisonResult:
    """Compare multiple models on calibration metrics.

    Args:
        models: Dict of model_name -> (predicted_probabilities, actual_outcomes).
        n_bins: Number of bins for calibration.
        min_samples: Minimum samples for valid calibration.

    Returns:
        ModelComparisonResult with per-model metrics and winners.
    """
    evaluator = CalibrationEvaluator(n_bins=n_bins, min_samples=min_samples)
    entries: list[ModelComparisonEntry] = []

    for model_name, (predictions, outcomes) in models.items():
        result = evaluator.evaluate(predictions, outcomes)
        if result.is_valid:
            entries.append(ModelComparisonEntry(
                model_name=model_name,
                brier_score=result.brier_score,
                log_loss=result.log_loss,
                ece=result.ece,
                n_predictions=result.n_predictions,
            ))

    if not entries:
        return ModelComparisonResult(entries=())

    best_brier = min(entries, key=lambda e: e.brier_score).model_name
    best_log_loss = min(entries, key=lambda e: e.log_loss).model_name
    best_ece = min(entries, key=lambda e: e.ece).model_name

    return ModelComparisonResult(
        entries=tuple(entries),
        best_brier=best_brier,
        best_log_loss=best_log_loss,
        best_ece=best_ece,
    )
