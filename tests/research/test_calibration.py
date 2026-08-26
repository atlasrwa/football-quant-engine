"""Tests for probability calibration metrics.

Tests cover:
- Brier score
- Log loss
- Expected Calibration Error (ECE)
- Maximum Calibration Error (MCE)
- Reliability bins
- Edge cases (empty, insufficient, invalid)
- Model comparison
- Calibration vs ROI distinction (fundamental research principle)
"""

import math

import pytest

from src.research.calibration import (
    CalibrationBin,
    CalibrationEvaluator,
    CalibrationResult,
    CalibrationStatus,
    ModelComparisonEntry,
    ModelComparisonResult,
    compare_models,
)


class TestCalibrationEvaluator:
    """Tests for CalibrationEvaluator."""

    @pytest.fixture
    def evaluator(self):
        return CalibrationEvaluator(n_bins=10, min_samples=5)

    def test_perfect_calibration_brier_zero(self, evaluator):
        """Perfect predictions (0.0 or 1.0) → Brier = 0."""
        predictions = [1.0, 0.0, 1.0, 0.0, 1.0]
        outcomes = [True, False, True, False, True]
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert result.brier_score == 0.0

    def test_worst_calibration_brier_one(self, evaluator):
        """Perfectly wrong predictions → Brier = 1."""
        predictions = [0.0, 1.0, 0.0, 1.0, 0.0]
        outcomes = [True, False, True, False, True]
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert result.brier_score == 1.0

    def test_brier_score_intermediate(self, evaluator):
        """50/50 predictions → Brier = 0.25."""
        predictions = [0.5] * 10
        outcomes = [True] * 5 + [False] * 5
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert abs(result.brier_score - 0.25) < 0.001

    def test_log_loss_perfect(self, evaluator):
        """Near-perfect predictions → log loss near 0."""
        predictions = [0.999, 0.001, 0.999, 0.001, 0.999]
        outcomes = [True, False, True, False, True]
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert result.log_loss < 0.01

    def test_log_loss_worst(self, evaluator):
        """Near-perfectly wrong → high log loss."""
        predictions = [0.001, 0.999, 0.001, 0.999, 0.001]
        outcomes = [True, False, True, False, True]
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert result.log_loss > 5.0

    def test_log_loss_50_50(self, evaluator):
        """0.5 predictions → log loss = log(2) ≈ 0.693."""
        predictions = [0.5] * 10
        outcomes = [True] * 5 + [False] * 5
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert abs(result.log_loss - math.log(2)) < 0.001

    def test_ece_perfect_calibration(self):
        """Well-calibrated predictions → ECE near 0."""
        evaluator = CalibrationEvaluator(n_bins=5, min_samples=5)
        # Predictions at 0.3 with 30% hit rate, 0.7 with 70% hit rate
        predictions = [0.3] * 10 + [0.7] * 10
        outcomes = [True] * 3 + [False] * 7 + [True] * 7 + [False] * 3
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert result.ece < 0.05

    def test_ece_poor_calibration(self):
        """Poorly calibrated predictions → high ECE."""
        evaluator = CalibrationEvaluator(n_bins=5, min_samples=5)
        # Predict 0.9 but only 20% hit rate
        predictions = [0.9] * 10
        outcomes = [True] * 2 + [False] * 8
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert result.ece > 0.5

    def test_mce_is_max_bin_deviation(self):
        """MCE should equal the maximum absolute deviation across bins."""
        evaluator = CalibrationEvaluator(n_bins=5, min_samples=5)
        predictions = [0.3] * 10 + [0.8] * 10
        outcomes = [True] * 3 + [False] * 7 + [True] * 2 + [False] * 8
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        # The 0.8 bin predicts 0.8 but actual is 0.2 → deviation 0.6
        assert result.mce > 0.5

    def test_bins_cover_full_range(self, evaluator):
        """Bins should cover [0, 1] completely."""
        predictions = [i / 20.0 for i in range(20)]
        outcomes = [i % 2 == 0 for i in range(20)]
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        assert len(result.bins) == 10
        assert result.bins[0].bin_start == 0.0
        assert result.bins[-1].bin_end == 1.0

    def test_bin_counts_sum_to_total(self, evaluator):
        """Sum of bin counts should equal total predictions (for occupied bins)."""
        predictions = [0.3, 0.3, 0.7, 0.7, 0.5, 0.5, 0.8, 0.2, 0.9, 0.1]
        outcomes = [True] * 5 + [False] * 5
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        total_in_bins = sum(b.count for b in result.bins)
        assert total_in_bins == 10


