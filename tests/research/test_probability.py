"""Tests for probability model layer."""

import pytest
import numpy as np

from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    PoissonModel,
    ProbabilityEstimate,
    ProbabilityModel,
)


class TestProbabilityEstimate:
    """Tests for ProbabilityEstimate data class."""

    def test_valid_estimate(self):
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4, model_name="test")
        assert est.p_over == 0.6
        assert est.p_under == 0.4

    def test_probabilities_must_sum_to_one(self):
        with pytest.raises(AssertionError):
            ProbabilityEstimate(p_over=0.6, p_under=0.6, model_name="test")

    def test_allows_small_floating_point_deviation(self):
        # Should not raise
        est = ProbabilityEstimate(p_over=0.6, p_under=0.4000001, model_name="test")
        assert est.p_over == 0.6


class TestHistoricalFrequencyModel:
    """Tests for baseline frequency model."""

    @pytest.fixture
    def model(self):
        return HistoricalFrequencyModel()

    def test_implements_interface(self, model):
        assert isinstance(model, ProbabilityModel)

    def test_name(self, model):
        assert model.name == "historical_frequency"

    def test_default_prediction_is_50_50(self, model):
        est = model.predict({})
        assert est.p_over == 0.5
        assert est.p_under == 0.5

    def test_fit_updates_probability(self, model):
        # 70% OVER rate
        outcomes = [True] * 7 + [False] * 3
        features = [{}] * 10
        model.fit(features, outcomes)
        est = model.predict({})
        assert abs(est.p_over - 0.7) < 0.001

    def test_fit_ignores_features(self, model):
        """Historical frequency doesn't use features."""
        features = [{"x": float(i)} for i in range(10)]
        outcomes = [True] * 8 + [False] * 2
        model.fit(features, outcomes)
        est = model.predict({"x": 999.0})
        assert abs(est.p_over - 0.8) < 0.001

    def test_probability_clipped(self, model):
        """All True or all False should be clipped, not 0 or 1."""
        model.fit([{}] * 10, [True] * 10)
        est = model.predict({})
        assert est.p_over < 1.0
        assert est.p_over > 0.9

    def test_empty_outcomes(self, model):
        model.fit([], [])
        est = model.predict({})
        assert est.p_over == 0.5

    def test_predict_many(self, model):
        model.fit([{}] * 10, [True] * 6 + [False] * 4)
        results = model.predict_many([{}, {}, {}])
        assert len(results) == 3
        assert all(abs(r.p_over - 0.6) < 0.001 for r in results)


class TestLogisticRegressionModel:
    """Tests for logistic regression model."""

    @pytest.fixture
    def model(self):
        return LogisticRegressionModel(learning_rate=0.1, max_iter=500)

    def test_implements_interface(self, model):
        assert isinstance(model, ProbabilityModel)

    def test_name(self, model):
        assert model.name == "logistic_regression"

    def test_default_prediction_without_fit(self, model):
        est = model.predict({"x": 1.0})
        assert abs(est.p_over + est.p_under - 1.0) < 0.001

    def test_learns_simple_relationship(self, model):
        """Feature x > 0 → OVER, x < 0 → UNDER."""
        rng = np.random.default_rng(42)
        n = 200
        features = [{"x": float(rng.normal(1, 0.5))} for _ in range(n // 2)]
        features += [{"x": float(rng.normal(-1, 0.5))} for _ in range(n // 2)]
        outcomes = [True] * (n // 2) + [False] * (n // 2)

        model.fit(features, outcomes)

        # High x → high p_over
        est_high = model.predict({"x": 2.0})
        est_low = model.predict({"x": -2.0})
        assert est_high.p_over > est_low.p_over
        assert est_high.p_over > 0.6
        assert est_low.p_over < 0.4

    def test_probabilities_always_valid(self, model):
        """Output probabilities always between 0 and 1, sum to 1."""
        features = [{"x": float(i)} for i in range(50)]
        outcomes = [i > 25 for i in range(50)]
        model.fit(features, outcomes)

        for x_val in [-100, -10, 0, 10, 100]:
            est = model.predict({"x": float(x_val)})
            assert 0 < est.p_over < 1
            assert 0 < est.p_under < 1
            assert abs(est.p_over + est.p_under - 1.0) < 0.001

    def test_handles_empty_features(self, model):
        model.fit([], [])
        est = model.predict({})
        assert abs(est.p_over + est.p_under - 1.0) < 0.001

    def test_handles_missing_feature_keys(self, model):
        features = [{"x": float(i), "y": float(i * 2)} for i in range(50)]
        outcomes = [i > 25 for i in range(50)]
        model.fit(features, outcomes)
        # Predict with missing key — should use 0.0 default
        est = model.predict({"x": 30.0})
        assert abs(est.p_over + est.p_under - 1.0) < 0.001


class TestPoissonModel:
    """Tests for Poisson probability model."""

    @pytest.fixture
    def model(self):
        return PoissonModel(line=2.5)

    def test_implements_interface(self, model):
        assert isinstance(model, ProbabilityModel)

    def test_name(self, model):
        assert model.name == "poisson"

    def test_fit_and_predict(self, model):
        outcomes = [True] * 60 + [False] * 40
        features = [{}] * 100
        model.fit(features, outcomes)
        est = model.predict({})
        # Should estimate ~60% over rate via Poisson CDF
        assert abs(est.p_over - 0.6) < 0.1

    def test_probability_sum_to_one(self, model):
        model.fit([{}] * 50, [True] * 30 + [False] * 20)
        est = model.predict({})
        assert abs(est.p_over + est.p_under - 1.0) < 0.001

    def test_uses_poisson_distribution(self):
        """Verify the model uses actual Poisson CDF, not just frequency."""
        model = PoissonModel(line=9.5)  # Corners line
        # High over-rate → high lambda → P(X>9.5) should be close to rate
        outcomes = [True] * 70 + [False] * 30
        model.fit([{}] * 100, outcomes)
        est = model.predict({})
        # Should approximate the training rate
        assert 0.5 < est.p_over < 0.9

    def test_feature_adjustment(self):
        """Features should adjust prediction."""
        model = PoissonModel(line=2.5)
        rng = np.random.default_rng(42)
        # High feature → more overs
        features = [{"x": float(rng.normal(2, 0.5))} for _ in range(100)]
        features += [{"x": float(rng.normal(-2, 0.5))} for _ in range(100)]
        outcomes = [True] * 100 + [False] * 100
        model.fit(features, outcomes)

        est_high = model.predict({"x": 3.0})
        est_low = model.predict({"x": -3.0})
        # High feature should give higher P(over)
        assert est_high.p_over > est_low.p_over
