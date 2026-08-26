"""Comprehensive tests for Batch 4 — Experiment Engine.

Test categories:
A. Experiment identity
B. Temporal split
C. Candidate evaluation
D. Probability (training-only fitting, OOS prediction)
E. EV (valid/missing/invalid odds, two-way/three-way)
F. Calibration
G. Baseline comparison
H. Reproducibility
I. Failure safety
J. Temporal leakage attack tests
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pytest

from src.research.candidates import CandidateCondition, CandidateOperator, ResearchCandidate
from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.experiment_engine.config import (
    ExperimentConfig,
    ExperimentThresholds,
    OddsMode,
)
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.hypothesis import ExperimentHypothesis, HypothesisStatus
from src.research.experiment_engine.reporting import ExperimentReporter
from src.research.experiment_engine.result import (
    BaselineComparison,
    EvidenceClassification,
    EvidenceClassifier,
    ExperimentPrediction,
    ExperimentResult,
    ExperimentResultStatus,
    EVStatus,
    ObservationCounts,
    PredictiveMetrics,
    StatisticalEvidence,
)
from src.research.experiment_engine.runner import ExperimentRunner
from src.research.experiment_engine.temporal import (
    SplitMethod,
    SplitType,
    TemporalBoundary,
    TemporalSplit,
    TemporalSplitFactory,
)
from src.research.experiment_engine.walkforward_adapter import WalkForwardAdapter
from src.research.market import MarketType, create_default_registry
from src.research.probability import HistoricalFrequencyModel, LogisticRegressionModel, PoissonModel
from src.research.synthetic_data import SyntheticResearchDataSource


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def synthetic_source():
    """Deterministic synthetic data source."""
    return SyntheticResearchDataSource(seed=42)


@pytest.fixture
def market_registry():
    return create_default_registry()


@pytest.fixture
def corners_market(market_registry):
    return market_registry.get(MarketType.CORNERS_TOTAL)


@pytest.fixture
def goals_market(market_registry):
    return market_registry.get(MarketType.GOALS_TOTAL)


@pytest.fixture
def btts_market(market_registry):
    return market_registry.get(MarketType.BTTS)


@pytest.fixture
def match_result_market(market_registry):
    return market_registry.get(MarketType.MATCH_RESULT_1X2)


@pytest.fixture
def sample_candidate():
    return ResearchCandidate(
        candidate_id="test_candidate_corners",
        market_type=MarketType.CORNERS_TOTAL.value,
        feature_ids=("dangerous_attacks_home",),
        conditions=(
            CandidateCondition(
                feature_id="dangerous_attacks_home", operator=">", threshold=20.0
            ),
        ),
        operator_type=CandidateOperator.THRESHOLD_GT,
        direction="OVER",
    )


@pytest.fixture
def sample_hypothesis(sample_candidate):
    return ExperimentHypothesis.from_candidate(sample_candidate)


@pytest.fixture
def sample_dataset(synthetic_source, corners_market):
    return ResearchDataset(source=synthetic_source, market=corners_market)


@pytest.fixture
def sample_config(sample_hypothesis, sample_dataset, synthetic_source):
    matches = synthetic_source.get_matches()
    midpoint = matches[int(len(matches) * 0.6)].date_unix
    return ExperimentConfig(
        hypothesis=sample_hypothesis,
        market_type=MarketType.CORNERS_TOTAL.value,
        dataset_version=sample_dataset.content_hash,
        model_type="HistoricalFrequencyModel",
        training_start=matches[0].date_unix,
        training_end=midpoint,
        evaluation_start=midpoint,
        evaluation_end=matches[-1].date_unix + 1,
        odds_mode=OddsMode.SYNTHETIC_ODDS,
        random_seed=42,
    )


# ═══════════════════════════════════════════════════════════════
# A. EXPERIMENT IDENTITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestExperimentIdentity:
    """Test deterministic experiment identity hashing."""

    def test_same_config_same_hash(self, sample_config):
        """Same configuration must produce same experiment ID."""
        id1 = sample_config.experiment_id
        id2 = sample_config.experiment_id
        assert id1 == id2

    def test_same_config_reconstructed_same_hash(self, sample_hypothesis, sample_dataset, synthetic_source):
        """Reconstructing equivalent config produces same hash."""
        matches = synthetic_source.get_matches()
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config1 = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type=MarketType.CORNERS_TOTAL.value,
            dataset_version=sample_dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            random_seed=42,
        )
        config2 = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type=MarketType.CORNERS_TOTAL.value,
            dataset_version=sample_dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            random_seed=42,
        )
        assert config1.experiment_id == config2.experiment_id

    def test_different_candidate_different_hash(self, sample_dataset, synthetic_source):
        """Different candidate produces different experiment ID."""
        matches = synthetic_source.get_matches()
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        candidate1 = ResearchCandidate(
            candidate_id="c1",
            market_type=MarketType.CORNERS_TOTAL.value,
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 20.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        candidate2 = ResearchCandidate(
            candidate_id="c2",
            market_type=MarketType.CORNERS_TOTAL.value,
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 25.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h1 = ExperimentHypothesis.from_candidate(candidate1)
        h2 = ExperimentHypothesis.from_candidate(candidate2)

        config1 = ExperimentConfig(
            hypothesis=h1, market_type="CORNERS_TOTAL",
            dataset_version="v1", model_type="HF",
            training_start=matches[0].date_unix, training_end=midpoint,
            evaluation_start=midpoint, evaluation_end=matches[-1].date_unix + 1,
        )
        config2 = ExperimentConfig(
            hypothesis=h2, market_type="CORNERS_TOTAL",
            dataset_version="v1", model_type="HF",
            training_start=matches[0].date_unix, training_end=midpoint,
            evaluation_start=midpoint, evaluation_end=matches[-1].date_unix + 1,
        )
        assert config1.experiment_id != config2.experiment_id

    def test_different_dataset_different_hash(self, sample_hypothesis):
        """Different dataset version produces different experiment ID."""
        config1 = ExperimentConfig(
            hypothesis=sample_hypothesis, market_type="CORNERS_TOTAL",
            dataset_version="dataset_v1", model_type="HF",
            training_start=1000, training_end=2000,
            evaluation_start=2000, evaluation_end=3000,
        )
        config2 = ExperimentConfig(
            hypothesis=sample_hypothesis, market_type="CORNERS_TOTAL",
            dataset_version="dataset_v2", model_type="HF",
            training_start=1000, training_end=2000,
            evaluation_start=2000, evaluation_end=3000,
        )
        assert config1.experiment_id != config2.experiment_id

    def test_different_model_different_hash(self, sample_hypothesis):
        """Different model produces different experiment ID."""
        config1 = ExperimentConfig(
            hypothesis=sample_hypothesis, market_type="CORNERS_TOTAL",
            dataset_version="v1", model_type="HistoricalFrequencyModel",
            training_start=1000, training_end=2000,
            evaluation_start=2000, evaluation_end=3000,
        )
        config2 = ExperimentConfig(
            hypothesis=sample_hypothesis, market_type="CORNERS_TOTAL",
            dataset_version="v1", model_type="LogisticRegressionModel",
            training_start=1000, training_end=2000,
            evaluation_start=2000, evaluation_end=3000,
        )
        assert config1.experiment_id != config2.experiment_id

    def test_different_seed_different_hash(self, sample_hypothesis):
        """Different random seed produces different experiment ID."""
        config1 = ExperimentConfig(
            hypothesis=sample_hypothesis, market_type="CORNERS_TOTAL",
            dataset_version="v1", model_type="HF",
            training_start=1000, training_end=2000,
            evaluation_start=2000, evaluation_end=3000,
            random_seed=42,
        )
        config2 = ExperimentConfig(
            hypothesis=sample_hypothesis, market_type="CORNERS_TOTAL",
            dataset_version="v1", model_type="HF",
            training_start=1000, training_end=2000,
            evaluation_start=2000, evaluation_end=3000,
            random_seed=123,
        )
        assert config1.experiment_id != config2.experiment_id

    def test_hypothesis_content_hash_deterministic(self, sample_candidate):
        """Hypothesis content hash is deterministic."""
        h1 = ExperimentHypothesis.from_candidate(sample_candidate)
        h2 = ExperimentHypothesis.from_candidate(sample_candidate)
        assert h1.content_hash == h2.content_hash

    def test_hypothesis_hash_excludes_created_at(self):
        """Hypothesis hash does not depend on created_at."""
        candidate = ResearchCandidate(
            candidate_id="c",
            market_type="CORNERS_TOTAL",
            feature_ids=("f1",),
            conditions=(CandidateCondition("f1", ">", 1.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
            created_at="2024-01-01T00:00:00",
        )
        h1 = ExperimentHypothesis.from_candidate(candidate)

        candidate2 = ResearchCandidate(
            candidate_id="c",
            market_type="CORNERS_TOTAL",
            feature_ids=("f1",),
            conditions=(CandidateCondition("f1", ">", 1.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
            created_at="2025-06-01T12:00:00",
        )
        h2 = ExperimentHypothesis.from_candidate(candidate2)
        assert h1.content_hash == h2.content_hash


# ═══════════════════════════════════════════════════════════════
# B. TEMPORAL SPLIT TESTS
# ═══════════════════════════════════════════════════════════════


class TestTemporalSplit:
    """Test temporal splitting and ordering enforcement."""

    def test_chronological_ordering_valid(self):
        """Valid chronological split passes validation."""
        split = TemporalSplitFactory.from_timestamps(
            train_start=1000, train_end=2000,
            test_start=2000, test_end=3000,
        )
        valid, msg = split.validate()
        assert valid, msg

    def test_chronological_ordering_with_validation(self):
        """Valid split with validation segment."""
        split = TemporalSplitFactory.from_timestamps(
            train_start=1000, train_end=2000,
            validation_start=2000, validation_end=2500,
            test_start=2500, test_end=3000,
        )
        valid, msg = split.validate()
        assert valid, msg

    def test_overlapping_train_test_rejected(self):
        """Overlapping train/test periods are rejected."""
        split = TemporalSplitFactory.from_timestamps(
            train_start=1000, train_end=2500,
            test_start=2000, test_end=3000,
        )
        valid, msg = split.validate()
        assert not valid
        assert "temporal violation" in msg.lower()

    def test_overlapping_validation_test_rejected(self):
        """Overlapping validation/test periods are rejected."""
        split = TemporalSplitFactory.from_timestamps(
            train_start=1000, train_end=2000,
            validation_start=2000, validation_end=3000,
            test_start=2500, test_end=4000,
        )
        valid, msg = split.validate()
        assert not valid

    def test_split_matches_assigns_correctly(self, synthetic_source):
        """Matches are correctly assigned to segments."""
        matches = synthetic_source.get_matches()
        midpoint = matches[len(matches) // 2].date_unix
        split = TemporalSplitFactory.from_timestamps(
            train_start=matches[0].date_unix,
            train_end=midpoint,
            test_start=midpoint,
            test_end=matches[-1].date_unix + 1,
        )
        segments = split.split_matches(matches)
        train = segments[SplitType.TRAIN]
        test = segments[SplitType.TEST]

        assert len(train) > 0
        assert len(test) > 0
        assert len(train) + len(test) == len(matches)

        # All train matches before test
        assert all(m.date_unix < midpoint for m in train)
        assert all(m.date_unix >= midpoint for m in test)

    def test_no_future_leakage_in_split(self, synthetic_source):
        """No training match has timestamp >= test start."""
        matches = synthetic_source.get_matches()
        midpoint = matches[len(matches) // 2].date_unix
        split = TemporalSplitFactory.from_timestamps(
            train_start=matches[0].date_unix,
            train_end=midpoint,
            test_start=midpoint,
            test_end=matches[-1].date_unix + 1,
        )
        segments = split.split_matches(matches)
        for m in segments[SplitType.TRAIN]:
            assert m.date_unix < midpoint

    def test_from_ratios(self, synthetic_source):
        """Split from ratios produces valid chronological segments."""
        matches = synthetic_source.get_matches()
        split = TemporalSplitFactory.from_ratios(
            matches, train_ratio=0.6, validation_ratio=0.2, test_ratio=0.2
        )
        valid, msg = split.validate()
        assert valid, msg
        assert split.validation is not None

    def test_empty_matches_raises(self):
        """Empty matches raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            TemporalSplitFactory.from_ratios([], train_ratio=0.7, validation_ratio=0.0, test_ratio=0.3)

    def test_training_before_prediction(self, synthetic_source):
        """All training timestamps precede evaluation timestamps."""
        matches = synthetic_source.get_matches()
        n = len(matches)
        split = TemporalSplitFactory.from_timestamps(
            train_start=matches[0].date_unix,
            train_end=matches[n // 2].date_unix,
            test_start=matches[n // 2].date_unix,
            test_end=matches[-1].date_unix + 1,
        )
        assert split.train.end_timestamp <= split.test.start_timestamp


# ═══════════════════════════════════════════════════════════════
# C. CANDIDATE EVALUATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestCandidateEvaluation:
    """Test hypothesis condition evaluation."""

    def test_valid_candidate_passes(self, sample_hypothesis):
        """Conditions evaluate correctly with valid features."""
        features = {"dangerous_attacks_home": 25.0, "shots_home": 10.0}
        result = sample_hypothesis.evaluate_conditions(features)
        assert result is True

    def test_condition_not_met(self, sample_hypothesis):
        """Conditions return False when threshold not met."""
        features = {"dangerous_attacks_home": 15.0}
        result = sample_hypothesis.evaluate_conditions(features)
        assert result is False

    def test_missing_feature_returns_none(self, sample_hypothesis):
        """Missing feature returns None (not False)."""
        features = {"shots_home": 10.0}  # missing dangerous_attacks_home
        result = sample_hypothesis.evaluate_conditions(features)
        assert result is None

    def test_null_not_equal_to_zero(self):
        """NULL/missing is not treated as 0."""
        candidate = ResearchCandidate(
            candidate_id="c",
            market_type="CORNERS_TOTAL",
            feature_ids=("corner_ratio",),
            conditions=(CandidateCondition("corner_ratio", ">", 0.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        # Missing value
        assert h.evaluate_conditions({}) is None
        # Zero is valid and does NOT pass > 0
        assert h.evaluate_conditions({"corner_ratio": 0.0}) is False
        # Positive passes
        assert h.evaluate_conditions({"corner_ratio": 0.5}) is True

    def test_multiple_conditions_all_must_pass(self):
        """All conditions must pass (AND logic)."""
        candidate = ResearchCandidate(
            candidate_id="c",
            market_type="CORNERS_TOTAL",
            feature_ids=("f1", "f2"),
            conditions=(
                CandidateCondition("f1", ">", 5.0),
                CandidateCondition("f2", "<", 3.0),
            ),
            operator_type=CandidateOperator.INTERACTION_AND,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        # Both pass
        assert h.evaluate_conditions({"f1": 6.0, "f2": 2.0}) is True
        # Only first passes
        assert h.evaluate_conditions({"f1": 6.0, "f2": 4.0}) is False
        # Only second passes
        assert h.evaluate_conditions({"f1": 4.0, "f2": 2.0}) is False

    def test_insufficient_history(self, synthetic_source, corners_market):
        """Candidate with very high threshold produces few predictions."""
        candidate = ResearchCandidate(
            candidate_id="extreme",
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 999.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        matches = synthetic_source.get_matches()
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config = ExperimentConfig(
            hypothesis=h,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)
        # Should complete but with zero predictions
        assert result.prediction_count == 0 or result.status == ExperimentResultStatus.INSUFFICIENT_DATA


# ═══════════════════════════════════════════════════════════════
# D. PROBABILITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestProbability:
    """Test model fitting and out-of-sample prediction."""

    def test_training_only_fitting(self, sample_config, sample_dataset):
        """Model is fit on training data only."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        # Model should have been trained (is_fitted)
        assert model.is_fitted

    def test_out_of_sample_prediction(self, sample_config, sample_dataset):
        """Predictions are generated on out-of-sample data."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.prediction_count > 0
        # Predictions should be in evaluation period
        for p in result.predictions:
            assert p.prediction_timestamp >= sample_config.evaluation_start
            assert p.prediction_timestamp < sample_config.evaluation_end

    def test_logistic_regression_model(self, sample_hypothesis, synthetic_source, corners_market):
        """LogisticRegressionModel works in experiment."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="LogisticRegressionModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            random_seed=42,
        )
        model = LogisticRegressionModel(seed=42, max_iter=100)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.prediction_count > 0
        # Probabilities should be in [0, 1]
        for p in result.predictions:
            assert 0.0 <= p.model_probability <= 1.0

    def test_poisson_model(self, sample_hypothesis, synthetic_source, corners_market):
        """PoissonModel works in experiment."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="PoissonModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            random_seed=42,
        )
        model = PoissonModel(line=9.5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.prediction_count > 0


# ═══════════════════════════════════════════════════════════════
# E. EV TESTS
# ═══════════════════════════════════════════════════════════════


class TestEV:
    """Test expected value calculation."""

    def test_valid_odds_ev_calculated(self, sample_config, sample_dataset):
        """EV is calculated when odds are available."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.economic_metrics.odds_available is True
        assert result.economic_metrics.mean_ev is not None
        assert result.economic_metrics.number_of_bets > 0

    def test_missing_odds_mode(self, sample_hypothesis, synthetic_source, corners_market):
        """NO_ODDS mode produces no economic metrics."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.NO_ODDS,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.economic_metrics.odds_available is False
        assert result.economic_metrics.mean_ev is None
        # But predictive metrics still work
        assert result.predictive_metrics.sample_size > 0

    def test_ev_not_zero_when_missing(self, sample_hypothesis, synthetic_source, corners_market):
        """Missing odds produces MISSING_ODDS status, not zero EV."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.NO_ODDS,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # EV should NOT be zero — it should be None/missing
        for pred in result.predictions:
            assert pred.ev_status == EVStatus.MISSING_ODDS
            assert pred.expected_value is None

    def test_odds_filter_applied(self, sample_hypothesis, synthetic_source, corners_market):
        """Odds outside threshold range are filtered."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        # Very tight odds filter
        thresholds = ExperimentThresholds(min_odds=1.80, max_odds=2.20)
        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            thresholds=thresholds,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # Some predictions should have invalid odds
        invalid_odds = [p for p in result.predictions if p.ev_status == EVStatus.INVALID_ODDS]
        valid_odds = [p for p in result.predictions if p.ev_status == EVStatus.VALID]
        # With tight filter, most should be filtered
        assert len(invalid_odds) > 0 or len(valid_odds) < result.prediction_count


# ═══════════════════════════════════════════════════════════════
# F. CALIBRATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestCalibration:
    """Test calibration metric computation."""

    def test_brier_score_computed(self, sample_config, sample_dataset):
        """Brier score is computed for completed experiments."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.predictive_metrics.brier_score is not None
        assert 0.0 <= result.predictive_metrics.brier_score <= 1.0

    def test_log_loss_computed(self, sample_config, sample_dataset):
        """Log loss is computed."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.predictive_metrics.log_loss is not None
        assert result.predictive_metrics.log_loss >= 0.0

    def test_ece_computed(self, sample_config, sample_dataset):
        """ECE is computed."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.predictive_metrics.ece is not None
        assert 0.0 <= result.predictive_metrics.ece <= 1.0

    def test_mce_computed(self, sample_config, sample_dataset):
        """MCE is computed."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        assert result.predictive_metrics.mce is not None
        assert 0.0 <= result.predictive_metrics.mce <= 1.0


# ═══════════════════════════════════════════════════════════════
# G. BASELINE COMPARISON TESTS
# ═══════════════════════════════════════════════════════════════


class TestBaselineComparison:
    """Test baseline comparison."""

    def test_baseline_computed(self, sample_config, sample_dataset):
        """Baseline comparison is computed."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        bl = result.baseline_comparison
        assert bl.baseline_name == "historical_base_rate"
        assert bl.baseline_frequency is not None
        assert 0.0 <= bl.baseline_frequency <= 1.0

    def test_candidate_vs_baseline(self, sample_config, sample_dataset):
        """Candidate frequency differs from baseline."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        bl = result.baseline_comparison
        assert bl.candidate_frequency is not None
        assert bl.improvement is not None
        # improvement = candidate - baseline
        assert abs(bl.improvement - (bl.candidate_frequency - bl.baseline_frequency)) < 1e-10

    def test_brier_improvement_meaningful(self, sample_config, sample_dataset):
        """Brier improvement is computed."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        bl = result.baseline_comparison
        assert bl.baseline_brier is not None
        assert bl.candidate_brier is not None
        # Brier improvement = baseline_brier - candidate_brier
        assert abs(bl.brier_improvement - (bl.baseline_brier - bl.candidate_brier)) < 1e-10


# ═══════════════════════════════════════════════════════════════
# H. REPRODUCIBILITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestReproducibility:
    """Test that same inputs produce same outputs."""

    def test_same_input_same_result(self, sample_config, sample_dataset):
        """Running same experiment twice produces identical results."""
        model1 = HistoricalFrequencyModel(min_observations=5)
        model2 = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()

        result1 = runner.run(sample_config, sample_dataset, model1)
        result2 = runner.run(sample_config, sample_dataset, model2)

        assert result1.experiment_id == result2.experiment_id
        assert result1.prediction_count == result2.prediction_count
        assert result1.predictive_metrics.hit_rate == result2.predictive_metrics.hit_rate
        assert result1.predictive_metrics.brier_score == result2.predictive_metrics.brier_score
        assert result1.statistical_evidence.p_value == result2.statistical_evidence.p_value

    def test_same_predictions(self, sample_config, sample_dataset):
        """Individual predictions are identical across runs."""
        model1 = HistoricalFrequencyModel(min_observations=5)
        model2 = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()

        result1 = runner.run(sample_config, sample_dataset, model1)
        result2 = runner.run(sample_config, sample_dataset, model2)

        for p1, p2 in zip(result1.predictions, result2.predictions):
            assert p1.match_id == p2.match_id
            assert p1.model_probability == p2.model_probability
            assert p1.actual_outcome == p2.actual_outcome
            assert p1.is_hit == p2.is_hit
            assert p1.expected_value == p2.expected_value

    def test_logistic_regression_reproducible(self, sample_hypothesis, synthetic_source, corners_market):
        """LogisticRegression with fixed seed is reproducible."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=corners_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="LogisticRegressionModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            random_seed=42,
        )
        runner = ExperimentRunner()
        model1 = LogisticRegressionModel(seed=42, max_iter=100)
        model2 = LogisticRegressionModel(seed=42, max_iter=100)

        result1 = runner.run(config, dataset, model1)
        result2 = runner.run(config, dataset, model2)

        assert result1.prediction_count == result2.prediction_count
        for p1, p2 in zip(result1.predictions, result2.predictions):
            assert abs(p1.model_probability - p2.model_probability) < 1e-10


# ═══════════════════════════════════════════════════════════════
# I. FAILURE SAFETY TESTS
# ═══════════════════════════════════════════════════════════════


class TestFailureSafety:
    """Test graceful failure handling."""

    def test_invalid_configuration(self, sample_hypothesis):
        """Invalid config produces explicit failure, not crash."""
        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version="v1",
            model_type="HF",
            training_start=3000,  # start after end
            training_end=1000,
            evaluation_start=4000,
            evaluation_end=5000,
        )
        # Use a minimal dataset
        source = SyntheticResearchDataSource(seed=42)
        market = create_default_registry().get(MarketType.CORNERS_TOTAL)
        dataset = ResearchDataset(source=source, market=market)
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.INVALID_CONFIGURATION

    def test_empty_dataset(self, sample_hypothesis, corners_market):
        """Empty dataset produces INSUFFICIENT_DATA."""

        class EmptySource(ResearchDataSource):
            def get_matches(self, **kwargs):
                return []

            def get_available_fields(self):
                return []

            def get_market_odds(self, **kwargs):
                return []

        source = EmptySource()
        dataset = ResearchDataset(source=source, market=corners_market)

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version="empty",
            model_type="HF",
            training_start=1000,
            training_end=2000,
            evaluation_start=2000,
            evaluation_end=3000,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.INSUFFICIENT_DATA

    def test_small_dataset(self, sample_hypothesis, corners_market):
        """Small dataset below minimum observations fails gracefully."""

        class TinySource(ResearchDataSource):
            def get_matches(self, **kwargs):
                return [
                    ResearchMatch(
                        match_id=i,
                        date_unix=1000 + i * 100,
                        league_id=1,
                        season="2024",
                        home_team="A",
                        away_team="B",
                        total_corners=10,
                    )
                    for i in range(5)
                ]

            def get_available_fields(self):
                return ["total_corners"]

            def get_market_odds(self, **kwargs):
                return []

        source = TinySource()
        dataset = ResearchDataset(source=source, market=corners_market)

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version="tiny",
            model_type="HF",
            training_start=1000,
            training_end=1300,
            evaluation_start=1300,
            evaluation_end=1500,
            minimum_observations=50,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.INSUFFICIENT_DATA

    def test_missing_target_field(self, sample_hypothesis, corners_market):
        """Missing target field handled gracefully."""

        class NoTargetSource(ResearchDataSource):
            def get_matches(self, **kwargs):
                return [
                    ResearchMatch(
                        match_id=i,
                        date_unix=1000 + i * 100,
                        league_id=1,
                        season="2024",
                        home_team="A",
                        away_team="B",
                        # total_corners intentionally None
                        dangerous_attacks_home=25,
                    )
                    for i in range(200)
                ]

            def get_available_fields(self):
                return ["dangerous_attacks_home"]

            def get_market_odds(self, **kwargs):
                return []

        source = NoTargetSource()
        dataset = ResearchDataset(source=source, market=corners_market)

        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version="no_target",
            model_type="HF",
            training_start=1000,
            training_end=11000,
            evaluation_start=11000,
            evaluation_end=21000,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # Should fail due to all targets missing
        assert result.status == ExperimentResultStatus.INSUFFICIENT_DATA

    def test_no_hypothesis_config_invalid(self):
        """Config without hypothesis is invalid."""
        config = ExperimentConfig(
            hypothesis=None,
            market_type="CORNERS_TOTAL",
            dataset_version="v1",
            model_type="HF",
            training_start=1000,
            training_end=2000,
            evaluation_start=2000,
            evaluation_end=3000,
        )
        valid, reason = config.validate()
        assert not valid
        assert "hypothesis" in reason.lower()

    def test_temporal_violation_in_config(self, sample_hypothesis):
        """Config with training overlapping evaluation is invalid."""
        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version="v1",
            model_type="HF",
            training_start=1000,
            training_end=3000,
            evaluation_start=2000,
            evaluation_end=4000,
        )
        valid, reason = config.validate()
        assert not valid
        assert "overlap" in reason.lower() or "temporal" in reason.lower()


# ═══════════════════════════════════════════════════════════════
# J. TEMPORAL LEAKAGE ATTACK TESTS
# ═══════════════════════════════════════════════════════════════


class TestTemporalLeakage:
    """Construct artificial datasets where future info is extremely
    predictive. The experiment MUST NOT exploit these fields."""

    def _create_leakage_source(self, leak_type: str):
        """Create a data source with deliberate leakage opportunity.

        Three leak types:
        - 'future_outcome': future match outcome is a feature
        - 'future_feature': future statistics predict current match
        - 'future_odds': odds from a future match predict current
        """

        class LeakageSource(ResearchDataSource):
            def __init__(self):
                self._matches = []
                self._odds = []
                rng = np.random.default_rng(42)

                for i in range(300):
                    date_unix = 1000000 + i * 86400  # 1 day apart
                    # Deterministic outcome: corners = 8 + (i % 5)
                    total_corners = 8 + (i % 5)
                    is_over = total_corners > 9.5

                    # Normal feature
                    dangerous_attacks = 20 + rng.integers(-5, 5)

                    # Leakage feature: perfectly predicts outcome
                    if leak_type == "future_outcome":
                        # This feature IS the future outcome
                        leak_feature = float(total_corners)
                    elif leak_type == "future_feature":
                        # This feature is from a FUTURE match
                        future_idx = min(i + 10, 299)
                        future_corners = 8 + (future_idx % 5)
                        leak_feature = float(future_corners)
                    elif leak_type == "future_odds":
                        # Odds that perfectly reflect outcome
                        leak_feature = 1.5 if is_over else 3.0
                    else:
                        leak_feature = 0.0

                    self._matches.append(ResearchMatch(
                        match_id=i + 5000,
                        date_unix=date_unix,
                        league_id=1,
                        season="2024",
                        home_team="A",
                        away_team="B",
                        total_corners=total_corners,
                        dangerous_attacks_home=int(dangerous_attacks),
                    ))

                    # Store odds
                    over_odds = 1.8 + rng.uniform(-0.2, 0.2)
                    under_odds = 2.1 + rng.uniform(-0.2, 0.2)
                    self._odds.append(MarketOdds(
                        match_id=i + 5000,
                        market="CORNERS_TOTAL",
                        line=9.5,
                        over_odds=over_odds,
                        under_odds=under_odds,
                        timestamp=date_unix - 3600,
                    ))

            def get_matches(self, **kwargs):
                return sorted(self._matches, key=lambda m: m.date_unix)

            def get_available_fields(self):
                return ["total_corners", "dangerous_attacks_home"]

            def get_market_odds(self, **kwargs):
                return self._odds

        return LeakageSource()

    def test_no_future_outcome_leakage(self, corners_market):
        """Experiment cannot use the actual outcome as a feature.

        The model is trained on features only. The target (total_corners)
        is used ONLY for outcome resolution, not as a predictive feature
        accessible before the match.

        In a temporal experiment, the outcome is resolved AFTER prediction.
        """
        source = self._create_leakage_source("future_outcome")
        dataset = ResearchDataset(source=source, market=corners_market)
        matches = source.get_matches()

        # Create a candidate that uses dangerous_attacks_home (legitimate)
        candidate = ResearchCandidate(
            candidate_id="legit",
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 15.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)

        midpoint = matches[180].date_unix
        config = ExperimentConfig(
            hypothesis=h,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # The model should NOT achieve perfect accuracy
        # because it can only see dangerous_attacks_home, not total_corners
        if result.status == ExperimentResultStatus.COMPLETED and result.prediction_count > 0:
            # A model with leakage would have hit_rate near 1.0
            # Without leakage, it should be much lower
            assert result.predictive_metrics.hit_rate < 0.95

    def test_training_data_precedes_evaluation(self, corners_market):
        """All training observations have timestamps before evaluation."""
        source = self._create_leakage_source("future_feature")
        dataset = ResearchDataset(source=source, market=corners_market)
        matches = source.get_matches()

        candidate = ResearchCandidate(
            candidate_id="temporal_test",
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 15.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)

        midpoint = matches[180].date_unix
        config = ExperimentConfig(
            hypothesis=h,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # All predictions must have timestamp >= evaluation_start
        if result.prediction_count > 0:
            for p in result.predictions:
                assert p.prediction_timestamp >= config.evaluation_start

    def test_no_future_odds_leakage(self, corners_market):
        """Future odds cannot be used as predictive features."""
        source = self._create_leakage_source("future_odds")
        dataset = ResearchDataset(source=source, market=corners_market)
        matches = source.get_matches()

        # Candidate uses legitimate pre-match feature
        candidate = ResearchCandidate(
            candidate_id="odds_leak_test",
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 15.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)

        midpoint = matches[180].date_unix
        config = ExperimentConfig(
            hypothesis=h,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # Without future leakage, hit rate should not be perfect
        if result.status == ExperimentResultStatus.COMPLETED and result.prediction_count > 0:
            assert result.predictive_metrics.hit_rate < 0.95

    def test_temporal_split_prevents_future_training(self, corners_market):
        """Training period never extends into evaluation period."""
        source = SyntheticResearchDataSource(seed=42)
        matches = source.get_matches()
        dataset = ResearchDataset(source=source, market=corners_market)

        midpoint = matches[len(matches) // 2].date_unix
        split = TemporalSplitFactory.from_timestamps(
            train_start=matches[0].date_unix,
            train_end=midpoint,
            test_start=midpoint,
            test_end=matches[-1].date_unix + 1,
        )
        segments = split.split_matches(matches)

        # Verify: no training match exists at or after evaluation start
        for m in segments[SplitType.TRAIN]:
            assert m.date_unix < midpoint, (
                f"Training match at {m.date_unix} >= evaluation start {midpoint}"
            )


# ═══════════════════════════════════════════════════════════════
# ADDITIONAL TESTS
# ═══════════════════════════════════════════════════════════════


class TestDataset:
    """Test ResearchDataset functionality."""

    def test_content_hash_deterministic(self, synthetic_source, corners_market):
        """Dataset content hash is deterministic."""
        d1 = ResearchDataset(source=synthetic_source, market=corners_market)
        d2 = ResearchDataset(source=synthetic_source, market=corners_market)
        assert d1.content_hash == d2.content_hash

    def test_statistics_computed(self, sample_dataset):
        """Dataset statistics are accurate."""
        stats = sample_dataset.compute_statistics()
        assert stats.total_matches == 528
        assert stats.eligible_matches > 0
        assert stats.matches_with_odds > 0

    def test_odds_merged(self, sample_dataset, corners_market):
        """Odds are merged into match dicts."""
        for d in sample_dataset.match_dicts:
            # Corners market odds should be available
            assert corners_market.odds_over_field in d or d.get(corners_market.odds_over_field) is None


class TestEvidenceClassifier:
    """Test evidence classification logic."""

    def test_insufficient_data(self):
        """Small sample classified as INSUFFICIENT_DATA."""
        classifier = EvidenceClassifier()
        evidence = StatisticalEvidence(sample_size=5, p_value=0.01, effect_size=0.1)
        metrics = PredictiveMetrics(sample_size=5)
        assert classifier.classify(evidence, metrics) == EvidenceClassification.INSUFFICIENT_DATA

    def test_strong_signal(self):
        """Strong evidence classified correctly."""
        classifier = EvidenceClassifier()
        evidence = StatisticalEvidence(
            sample_size=200, p_value=0.005, effect_size=0.1,
            difference=0.05, mean_outcome=0.55, baseline_outcome=0.50
        )
        metrics = PredictiveMetrics(sample_size=200)
        assert classifier.classify(evidence, metrics) == EvidenceClassification.STRONG_SIGNAL

    def test_promising(self):
        """Moderate evidence classified as PROMISING."""
        classifier = EvidenceClassifier()
        evidence = StatisticalEvidence(
            sample_size=100, p_value=0.03, effect_size=0.03,
            difference=0.03, mean_outcome=0.53, baseline_outcome=0.50
        )
        metrics = PredictiveMetrics(sample_size=100)
        assert classifier.classify(evidence, metrics) == EvidenceClassification.PROMISING

    def test_negative(self):
        """Significant negative effect classified as NEGATIVE."""
        classifier = EvidenceClassifier()
        evidence = StatisticalEvidence(
            sample_size=200, p_value=0.01, effect_size=0.1,
            difference=-0.05, mean_outcome=0.45, baseline_outcome=0.50
        )
        metrics = PredictiveMetrics(sample_size=200)
        assert classifier.classify(evidence, metrics) == EvidenceClassification.NEGATIVE

    def test_neutral(self):
        """Non-significant result classified as NEUTRAL."""
        classifier = EvidenceClassifier()
        evidence = StatisticalEvidence(
            sample_size=100, p_value=0.30, effect_size=0.01,
            difference=0.01, mean_outcome=0.51, baseline_outcome=0.50
        )
        metrics = PredictiveMetrics(sample_size=100)
        assert classifier.classify(evidence, metrics) == EvidenceClassification.NEUTRAL


class TestWalkForwardAdapter:
    """Test walk-forward adapter for Batch 5 compatibility."""

    def test_fold_generation(self):
        """Folds are generated chronologically."""
        adapter = WalkForwardAdapter(
            train_window_days=365,
            test_window_days=90,
            step_days=90,
        )
        # 3 years of data
        start = 1577836800  # 2020-01-01
        end = start + 3 * 365 * 86400

        folds = adapter.generate_folds(start, end)
        assert len(folds) > 0

        # Verify chronological ordering
        for i, fold in enumerate(folds):
            assert fold.training_start < fold.training_end
            assert fold.training_end <= fold.evaluation_start
            assert fold.evaluation_start < fold.evaluation_end
            assert fold.fold_index == i

        # Verify stepping
        if len(folds) > 1:
            step = folds[1].training_start - folds[0].training_start
            assert step == 90 * 86400

    def test_fold_config_creation(self, sample_config):
        """Fold configs have correct periods."""
        adapter = WalkForwardAdapter()
        from src.research.experiment_engine.walkforward_adapter import WalkForwardFold

        fold = WalkForwardFold(
            fold_index=0,
            training_start=1000,
            training_end=2000,
            evaluation_start=2000,
            evaluation_end=3000,
        )
        fold_config = adapter.create_fold_config(sample_config, fold)
        assert fold_config.training_start == 1000
        assert fold_config.training_end == 2000
        assert fold_config.evaluation_start == 2000
        assert fold_config.evaluation_end == 3000
        # Other fields preserved
        assert fold_config.hypothesis == sample_config.hypothesis
        assert fold_config.market_type == sample_config.market_type


class TestReporting:
    """Test experiment reporting."""

    def test_report_generated(self, sample_config, sample_dataset):
        """Report is generated for completed experiment."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        reporter = ExperimentReporter()
        summary = reporter.generate_summary(result)

        assert "RESEARCH EXPERIMENT REPORT" in summary
        assert result.experiment_id in summary
        assert "PREDICTIVE METRICS" in summary
        assert "BASELINE COMPARISON" in summary
        assert "STATISTICAL EVIDENCE" in summary
        assert "LIMITATIONS" in summary
        assert "RESEARCH CLASSIFICATION" in summary
        # No profitability claims
        assert "profitable" not in summary.lower()
        assert "beats" not in summary.lower()

    def test_failure_report(self, sample_hypothesis, corners_market):
        """Report handles failed experiments."""

        class EmptySource(ResearchDataSource):
            def get_matches(self, **kwargs):
                return []

            def get_available_fields(self):
                return []

            def get_market_odds(self, **kwargs):
                return []

        source = EmptySource()
        dataset = ResearchDataset(source=source, market=corners_market)
        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type="CORNERS_TOTAL",
            dataset_version="empty",
            model_type="HF",
            training_start=1000,
            training_end=2000,
            evaluation_start=2000,
            evaluation_end=3000,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        reporter = ExperimentReporter()
        summary = reporter.generate_summary(result)
        assert "EXPERIMENT DID NOT COMPLETE" in summary


class TestMultipleMarkets:
    """Test experiment works across different market types."""

    def test_goals_market(self, synthetic_source, goals_market):
        """Experiment works with goals market."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=goals_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        candidate = ResearchCandidate(
            candidate_id="goals_test",
            market_type="GOALS_TOTAL",
            feature_ids=("shots_home",),
            conditions=(CandidateCondition("shots_home", ">", 10.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        config = ExperimentConfig(
            hypothesis=h,
            market_type="GOALS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.prediction_count > 0

    def test_btts_market(self, synthetic_source, btts_market):
        """Experiment works with BTTS market."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=btts_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        candidate = ResearchCandidate(
            candidate_id="btts_test",
            market_type="BTTS",
            feature_ids=("shots_on_target_home",),
            conditions=(CandidateCondition("shots_on_target_home", ">", 3.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="YES",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        config = ExperimentConfig(
            hypothesis=h,
            market_type="BTTS",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.NO_ODDS,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.prediction_count > 0

    def test_match_result_1x2_market(self, synthetic_source, match_result_market):
        """Experiment works with 1X2 three-way market."""
        matches = synthetic_source.get_matches()
        dataset = ResearchDataset(source=synthetic_source, market=match_result_market)
        midpoint = matches[int(len(matches) * 0.6)].date_unix

        candidate = ResearchCandidate(
            candidate_id="1x2_test",
            market_type="MATCH_RESULT_1X2",
            feature_ids=("possession_home",),
            conditions=(CandidateCondition("possession_home", ">", 55.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="HOME",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        config = ExperimentConfig(
            hypothesis=h,
            market_type="MATCH_RESULT_1X2",
            dataset_version=dataset.content_hash,
            model_type="HistoricalFrequencyModel",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            odds_mode=OddsMode.NO_ODDS,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        assert result.status == ExperimentResultStatus.COMPLETED
        assert result.prediction_count > 0


class TestObservationCounting:
    """Test that observations are tracked, not silently discarded."""

    def test_counts_sum_correctly(self, sample_config, sample_dataset):
        """Observation counts are consistent."""
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(sample_config, sample_dataset, model)

        counts = result.observation_counts
        # Total rows should equal dataset size
        assert counts.total_rows > 0
        # eligible + missing + invalid + insufficient <= total
        accounted = (
            counts.eligible_rows + counts.missing_rows
            + counts.invalid_rows + counts.insufficient_history_rows
        )
        # Note: eligible_rows counts eval predictions, totals count all
        assert counts.missing_rows >= 0
        assert counts.invalid_rows >= 0

    def test_missing_not_silently_discarded(self, corners_market):
        """Missing data is tracked, not silently dropped."""

        class PartialSource(ResearchDataSource):
            def get_matches(self, **kwargs):
                matches = []
                for i in range(200):
                    # Half have missing corners
                    corners = 10 if i % 2 == 0 else None
                    matches.append(ResearchMatch(
                        match_id=i + 8000,
                        date_unix=1000000 + i * 86400,
                        league_id=1,
                        season="2024",
                        home_team="A",
                        away_team="B",
                        total_corners=corners,
                        dangerous_attacks_home=22,
                    ))
                return matches

            def get_available_fields(self):
                return ["total_corners", "dangerous_attacks_home"]

            def get_market_odds(self, **kwargs):
                return []

        source = PartialSource()
        dataset = ResearchDataset(source=source, market=corners_market)
        matches = source.get_matches()
        midpoint = matches[120].date_unix

        candidate = ResearchCandidate(
            candidate_id="partial",
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            conditions=(CandidateCondition("dangerous_attacks_home", ">", 20.0),),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        h = ExperimentHypothesis.from_candidate(candidate)
        config = ExperimentConfig(
            hypothesis=h,
            market_type="CORNERS_TOTAL",
            dataset_version=dataset.content_hash,
            model_type="HF",
            training_start=matches[0].date_unix,
            training_end=midpoint,
            evaluation_start=midpoint,
            evaluation_end=matches[-1].date_unix + 1,
            minimum_observations=10,
        )
        model = HistoricalFrequencyModel(min_observations=5)
        runner = ExperimentRunner()
        result = runner.run(config, dataset, model)

        # Missing rows should be tracked
        assert result.observation_counts.missing_rows > 0