class TestCalibrationEdgeCases:
    """Tests for edge cases and error handling."""

    def test_no_predictions(self):
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=5)
        result = evaluator.evaluate([], [])
        assert result.status == CalibrationStatus.NO_PREDICTIONS
        assert not result.is_valid

    def test_insufficient_samples(self):
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=20)
        result = evaluator.evaluate([0.5] * 10, [True] * 5 + [False] * 5)
        assert result.status == CalibrationStatus.INSUFFICIENT_SAMPLES
        assert result.n_predictions == 10

    def test_length_mismatch(self):
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=5)
        result = evaluator.evaluate([0.5] * 10, [True] * 8)
        assert result.status == CalibrationStatus.INVALID_INPUT
        assert "mismatch" in result.reason.lower()

    def test_invalid_probability_above_one(self):
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=5)
        result = evaluator.evaluate([1.5, 0.5, 0.5, 0.5, 0.5], [True] * 5)
        assert result.status == CalibrationStatus.INVALID_INPUT
        assert "index 0" in result.reason

    def test_invalid_probability_below_zero(self):
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=5)
        result = evaluator.evaluate([0.5, -0.1, 0.5, 0.5, 0.5], [True] * 5)
        assert result.status == CalibrationStatus.INVALID_INPUT

    def test_all_same_outcome(self):
        """All True outcomes should still compute valid calibration."""
        evaluator = CalibrationEvaluator(n_bins=10, min_samples=5)
        predictions = [0.8] * 10
        outcomes = [True] * 10
        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid
        # Predicting 0.8 with 100% hit rate → Brier = (0.8-1)^2 = 0.04
        assert abs(result.brier_score - 0.04) < 0.001

    def test_n_bins_minimum(self):
        with pytest.raises(ValueError):
            CalibrationEvaluator(n_bins=1)

    def test_min_samples_minimum(self):
        with pytest.raises(ValueError):
            CalibrationEvaluator(min_samples=0)


class TestModelComparison:
    """Tests for compare_models()."""

    def test_compare_two_models(self):
        """Compare a well-calibrated vs poorly calibrated model."""
        # Model A: well calibrated (predicts 0.6, actual ~60%)
        preds_a = [0.6] * 50
        outcomes_a = [True] * 30 + [False] * 20

        # Model B: poorly calibrated (predicts 0.9, actual ~60%)
        preds_b = [0.9] * 50
        outcomes_b = [True] * 30 + [False] * 20

        result = compare_models(
            {"model_a": (preds_a, outcomes_a), "model_b": (preds_b, outcomes_b)},
            min_samples=10,
        )
        assert len(result.entries) == 2
        assert result.best_brier == "model_a"
        assert result.best_log_loss == "model_a"

    def test_compare_single_model(self):
        result = compare_models(
            {"only_model": ([0.5] * 20, [True] * 10 + [False] * 10)},
            min_samples=10,
        )
        assert len(result.entries) == 1
        assert result.best_brier == "only_model"

    def test_compare_empty(self):
        result = compare_models({}, min_samples=10)
        assert len(result.entries) == 0
        assert result.best_brier is None

    def test_compare_insufficient_data_excluded(self):
        """Models with insufficient data are excluded from comparison."""
        result = compare_models(
            {
                "good": ([0.5] * 20, [True] * 10 + [False] * 10),
                "too_small": ([0.5] * 3, [True, False, True]),
            },
            min_samples=10,
        )
        assert len(result.entries) == 1
        assert result.best_brier == "good"


class TestCalibrationVsROI:
    """Tests proving calibration ≠ profitability.

    FUNDAMENTAL PRINCIPLE:
    - A model with better calibration is NOT automatically more profitable.
    - A high ROI does NOT imply well-calibrated probabilities.
    """

    def test_better_calibration_not_better_roi(self):
        """
        Model A: well-calibrated (predicts 0.6, actual 60%) but no edge vs market
        Model B: poorly calibrated (predicts 0.8, actual 60%) but happens to bet
                 on the right side at good odds

        Model A has better calibration but Model B could have better ROI
        if market odds favor its bets.
        """
        evaluator = CalibrationEvaluator(n_bins=5, min_samples=10)

        # Model A: well calibrated
        preds_a = [0.6] * 20
        outcomes_a = [True] * 12 + [False] * 8  # 60% → matches prediction
        result_a = evaluator.evaluate(preds_a, outcomes_a)

        # Model B: overconfident (predicts 0.8, actual 60%)
        preds_b = [0.8] * 20
        outcomes_b = [True] * 12 + [False] * 8  # 60% → doesn't match prediction
        result_b = evaluator.evaluate(preds_b, outcomes_b)

        # Model A has better Brier score
        assert result_a.brier_score < result_b.brier_score

        # But ROI depends on ODDS, not calibration alone
        # At odds 2.0, Model B would have bet more confidently
        # and could still profit if odds were favorable
        # This test proves the CONCEPTS are separate

    def test_high_roi_does_not_imply_calibration(self):
        """
        A lucky model can have high ROI but terrible calibration.
        Predicts 0.9 always, but only 50% of the time is correct.
        If odds are 3.0, it still profits: 0.5 * 3.0 - 1 = 0.5 (50% ROI)
        But calibration is terrible (predicts 90%, actual 50%).
        """
        evaluator = CalibrationEvaluator(n_bins=5, min_samples=10)

        predictions = [0.9] * 20
        outcomes = [True] * 10 + [False] * 10  # 50% actual

        result = evaluator.evaluate(predictions, outcomes)
        assert result.is_valid

        # Terrible calibration
        assert result.brier_score > 0.15  # (0.9-0.5)^2 avg = 0.16 + ...
        assert result.ece > 0.3  # Large deviation from predicted

        # But at odds 3.0: ROI = 0.5 * 3.0 - 1 = 0.5 (50% profit!)
        # The system MUST NOT select models by ROI alone
        roi = 0.5 * 3.0 - 1.0
        assert roi > 0  # Profitable despite terrible calibration
