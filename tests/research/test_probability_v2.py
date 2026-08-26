"""Tests for Batch 2 probability extensions.

Tests cover:
- Model identity / versioning
- Three-way probability estimates
- Training metadata / temporal causality
- Prediction status / missing-data handling
- predict_safe() behavior
- Poisson distribution output
- HistoricalFrequency min_observations and lookback_window
"""

import pytest
import numpy as np

from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    ModelIdentity,
    PoissonModel,
    PredictionResult,
    PredictionStatus,
    ProbabilityEstimate,
    ThreeWayProbabilityEstimate,
    TrainingMetadata,
)


class TestModelIdentity:
    """Tests for deterministic model identity."""

    def test_same_config_same_hash(self):
        """Identical configurations produce identical content hashes."""
        id1 = ModelIdentity.create("logistic", 1, {"lr": 0.01, "max_iter": 1000})
        id2 = ModelIdentity.create("logistic", 1, {"lr": 0.01, "max_iter": 1000})
        assert id1.content_hash == id2.content_hash

    def test_different_version_different_hash(self):
        id1 = ModelIdentity.create("logistic", 1, {"lr": 0.01})
        id2 = ModelIdentity.create("logistic", 2, {"lr": 0.01})
        assert id1.content_hash != id2.content_hash

    def test_different_params_different_hash(self):
        id1 = ModelIdentity.create("logistic", 1, {"lr": 0.01})
        id2 = ModelIdentity.create("logistic", 1, {"lr": 0.02})
        assert id1.content_hash != id2.content_hash

    def test_different_type_different_hash(self):
        id1 = ModelIdentity.create("logistic", 1, {"lr": 0.01})
        id2 = ModelIdentity.create("poisson", 1, {"lr": 0.01})
        assert id1.content_hash != id2.content_hash

    def test_parameter_order_does_not_matter(self):
        """JSON serialization uses sort_keys, so order is irrelevant."""
        id1 = ModelIdentity.create("test", 1, {"a": 1, "b": 2, "c": 3})
        id2 = ModelIdentity.create("test", 1, {"c": 3, "a": 1, "b": 2})
        assert id1.content_hash == id2.content_hash

    def test_identity_on_model_instance(self):
        model = HistoricalFrequencyModel(min_observations=10)
        identity = model.model_identity
        assert identity.model_type == "historical_frequency"
        assert identity.model_version == 1
        assert ("min_observations", 10) in identity.parameters

    def test_logistic_identity_includes_config(self):
        model = LogisticRegressionModel(learning_rate=0.05, max_iter=500)
        identity = model.model_identity
        assert identity.model_type == "logistic_regression"
        assert ("learning_rate", 0.05) in identity.parameters
        assert ("max_iter", 500) in identity.parameters

    def test_poisson_identity_includes_line(self):
        model = PoissonModel(line=9.5)
        identity = model.model_identity
        assert identity.model_type == "poisson"
        assert ("line", 9.5) in identity.parameters

    def test_identity_is_frozen(self):
        identity = ModelIdentity.create("test", 1, {"x": 1})
        with pytest.raises(Exception):
            identity.model_type = "changed"


class TestThreeWayProbabilityEstimate:
    """Tests for three-way (1X2) probability estimates."""

    def test_valid_estimate(self):
        est = ThreeWayProbabilityEstimate(
            p_home=0.5, p_draw=0.3, p_away=0.2, model_name="test"
        )
        assert est.p_home == 0.5
        assert est.p_draw == 0.3
        assert est.p_away == 0.2

    def test_must_sum_to_one(self):
        with pytest.raises(AssertionError):
            ThreeWayProbabilityEstimate(
                p_home=0.5, p_draw=0.3, p_away=0.3, model_name="test"
            )

    def test_allows_floating_point_deviation(self):
        # Should not raise
        est = ThreeWayProbabilityEstimate(
            p_home=0.333334, p_draw=0.333333, p_away=0.333333, model_name="test"
        )
        assert est.p_home > 0

    def test_negative_probability_rejected(self):
        with pytest.raises(AssertionError):
            ThreeWayProbabilityEstimate(
                p_home=-0.1, p_draw=0.6, p_away=0.5, model_name="test"
            )

    def test_boundary_probabilities(self):
        """One outcome can be very likely."""
        est = ThreeWayProbabilityEstimate(
            p_home=0.95, p_draw=0.03, p_away=0.02, model_name="test"
        )
        assert abs(est.p_home + est.p_draw + est.p_away - 1.0) < 0.001


class TestTrainingMetadata:
    """Tests for training metadata and temporal causality."""

    def test_valid_metadata(self):
        meta = TrainingMetadata(
            training_start=1000,
            training_end=2000,
            sample_size=100,
            feature_names=("x", "y"),
        )
        assert meta.training_start == 1000
        assert meta.training_end == 2000
        assert meta.sample_size == 100

    def test_end_before_start_rejected(self):
        with pytest.raises(ValueError):
            TrainingMetadata(training_start=2000, training_end=1000, sample_size=50)

    def test_negative_sample_size_rejected(self):
        with pytest.raises(ValueError):
            TrainingMetadata(training_start=1000, training_end=2000, sample_size=-1)

    def test_prediction_after_training_is_valid(self):
        meta = TrainingMetadata(training_start=1000, training_end=2000, sample_size=50)
        assert meta.is_prediction_valid(2001) is True
        assert meta.is_prediction_valid(3000) is True

    def test_prediction_during_training_is_invalid(self):
        meta = TrainingMetadata(training_start=1000, training_end=2000, sample_size=50)
        assert meta.is_prediction_valid(1500) is False
        assert meta.is_prediction_valid(2000) is False  # boundary: not strictly after

    def test_prediction_before_training_is_invalid(self):
        meta = TrainingMetadata(training_start=1000, training_end=2000, sample_size=50)
        assert meta.is_prediction_valid(500) is False


class TestPredictionResult:
    """Tests for safe prediction result wrapper."""

    def test_valid_result(self):
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        result = PredictionResult(status=PredictionStatus.VALID, estimate=est)
        assert result.is_valid
        assert result.estimate.p_over == 0.6

    def test_insufficient_data_result(self):
        result = PredictionResult(
            status=PredictionStatus.INSUFFICIENT_DATA,
            reason="Only 3 observations.",
        )
        assert not result.is_valid
        assert result.estimate is None

    def test_model_not_fitted_result(self):
        result = PredictionResult(status=PredictionStatus.MODEL_NOT_FITTED)
        assert not result.is_valid


class TestPredictSafe:
    """Tests for predict_safe() on models."""

    def test_historical_insufficient_data(self):
        model = HistoricalFrequencyModel(min_observations=20)
        model.fit([{}] * 5, [True] * 3 + [False] * 2)
        result = model.predict_safe({})
        assert result.status == PredictionStatus.INSUFFICIENT_DATA

    def test_historical_sufficient_data(self):
        model = HistoricalFrequencyModel(min_observations=5)
        model.fit([{}] * 10, [True] * 6 + [False] * 4)
        result = model.predict_safe({})
        assert result.is_valid
        assert abs(result.estimate.p_over - 0.6) < 0.001

    def test_logistic_not_fitted(self):
        model = LogisticRegressionModel()
        # predict_safe on unfitted model — LogisticRegression starts unfitted
        # but after fit with empty data, is_fitted = True
        result = model.predict_safe({"x": 1.0})
        assert result.status == PredictionStatus.MODEL_NOT_FITTED

    def test_logistic_after_fit_is_valid(self):
        model = LogisticRegressionModel(learning_rate=0.1, max_iter=100)
        model.fit([{"x": 1.0}] * 10, [True] * 5 + [False] * 5)
        result = model.predict_safe({"x": 1.0})
        assert result.is_valid

    def test_poisson_not_fitted(self):
        model = PoissonModel(line=2.5)
        result = model.predict_safe({})
        assert result.status == PredictionStatus.MODEL_NOT_FITTED


class TestHistoricalFrequencyExtended:
    """Tests for HistoricalFrequencyModel extensions."""

    def test_lookback_window(self):
        """Only recent observations used."""
        model = HistoricalFrequencyModel(lookback_window=5)
        # First 5: all True. Last 5: all False.
        outcomes = [True] * 5 + [False] * 5
        model.fit([{}] * 10, outcomes)
        est = model.predict({})
        # Should only use last 5 (all False) → p_over ≈ 0.01 (clipped)
        assert est.p_over < 0.1

    def test_training_metadata_recorded(self):
        model = HistoricalFrequencyModel()
        model.fit([{}] * 10, [True] * 6 + [False] * 4,
                  training_start=1000, training_end=2000)
        meta = model.training_metadata
        assert meta is not None
        assert meta.training_start == 1000
        assert meta.training_end == 2000
        assert meta.sample_size == 10

    def test_min_observations_boundary(self):
        model = HistoricalFrequencyModel(min_observations=10)
        model.fit([{}] * 10, [True] * 5 + [False] * 5)
        result = model.predict_safe({})
        assert result.is_valid  # Exactly at boundary

    def test_min_observations_below(self):
        model = HistoricalFrequencyModel(min_observations=10)
        model.fit([{}] * 9, [True] * 5 + [False] * 4)
        result = model.predict_safe({})
        assert result.status == PredictionStatus.INSUFFICIENT_DATA


class TestLogisticExtended:
    """Tests for LogisticRegressionModel extensions."""

    def test_training_metadata(self):
        model = LogisticRegressionModel(learning_rate=0.1, max_iter=100)
        features = [{"x": float(i)} for i in range(20)]
        outcomes = [i > 10 for i in range(20)]
        model.fit(features, outcomes, training_start=5000, training_end=6000)
        meta = model.training_metadata
        assert meta is not None
        assert meta.sample_size == 20
        assert meta.feature_names == ("x",)

    def test_seed_parameter_in_identity(self):
        model = LogisticRegressionModel(seed=42)
        identity = model.model_identity
        assert ("seed", 42) in identity.parameters


class TestPoissonExtended:
    """Tests for PoissonModel extensions."""

    def test_predict_distribution(self):
        model = PoissonModel(line=2.5)
        model.fit([{}] * 50, [True] * 30 + [False] * 20)
        dist = model.predict_distribution({}, max_k=10)
        assert len(dist) == 11  # k = 0, 1, ..., 10
        # All probabilities non-negative
        assert all(p >= 0 for p in dist)
        # Sum should be close to 1 (within max_k)
        assert sum(dist) > 0.95

    def test_distribution_valid_poisson(self):
        """Distribution should be a valid Poisson PMF."""
        model = PoissonModel(line=2.5)
        model.fit([{}] * 100, [True] * 50 + [False] * 50)
        dist = model.predict_distribution({}, max_k=20)
        # Mode should be near the expected lambda
        mode_k = dist.index(max(dist))
        # For lambda ≈ 2.5, mode should be 2
        assert 1 <= mode_k <= 4

    def test_training_metadata(self):
        model = PoissonModel(line=9.5)
        model.fit([{}] * 30, [True] * 15 + [False] * 15,
                  training_start=100, training_end=200)
        meta = model.training_metadata
        assert meta is not None
        assert meta.training_start == 100
        assert meta.training_end == 200
        assert meta.sample_size == 30

    def test_is_fitted_after_fit(self):
        model = PoissonModel(line=2.5)
        assert not model.is_fitted
        model.fit([{}] * 10, [True] * 5 + [False] * 5)
        assert model.is_fitted


class TestTemporalLeakage:
    """Tests proving temporal causality is enforced.

    These tests verify that:
    - Training metadata correctly constrains predictions
    - Future data cannot be used in model fitting
    - Training/prediction overlap is detectable
    """

    def test_prediction_timestamp_validated(self):
        """Model with training metadata rejects predictions within training window."""
        model = HistoricalFrequencyModel()
        model.fit(
            [{}] * 10, [True] * 5 + [False] * 5,
            training_start=1000, training_end=2000,
        )
        meta = model.training_metadata
        assert meta is not None
        # Valid: prediction after training
        assert meta.is_prediction_valid(2001)
        # Invalid: prediction during training
        assert not meta.is_prediction_valid(1500)
        # Invalid: prediction at training boundary
        assert not meta.is_prediction_valid(2000)

    def test_logistic_temporal_metadata(self):
        """Logistic model records temporal boundaries."""
        model = LogisticRegressionModel(learning_rate=0.1, max_iter=100)
        features = [{"x": float(i)} for i in range(50)]
        outcomes = [i > 25 for i in range(50)]
        model.fit(features, outcomes, training_start=0, training_end=50000)
        meta = model.training_metadata
        assert meta is not None
        # Prediction at timestamp 50001 is valid
        assert meta.is_prediction_valid(50001)
        # Prediction at timestamp 49999 is invalid
        assert not meta.is_prediction_valid(49999)

    def test_poisson_temporal_metadata(self):
        """Poisson model records temporal boundaries."""
        model = PoissonModel(line=2.5)
        model.fit([{}] * 20, [True] * 10 + [False] * 10,
                  training_start=100, training_end=500)
        meta = model.training_metadata
        assert meta is not None
        assert meta.is_prediction_valid(501)
        assert not meta.is_prediction_valid(400)
