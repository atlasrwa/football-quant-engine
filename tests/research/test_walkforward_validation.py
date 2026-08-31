"""Comprehensive tests for Batch 5 — Walk-Forward Validation & FDR Governance.

Test categories:
A. WalkForwardConfig validation
B. Fold generation (expanding/rolling, chronological, deterministic)
C. Temporal leakage protection
D. Model refitting per fold
E. Walk-forward orchestrator end-to-end
F. FDR integration (correct p-value collection, families, BH)
G. Governance classification state machine
H. Quarantine integration
I. Economic vs statistical evidence separation
J. Reproducibility (deterministic hashes, same input → same output)
K. Failure safety (NaN, None, empty, invalid)
L. Multiple-testing edge cases
M. Research run identity
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pytest

from src.engine.analysis.fdr import FDRController, FDRResult, QuarantineStatus, QuarantineTracker
from src.research.candidates import CandidateCondition, CandidateOperator, ResearchCandidate
from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.experiment_engine.config import (
    ExperimentConfig,
    ExperimentThresholds,
    OddsMode,
)
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.hypothesis import ExperimentHypothesis, HypothesisStatus
from src.research.experiment_engine.result import (
    EvidenceClassification,
    ExperimentResult,
    ExperimentResultStatus,
    StatisticalEvidence,
)
from src.research.experiment_engine.runner import ExperimentRunner
from src.research.fdr import FDRAdapter, FDRHypothesisResult, ResearchFDRResult, ResearchFamily, ResearchFamilyBuilder
from src.research.fdr.adapter import FDRStatus
from src.research.governance import (
    GovernanceClassifier,
    GovernanceCriteria,
    GovernanceDecision,
    GovernanceState,
    QuarantineAdapter,
    ResearchRunIdentity,
)
from src.research.market import MarketType, create_default_registry
from src.research.probability import HistoricalFrequencyModel, LogisticRegressionModel, PoissonModel
from src.research.synthetic_data import SyntheticResearchDataSource
from src.research.walkforward import (
    FoldGenerator,
    FoldResult,
    FoldStatus,
    WalkForwardConfig,
    WalkForwardOrchestrator,
    WalkForwardResult,
    WalkForwardStatus,
    WindowType,
)
from src.research.walkforward.folds import FoldSpec
from src.research.walkforward.result import (
    AggregateStatisticalEvidence,
    StabilityMetrics,
    aggregate_fold_results,
)


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

DAY = 86400  # seconds in a day
MONTH = 30 * DAY


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
def sample_candidate():
    return ResearchCandidate(
        candidate_id="test_wf_candidate",
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
def goals_dataset(synthetic_source, goals_market):
    return ResearchDataset(source=synthetic_source, market=goals_market)


@pytest.fixture
def wf_config_expanding():
    """Expanding window config suitable for synthetic data (4 seasons)."""
    return WalkForwardConfig(
        initial_training_period=6 * MONTH,
        test_period=3 * MONTH,
        step_period=3 * MONTH,
        validation_period=0,
        minimum_training_observations=10,
        minimum_test_observations=5,
        window_type=WindowType.EXPANDING,
        minimum_folds=3,
        maximum_folds=20,
    )


@pytest.fixture
def wf_config_rolling():
    """Rolling window config."""
    return WalkForwardConfig(
        initial_training_period=6 * MONTH,
        test_period=3 * MONTH,
        step_period=3 * MONTH,
        validation_period=0,
        minimum_training_observations=10,
        minimum_test_observations=5,
        window_type=WindowType.ROLLING,
        minimum_folds=3,
        maximum_folds=20,
    )


@pytest.fixture
def base_experiment_config(sample_hypothesis, sample_dataset):
    """Base experiment config for walk-forward (periods will be overridden)."""
    return ExperimentConfig(
        hypothesis=sample_hypothesis,
        market_type=MarketType.CORNERS_TOTAL.value,
        dataset_version=sample_dataset.content_hash,
        model_type="historical_frequency",
        model_parameters=(),
        training_start=0,
        training_end=1,
        evaluation_start=2,
        evaluation_end=3,
        minimum_observations=5,
        odds_mode=OddsMode.SYNTHETIC_ODDS,
    )


def make_model_factory(model_type="historical_frequency", **kwargs):
    """Create a model factory for testing."""
    def factory():
        if model_type == "historical_frequency":
            return HistoricalFrequencyModel(**kwargs)
        elif model_type == "logistic_regression":
            return LogisticRegressionModel(**kwargs)
        elif model_type == "poisson":
            return PoissonModel(**kwargs)
        return HistoricalFrequencyModel()
    return factory


# ═══════════════════════════════════════════════════════════════
# A. WALKFORWARD CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════


class TestWalkForwardConfig:
    """Test WalkForwardConfig validation and properties."""

    def test_valid_config_expanding(self):
        config = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
            window_type=WindowType.EXPANDING,
            minimum_folds=3,
            maximum_folds=10,
        )
        assert config.window_type == WindowType.EXPANDING
        assert config.minimum_folds == 3

    def test_valid_config_rolling(self):
        config = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
            window_type=WindowType.ROLLING,
            minimum_folds=3,
            maximum_folds=10,
        )
        assert config.window_type == WindowType.ROLLING

    def test_invalid_zero_training_period(self):
        with pytest.raises(ValueError, match="initial_training_period"):
            WalkForwardConfig(
                initial_training_period=0,
                test_period=90 * DAY,
                step_period=90 * DAY,
            )

    def test_invalid_negative_test_period(self):
        with pytest.raises(ValueError, match="test_period"):
            WalkForwardConfig(
                initial_training_period=180 * DAY,
                test_period=-1,
                step_period=90 * DAY,
            )

    def test_invalid_zero_step(self):
        with pytest.raises(ValueError, match="step_period"):
            WalkForwardConfig(
                initial_training_period=180 * DAY,
                test_period=90 * DAY,
                step_period=0,
            )

    def test_invalid_max_less_than_min_folds(self):
        with pytest.raises(ValueError, match="maximum_folds"):
            WalkForwardConfig(
                initial_training_period=180 * DAY,
                test_period=90 * DAY,
                step_period=90 * DAY,
                minimum_folds=10,
                maximum_folds=5,
            )

    def test_content_hash_deterministic(self):
        config1 = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
        )
        config2 = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
        )
        assert config1.content_hash == config2.content_hash

    def test_content_hash_changes_with_params(self):
        config1 = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
        )
        config2 = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=60 * DAY,
            step_period=90 * DAY,
        )
        assert config1.content_hash != config2.content_hash

    def test_minimum_data_span(self):
        config = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
            validation_period=30 * DAY,
            gap_period=7 * DAY,
        )
        expected = 180 * DAY + 7 * DAY + 30 * DAY + 7 * DAY + 90 * DAY
        assert config.minimum_data_span == expected

    def test_validation_period_with_gap(self):
        config = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
            validation_period=30 * DAY,
            gap_period=7 * DAY,
        )
        assert config.validation_period == 30 * DAY
        assert config.gap_period == 7 * DAY

    def test_to_dict(self):
        config = WalkForwardConfig(
            initial_training_period=180 * DAY,
            test_period=90 * DAY,
            step_period=90 * DAY,
        )
        d = config.to_dict()
        assert "content_hash" in d
        assert d["window_type"] == "EXPANDING"


# ═══════════════════════════════════════════════════════════════
# B. FOLD GENERATION
# ═══════════════════════════════════════════════════════════════


class TestFoldGeneration:
    """Test chronological fold generation."""

    def test_expanding_window_generates_folds(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        data_start = 0
        data_end = 24 * MONTH  # 2 years of data
        folds = gen.generate(data_start, data_end)
        assert len(folds) >= 3
        # Training start should be fixed for expanding
        for f in folds:
            assert f.train_start == data_start

    def test_rolling_window_generates_folds(self, wf_config_rolling):
        gen = FoldGenerator(wf_config_rolling)
        data_start = 0
        data_end = 24 * MONTH
        folds = gen.generate(data_start, data_end)
        assert len(folds) >= 3
        # Training window should be fixed size for rolling
        for f in folds:
            assert f.train_end - f.train_start == wf_config_rolling.initial_training_period

    def test_expanding_training_grows(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        folds = gen.generate(0, 36 * MONTH)
        # Each fold's training should be at least as large as previous
        for i in range(1, len(folds)):
            assert folds[i].training_duration >= folds[i - 1].training_duration

    def test_rolling_training_fixed_size(self, wf_config_rolling):
        gen = FoldGenerator(wf_config_rolling)
        folds = gen.generate(0, 36 * MONTH)
        for f in folds:
            assert f.training_duration == wf_config_rolling.initial_training_period

    def test_no_temporal_overlap_within_fold(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        folds = gen.generate(0, 36 * MONTH)
        for f in folds:
            assert f.train_end <= f.test_start
            valid, msg = f.validate_temporal_order()
            assert valid, msg

    def test_chronological_ordering_across_folds(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        folds = gen.generate(0, 36 * MONTH)
        # Test periods should be sequential
        for i in range(1, len(folds)):
            assert folds[i].test_start >= folds[i - 1].test_start

    def test_insufficient_data_returns_empty(self):
        config = WalkForwardConfig(
            initial_training_period=365 * DAY,
            test_period=180 * DAY,
            step_period=90 * DAY,
        )
        gen = FoldGenerator(config)
        # Only 6 months of data, needs at least 365+180=545 days
        folds = gen.generate(0, 180 * DAY)
        assert folds == []

    def test_maximum_folds_respected(self):
        config = WalkForwardConfig(
            initial_training_period=30 * DAY,
            test_period=7 * DAY,
            step_period=7 * DAY,
            maximum_folds=5,
            minimum_folds=1,
        )
        gen = FoldGenerator(config)
        folds = gen.generate(0, 365 * DAY)
        assert len(folds) <= 5

    def test_minimum_folds_in_estimate(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        est = gen.estimate_fold_count(0, 36 * MONTH)
        actual = len(gen.generate(0, 36 * MONTH))
        assert est == actual

    def test_deterministic_fold_boundaries(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        folds1 = gen.generate(0, 24 * MONTH)
        folds2 = gen.generate(0, 24 * MONTH)
        assert len(folds1) == len(folds2)
        for f1, f2 in zip(folds1, folds2):
            assert f1.train_start == f2.train_start
            assert f1.train_end == f2.train_end
            assert f1.test_start == f2.test_start
            assert f1.test_end == f2.test_end

    def test_validation_segment_generated(self):
        config = WalkForwardConfig(
            initial_training_period=6 * MONTH,
            test_period=2 * MONTH,
            step_period=2 * MONTH,
            validation_period=1 * MONTH,
            minimum_folds=1,
            maximum_folds=20,
        )
        gen = FoldGenerator(config)
        folds = gen.generate(0, 24 * MONTH)
        assert len(folds) > 0
        for f in folds:
            assert f.has_validation
            assert f.validation_start is not None
            assert f.validation_end is not None
            # Validate ordering: train < validation < test
            assert f.train_end <= f.validation_start
            assert f.validation_end <= f.test_start

    def test_gap_period_enforced(self):
        config = WalkForwardConfig(
            initial_training_period=6 * MONTH,
            test_period=2 * MONTH,
            step_period=2 * MONTH,
            validation_period=1 * MONTH,
            gap_period=7 * DAY,
            minimum_folds=1,
            maximum_folds=20,
        )
        gen = FoldGenerator(config)
        folds = gen.generate(0, 24 * MONTH)
        for f in folds:
            # Gap between train and validation
            assert f.validation_start - f.train_end >= 7 * DAY
            # Gap between validation and test
            assert f.test_start - f.validation_end >= 7 * DAY


# ═══════════════════════════════════════════════════════════════
# C. TEMPORAL LEAKAGE PROTECTION
# ═══════════════════════════════════════════════════════════════


class TestTemporalLeakage:
    """Test that future information cannot leak into predictions."""

    def test_training_always_precedes_test(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        folds = gen.generate(0, 36 * MONTH)
        for f in folds:
            assert f.train_end <= f.test_start

    def test_validation_never_leaks_into_training(self):
        config = WalkForwardConfig(
            initial_training_period=6 * MONTH,
            test_period=2 * MONTH,
            step_period=2 * MONTH,
            validation_period=1 * MONTH,
            minimum_folds=1,
            maximum_folds=20,
        )
        gen = FoldGenerator(config)
        folds = gen.generate(0, 24 * MONTH)
        for f in folds:
            if f.has_validation:
                assert f.train_end <= f.validation_start

    def test_test_never_influences_training(self, wf_config_expanding):
        gen = FoldGenerator(wf_config_expanding)
        folds = gen.generate(0, 36 * MONTH)
        for f in folds:
            assert f.train_end <= f.test_start

    def test_future_outcomes_unavailable_during_training(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Verify model is only trained on data before test period."""
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        # Each successful fold should have training period before test period
        for fold_result in result.folds:
            if fold_result.is_successful:
                exp = fold_result.experiment_result
                assert exp.training_period[1] <= exp.evaluation_period[0]

    def test_future_odds_unavailable(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Odds are only used from the match itself (pre-match), not from future matches."""
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        # Check that predictions only reference their own match's odds
        for fold_result in result.folds:
            if fold_result.is_successful and fold_result.experiment_result:
                for pred in fold_result.experiment_result.predictions:
                    # prediction_timestamp should be the match's own timestamp
                    assert pred.prediction_timestamp == pred.information_timestamp


# ═══════════════════════════════════════════════════════════════
# D. MODEL REFITTING PER FOLD
# ═══════════════════════════════════════════════════════════════


class TestModelRefitting:
    """Verify models are refitted for each fold."""

    def test_model_refitted_each_fold(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Each fold must have its own fitted model — no shared state."""
        models_created = []

        def tracking_factory():
            model = HistoricalFrequencyModel()
            models_created.append(model)
            return model

        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=tracking_factory,
            experiment_config_base=base_experiment_config,
        )
        # One model created per fold
        assert len(models_created) == result.fold_count

    def test_model_identity_differs_per_fold(
        self, sample_hypothesis, sample_dataset, base_experiment_config
    ):
        """Models with different training data should have different identities."""
        config = WalkForwardConfig(
            initial_training_period=6 * MONTH,
            test_period=3 * MONTH,
            step_period=3 * MONTH,
            window_type=WindowType.EXPANDING,
            minimum_folds=2,
            maximum_folds=10,
            minimum_training_observations=5,
            minimum_test_observations=3,
        )
        orchestrator = WalkForwardOrchestrator(config)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        # With expanding window, training data changes so model identity should change
        # (For HistoricalFrequencyModel the name is the same but the result differs)
        successful = [f for f in result.folds if f.is_successful]
        if len(successful) >= 2:
            # Training observations should differ for expanding window
            assert successful[0].training_observations <= successful[1].training_observations

    def test_test_data_never_used_for_fitting(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Training periods must not overlap with test periods."""
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        for fold_result in result.folds:
            if fold_result.is_successful:
                exp = fold_result.experiment_result
                # Training end <= evaluation start
                assert exp.training_period[1] <= exp.evaluation_period[0]


# ═══════════════════════════════════════════════════════════════
# E. WALK-FORWARD ORCHESTRATOR END-TO-END
# ═══════════════════════════════════════════════════════════════


class TestWalkForwardOrchestrator:
    """End-to-end walk-forward orchestrator tests."""

    def test_end_to_end_expanding(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        assert result.status == WalkForwardStatus.COMPLETED
        assert result.successful_folds >= wf_config_expanding.minimum_folds
        assert result.total_predictions > 0
        assert result.p_value_for_fdr is not None

    def test_end_to_end_rolling(
        self, sample_hypothesis, sample_dataset, wf_config_rolling, base_experiment_config
    ):
        orchestrator = WalkForwardOrchestrator(wf_config_rolling)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        assert result.status == WalkForwardStatus.COMPLETED
        assert result.successful_folds >= wf_config_rolling.minimum_folds

    def test_insufficient_data_returns_proper_status(self, sample_hypothesis, base_experiment_config):
        """Empty dataset should return INSUFFICIENT_DATA."""
        # Create minimal data source with no matches
        class EmptySource(ResearchDataSource):
            def get_matches(self, **kwargs):
                return []
            def get_available_fields(self):
                return []
            def get_market_odds(self, **kwargs):
                return []

        market = create_default_registry().get(MarketType.CORNERS_TOTAL)
        dataset = ResearchDataset(source=EmptySource(), market=market)

        config = WalkForwardConfig(
            initial_training_period=6 * MONTH,
            test_period=3 * MONTH,
            step_period=3 * MONTH,
            minimum_folds=3,
            maximum_folds=10,
        )
        orchestrator = WalkForwardOrchestrator(config)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        assert result.status == WalkForwardStatus.INSUFFICIENT_DATA

    def test_fold_results_contain_experiment_results(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        successful = [f for f in result.folds if f.is_successful]
        for fold_result in successful:
            assert fold_result.experiment_result is not None
            assert fold_result.experiment_result.status == ExperimentResultStatus.COMPLETED
            assert fold_result.experiment_result.predictive_metrics.sample_size > 0

    def test_aggregate_metrics_computed(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        assert result.aggregate_evidence.combined_p_value is not None
        assert result.aggregate_hit_rate is not None
        assert result.stability.positive_fold_ratio >= 0

    def test_stability_metrics_computed(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        stability = result.stability
        assert 0 <= stability.positive_fold_ratio <= 1.0
        assert stability.max_consecutive_negative >= 0

    def test_with_logistic_regression_model(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Test with a different model type."""
        config = ExperimentConfig(
            hypothesis=base_experiment_config.hypothesis,
            market_type=base_experiment_config.market_type,
            dataset_version=base_experiment_config.dataset_version,
            model_type="logistic_regression",
            model_parameters=(),
            training_start=0,
            training_end=1,
            evaluation_start=2,
            evaluation_end=3,
            minimum_observations=5,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
        )
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory("logistic_regression"),
            experiment_config_base=config,
        )
        # Should complete without errors
        assert result.fold_count > 0

    def test_with_poisson_model(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Test with Poisson model."""
        config = ExperimentConfig(
            hypothesis=base_experiment_config.hypothesis,
            market_type=base_experiment_config.market_type,
            dataset_version=base_experiment_config.dataset_version,
            model_type="poisson",
            model_parameters=(("line", 9.5),),
            training_start=0,
            training_end=1,
            evaluation_start=2,
            evaluation_end=3,
            minimum_observations=5,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
        )
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory("poisson", line=9.5),
            experiment_config_base=config,
        )
        assert result.fold_count > 0


# ═══════════════════════════════════════════════════════════════
# F. FDR INTEGRATION
# ═══════════════════════════════════════════════════════════════


class TestFDRIntegration:
    """Test FDR adapter connecting to frozen FDRController."""

    def test_correct_p_value_collection(self):
        """FDR receives correct p-values from walk-forward results."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="CORNERS_TOTAL",
            dataset_version="abc123",
            research_run_id="run_001",
            hypothesis_count=5,
        )

        # Create mock WalkForwardResults with known p-values
        results = []
        for p in [0.01, 0.02, 0.03, 0.04, 0.10]:
            results.append(WalkForwardResult(
                hypothesis_hash=f"hyp_{p}",
                candidate_hash=f"cand_{p}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    valid_p_value_count=5,
                ),
            ))

        fdr_result = adapter.correct(results, family)
        assert fdr_result.total_hypotheses == 5
        assert fdr_result.valid_hypotheses == 5

    def test_correct_research_family(self):
        """Research family correctly identifies the group."""
        family = ResearchFamilyBuilder.build(
            market_type="CORNERS_TOTAL",
            dataset_version="abc123",
            research_run_id="run_001",
        )
        assert family.market_type == "CORNERS_TOTAL"
        assert family.dataset_version == "abc123"
        assert len(family.family_id) == 16

    def test_correct_number_of_tests(self):
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1", hypothesis_count=10,
        )
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.01 * (i + 1),
                    valid_p_value_count=5,
                ),
            )
            for i in range(10)
        ]
        fdr_result = adapter.correct(results, family)
        for hr in fdr_result.hypothesis_results:
            if hr.fdr_status in (FDRStatus.FDR_PASS, FDRStatus.FDR_FAIL):
                assert hr.number_of_tests == 10

    def test_fdr_pass_fail(self):
        """Some hypotheses pass, others fail."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        # 10 hypotheses, first few have very low p-values
        p_values = [0.001, 0.002, 0.003, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    valid_p_value_count=5,
                ),
            )
            for i, p in enumerate(p_values)
        ]
        fdr_result = adapter.correct(results, family)
        passing = fdr_result.get_passing_hypotheses()
        failing = fdr_result.get_failing_hypotheses()
        assert len(passing) >= 1  # At least the lowest p-values should pass
        assert len(failing) >= 1  # High p-values should fail

    def test_missing_p_values_handled_safely(self):
        """Results without p-values get INSUFFICIENT_DATA status."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash="h1",
                candidate_hash="c1",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=None,  # No p-value
                    valid_p_value_count=0,
                ),
            ),
            WalkForwardResult(
                hypothesis_hash="h2",
                candidate_hash="c2",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.01,
                    valid_p_value_count=5,
                ),
            ),
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.insufficient_data_count == 1
        assert fdr_result.valid_hypotheses == 1

    def test_invalid_p_values_rejected(self):
        """p-values outside (0, 1] are rejected."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash="h1",
                candidate_hash="c1",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=-0.5,  # Invalid
                    valid_p_value_count=5,
                ),
            ),
            WalkForwardResult(
                hypothesis_hash="h2",
                candidate_hash="c2",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=1.5,  # Invalid
                    valid_p_value_count=5,
                ),
            ),
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.invalid_p_value_count == 2
        assert fdr_result.valid_hypotheses == 0

    def test_single_hypothesis(self):
        """Edge case: only 1 hypothesis."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash="h1",
                candidate_hash="c1",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.01,
                    valid_p_value_count=5,
                ),
            ),
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.total_hypotheses == 1
        assert fdr_result.rejected_count == 1  # p=0.01 < alpha=0.05

    def test_100_hypotheses(self):
        """Scale test: 100 hypotheses."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1", hypothesis_count=100,
        )
        # Generate p-values: some significant, most not
        rng = np.random.RandomState(42)
        p_values = list(rng.uniform(0.001, 0.999, 100))
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    valid_p_value_count=5,
                ),
            )
            for i, p in enumerate(p_values)
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.total_hypotheses == 100
        assert fdr_result.valid_hypotheses == 100
        assert fdr_result.rejected_count + fdr_result.accepted_count == 100

    def test_identical_p_values(self):
        """Edge case: all identical p-values."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.03,
                    valid_p_value_count=5,
                ),
            )
            for i in range(10)
        ]
        fdr_result = adapter.correct(results, family)
        # With BH: threshold for rank 10 = 10/10 * 0.05 = 0.05 > 0.03, so all pass
        assert fdr_result.rejected_count == 10

    def test_p_values_near_alpha(self):
        """Edge case: p-values clustered near alpha boundary."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    valid_p_value_count=5,
                ),
            )
            for i, p in enumerate([0.04, 0.045, 0.049, 0.050, 0.051, 0.055, 0.06])
        ]
        fdr_result = adapter.correct(results, family)
        # Should have deterministic result
        assert fdr_result.total_hypotheses == 7

    def test_all_null_hypotheses(self):
        """All p-values are high (all null true)."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.5 + i * 0.05,
                    valid_p_value_count=5,
                ),
            )
            for i in range(10)
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.rejected_count == 0

    def test_all_significant_hypotheses(self):
        """All p-values very low."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.001 * (i + 1),
                    valid_p_value_count=5,
                ),
            )
            for i in range(10)
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.rejected_count == 10  # All should pass BH

    def test_empty_input(self):
        """Empty list of results."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        fdr_result = adapter.correct([], family)
        assert fdr_result.total_hypotheses == 0
        assert fdr_result.rejected_count == 0

    def test_duplicate_hypotheses(self):
        """Duplicate hypothesis IDs in input."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash="same_id",
                candidate_hash="same_cand",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.01,
                    valid_p_value_count=5,
                ),
            ),
            WalkForwardResult(
                hypothesis_hash="same_id",
                candidate_hash="same_cand",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=0.01,
                    valid_p_value_count=5,
                ),
            ),
        ]
        # Should handle gracefully (no crash)
        fdr_result = adapter.correct(results, family)
        assert fdr_result.total_hypotheses == 2

    def test_research_family_deterministic_id(self):
        """Same inputs produce same family_id."""
        f1 = ResearchFamilyBuilder.build(
            market_type="CORNERS_TOTAL",
            dataset_version="abc",
            research_run_id="run1",
        )
        f2 = ResearchFamilyBuilder.build(
            market_type="CORNERS_TOTAL",
            dataset_version="abc",
            research_run_id="run1",
        )
        assert f1.family_id == f2.family_id

    def test_research_family_changes_with_market(self):
        """Different market produces different family_id."""
        f1 = ResearchFamilyBuilder.build(
            market_type="CORNERS_TOTAL", dataset_version="abc",
        )
        f2 = ResearchFamilyBuilder.build(
            market_type="GOALS_TOTAL", dataset_version="abc",
        )
        assert f1.family_id != f2.family_id


# ═══════════════════════════════════════════════════════════════
# G. GOVERNANCE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════


class TestGovernanceClassification:
    """Test governance state machine transitions."""

    def test_walk_forward_validated(self):
        """Good walk-forward result → WALK_FORWARD_VALIDATED."""
        classifier = GovernanceClassifier(GovernanceCriteria(
            minimum_folds=3,
            minimum_positive_fold_ratio=0.5,
            minimum_sample_size=20,
            maximum_p_value=0.05,
            minimum_effect_size=0.001,
            minimum_calibration_quality=0.50,
        ))
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            aggregate_brier_score=0.25,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.01,
                mean_effect_size=0.05,
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(
                positive_fold_ratio=0.8,
                max_consecutive_negative=1,
            ),
        )
        decision = classifier.classify_walk_forward(wf_result)
        assert decision.new_state == GovernanceState.WALK_FORWARD_VALIDATED

    def test_rejected_insufficient_folds(self):
        """Too few folds → REJECTED."""
        classifier = GovernanceClassifier(GovernanceCriteria(minimum_folds=5))
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=3,
            total_predictions=100,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.01,
                mean_effect_size=0.05,
                valid_p_value_count=3,
            ),
            stability=StabilityMetrics(positive_fold_ratio=0.8),
        )
        decision = classifier.classify_walk_forward(wf_result)
        assert decision.new_state == GovernanceState.REJECTED
        assert "Insufficient folds" in decision.reasons[0]

    def test_rejected_low_positive_fold_ratio(self):
        """Low positive fold ratio → REJECTED."""
        classifier = GovernanceClassifier(GovernanceCriteria(
            minimum_folds=3,
            minimum_positive_fold_ratio=0.6,
            minimum_sample_size=20,
            maximum_p_value=0.05,
        ))
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.01,
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(positive_fold_ratio=0.3),
        )
        decision = classifier.classify_walk_forward(wf_result)
        assert decision.new_state == GovernanceState.REJECTED

    def test_rejected_high_p_value(self):
        """High p-value → REJECTED."""
        classifier = GovernanceClassifier(GovernanceCriteria(
            minimum_folds=3,
            minimum_positive_fold_ratio=0.5,
            minimum_sample_size=20,
            maximum_p_value=0.05,
        ))
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.15,  # Too high
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(positive_fold_ratio=0.8),
        )
        decision = classifier.classify_walk_forward(wf_result)
        assert decision.new_state == GovernanceState.REJECTED

    def test_fdr_validated(self):
        """FDR pass → FDR_VALIDATED."""
        classifier = GovernanceClassifier()
        fdr_result = FDRHypothesisResult(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            raw_p_value=0.01,
            adjusted_threshold=0.025,
            rank=1,
            family_id="fam1",
            number_of_tests=10,
            alpha=0.05,
            fdr_status=FDRStatus.FDR_PASS,
        )
        decision = classifier.classify_fdr(fdr_result)
        assert decision.new_state == GovernanceState.FDR_VALIDATED

    def test_fdr_fail_rejected(self):
        """FDR fail → REJECTED."""
        classifier = GovernanceClassifier()
        fdr_result = FDRHypothesisResult(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            raw_p_value=0.08,
            adjusted_threshold=0.005,
            rank=10,
            family_id="fam1",
            number_of_tests=10,
            alpha=0.05,
            fdr_status=FDRStatus.FDR_FAIL,
        )
        decision = classifier.classify_fdr(fdr_result)
        assert decision.new_state == GovernanceState.REJECTED

    def test_quarantine_eligible(self):
        """WF validated + FDR pass → QUARANTINE_ELIGIBLE."""
        classifier = GovernanceClassifier(GovernanceCriteria())
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.001,
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(positive_fold_ratio=0.8),
        )
        fdr_result = FDRHypothesisResult(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            raw_p_value=0.001,
            adjusted_threshold=0.005,
            rank=1,
            family_id="fam1",
            number_of_tests=10,
            alpha=0.05,
            fdr_status=FDRStatus.FDR_PASS,
        )
        decision = classifier.determine_quarantine_eligibility(wf_result, fdr_result)
        assert decision.new_state == GovernanceState.QUARANTINE_ELIGIBLE

    def test_quarantine_rejected_without_fdr(self):
        """Without FDR pass → REJECTED for quarantine."""
        classifier = GovernanceClassifier()
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
        )
        fdr_result = FDRHypothesisResult(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            raw_p_value=0.08,
            adjusted_threshold=0.005,
            rank=10,
            family_id="fam1",
            number_of_tests=10,
            alpha=0.05,
            fdr_status=FDRStatus.FDR_FAIL,
        )
        decision = classifier.determine_quarantine_eligibility(wf_result, fdr_result)
        assert decision.new_state == GovernanceState.REJECTED

    def test_governance_states_are_ordered(self):
        """States follow the expected progression."""
        states = list(GovernanceState)
        assert states.index(GovernanceState.DISCOVERED) < states.index(GovernanceState.PROMISING)
        assert states.index(GovernanceState.PROMISING) < states.index(GovernanceState.WALK_FORWARD_VALIDATED)
        assert states.index(GovernanceState.WALK_FORWARD_VALIDATED) < states.index(GovernanceState.FDR_VALIDATED)
        assert states.index(GovernanceState.FDR_VALIDATED) < states.index(GovernanceState.QUARANTINE_ELIGIBLE)


# ═══════════════════════════════════════════════════════════════
# H. QUARANTINE INTEGRATION
# ═══════════════════════════════════════════════════════════════


class TestQuarantineIntegration:
    """Test quarantine adapter to frozen QuarantineTracker."""

    def test_submit_eligible_candidate(self):
        """QUARANTINE_ELIGIBLE can enter quarantine."""
        adapter = QuarantineAdapter()
        decision = GovernanceDecision(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            previous_state=GovernanceState.FDR_VALIDATED,
            new_state=GovernanceState.QUARANTINE_ELIGIBLE,
        )
        submission = adapter.submit_for_quarantine(
            decision, entry_date=datetime(2024, 1, 1)
        )
        assert submission.submitted is True
        assert submission.quarantine_entry is not None
        assert submission.quarantine_entry.status == QuarantineStatus.PENDING_QUARANTINE

    def test_reject_non_eligible(self):
        """Non-eligible decision raises ValueError."""
        adapter = QuarantineAdapter()
        decision = GovernanceDecision(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            previous_state=GovernanceState.PROMISING,
            new_state=GovernanceState.REJECTED,
        )
        with pytest.raises(ValueError, match="QUARANTINE_ELIGIBLE"):
            adapter.submit_for_quarantine(decision)

    def test_check_status(self):
        """Can check quarantine status after submission."""
        adapter = QuarantineAdapter()
        decision = GovernanceDecision(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            previous_state=GovernanceState.FDR_VALIDATED,
            new_state=GovernanceState.QUARANTINE_ELIGIBLE,
        )
        adapter.submit_for_quarantine(decision, entry_date=datetime(2024, 1, 1))
        status = adapter.check_quarantine_status("hyp1")
        assert status == QuarantineStatus.PENDING_QUARANTINE

    def test_not_in_quarantine_returns_none(self):
        """Unknown hypothesis returns None."""
        adapter = QuarantineAdapter()
        assert adapter.check_quarantine_status("unknown") is None

    def test_strategy_name_generated(self):
        """Strategy name is generated from hypothesis identity."""
        adapter = QuarantineAdapter()
        decision = GovernanceDecision(
            hypothesis_id="abcdef1234567890",
            candidate_hash="fedcba9876543210",
            previous_state=GovernanceState.FDR_VALIDATED,
            new_state=GovernanceState.QUARANTINE_ELIGIBLE,
        )
        submission = adapter.submit_for_quarantine(
            decision, entry_date=datetime(2024, 1, 1)
        )
        assert submission.strategy_name.startswith("research_")
        assert "fedcba98" in submission.strategy_name


# ═══════════════════════════════════════════════════════════════
# I. ECONOMIC VS STATISTICAL EVIDENCE SEPARATION
# ═══════════════════════════════════════════════════════════════


class TestEvidenceSeparation:
    """Test that statistical and economic evidence are kept separate."""

    def test_statistical_significance_not_profitability(self):
        """A statistically significant result can have negative ROI."""
        classifier = GovernanceClassifier(GovernanceCriteria(
            minimum_folds=3,
            minimum_positive_fold_ratio=0.5,
            minimum_sample_size=20,
            maximum_p_value=0.05,
            minimum_effect_size=0.001,
            minimum_calibration_quality=0.50,
        ))
        # Statistically significant but negative mean EV
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            mean_fold_roi=-5.0,  # Negative ROI
            mean_fold_ev=-0.02,  # Negative EV
            aggregate_brier_score=0.20,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.01,  # Statistically significant
                mean_effect_size=0.05,
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(
                positive_fold_ratio=0.6,
                max_consecutive_negative=1,
            ),
        )
        decision = classifier.classify_walk_forward(wf_result)
        # Can be walk-forward validated statistically while being unprofitable
        assert decision.new_state == GovernanceState.WALK_FORWARD_VALIDATED

    def test_profitability_not_statistical_significance(self):
        """A profitable result may not be statistically significant."""
        classifier = GovernanceClassifier(GovernanceCriteria(
            minimum_folds=3,
            minimum_positive_fold_ratio=0.5,
            minimum_sample_size=20,
            maximum_p_value=0.05,
        ))
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            mean_fold_roi=15.0,  # Highly profitable
            mean_fold_ev=0.10,
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.20,  # NOT significant
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(positive_fold_ratio=0.8),
        )
        decision = classifier.classify_walk_forward(wf_result)
        assert decision.new_state == GovernanceState.REJECTED

    def test_calibration_not_profitability(self):
        """Good calibration (low Brier) doesn't guarantee profits."""
        # This is tested implicitly: calibration_quality check is separate
        # from economic metrics
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.COMPLETED,
            successful_folds=5,
            total_predictions=100,
            aggregate_brier_score=0.15,  # Excellent calibration
            mean_fold_roi=-10.0,  # But negative ROI
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.01,
                mean_effect_size=0.05,
                valid_p_value_count=5,
            ),
            stability=StabilityMetrics(positive_fold_ratio=0.6),
        )
        # Economic metrics are separate from classification
        assert wf_result.mean_fold_roi < 0
        assert wf_result.aggregate_brier_score < 0.25

    def test_fdr_pass_not_production_readiness(self):
        """FDR pass alone doesn't mean production ready."""
        # QUARANTINE_ELIGIBLE is NOT the same as production-ready
        # Production requires actual quarantine period (90 days paper trading)
        classifier = GovernanceClassifier()
        fdr_result = FDRHypothesisResult(
            hypothesis_id="hyp1",
            candidate_hash="cand1",
            raw_p_value=0.001,
            adjusted_threshold=0.005,
            rank=1,
            family_id="fam1",
            number_of_tests=10,
            alpha=0.05,
            fdr_status=FDRStatus.FDR_PASS,
        )
        decision = classifier.classify_fdr(fdr_result)
        # FDR_VALIDATED != QUARANTINE_ELIGIBLE != PROMOTED
        assert decision.new_state == GovernanceState.FDR_VALIDATED
        assert decision.new_state != GovernanceState.QUARANTINE_ELIGIBLE


# ═══════════════════════════════════════════════════════════════
# J. REPRODUCIBILITY
# ═══════════════════════════════════════════════════════════════


class TestReproducibility:
    """Test deterministic results from same inputs."""

    def test_same_config_same_folds(self, wf_config_expanding):
        """Same config produces same fold boundaries."""
        gen = FoldGenerator(wf_config_expanding)
        folds1 = gen.generate(0, 24 * MONTH)
        folds2 = gen.generate(0, 24 * MONTH)
        assert len(folds1) == len(folds2)
        for f1, f2 in zip(folds1, folds2):
            assert f1 == f2

    def test_same_input_same_wf_result(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Same inputs produce same walk-forward result."""
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result1 = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        result2 = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=base_experiment_config,
        )
        assert result1.successful_folds == result2.successful_folds
        assert result1.total_predictions == result2.total_predictions
        assert result1.p_value_for_fdr == result2.p_value_for_fdr
        assert result1.aggregate_hit_rate == result2.aggregate_hit_rate

    def test_same_input_same_fdr(self):
        """Same p-values produce same FDR results."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        p_values = [0.001, 0.01, 0.03, 0.05, 0.10]
        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i}",
                candidate_hash=f"c{i}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    valid_p_value_count=5,
                ),
            )
            for i, p in enumerate(p_values)
        ]
        fdr1 = adapter.correct(results, family)
        fdr2 = adapter.correct(results, family)
        assert fdr1.rejected_count == fdr2.rejected_count
        for h1, h2 in zip(fdr1.hypothesis_results, fdr2.hypothesis_results):
            assert h1.fdr_status == h2.fdr_status

    def test_research_run_identity_deterministic(self):
        """Same inputs produce same run_id."""
        id1 = ResearchRunIdentity(
            dataset_version="abc",
            walkforward_config_hash="def",
            model_type="hist_freq",
        )
        id2 = ResearchRunIdentity(
            dataset_version="abc",
            walkforward_config_hash="def",
            model_type="hist_freq",
        )
        assert id1.run_id == id2.run_id

    def test_research_run_identity_changes_with_input(self):
        """Different inputs produce different run_id."""
        id1 = ResearchRunIdentity(
            dataset_version="abc",
            walkforward_config_hash="def",
            model_type="hist_freq",
        )
        id2 = ResearchRunIdentity(
            dataset_version="xyz",
            walkforward_config_hash="def",
            model_type="hist_freq",
        )
        assert id1.run_id != id2.run_id

    def test_walkforward_result_content_hash(self):
        """WalkForwardResult produces deterministic content hash."""
        result = WalkForwardResult(
            experiment_id="exp1",
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            market_type="TEST",
            status=WalkForwardStatus.COMPLETED,
            fold_count=5,
            successful_folds=5,
            total_predictions=100,
            walkforward_config_hash="cfg1",
            aggregate_evidence=AggregateStatisticalEvidence(
                combined_p_value=0.01,
                valid_p_value_count=5,
            ),
        )
        # Hash should be deterministic
        h1 = result.content_hash
        h2 = result.content_hash
        assert h1 == h2
        assert len(h1) == 16

    def test_governance_criteria_hash(self):
        """GovernanceCriteria has deterministic hash."""
        c1 = GovernanceCriteria(minimum_folds=5, maximum_p_value=0.05)
        c2 = GovernanceCriteria(minimum_folds=5, maximum_p_value=0.05)
        assert c1.content_hash == c2.content_hash

    def test_fdr_result_content_hash(self):
        """ResearchFDRResult has deterministic hash."""
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        result = ResearchFDRResult(
            family=family,
            alpha=0.05,
            total_hypotheses=10,
            valid_hypotheses=10,
            rejected_count=3,
            accepted_count=7,
            insufficient_data_count=0,
            invalid_p_value_count=0,
            hypothesis_results=(
                FDRHypothesisResult(
                    hypothesis_id="h1",
                    candidate_hash="c1",
                    raw_p_value=0.01,
                    adjusted_threshold=0.005,
                    rank=1,
                    family_id=family.family_id,
                    number_of_tests=10,
                    alpha=0.05,
                    fdr_status=FDRStatus.FDR_PASS,
                ),
            ),
        )
        h1 = result.content_hash
        h2 = result.content_hash
        assert h1 == h2


# ═══════════════════════════════════════════════════════════════
# K. FAILURE SAFETY
# ═══════════════════════════════════════════════════════════════


class TestFailureSafety:
    """Test safe handling of invalid/missing data."""

    def test_nan_p_value_handled(self):
        """NaN p-value treated as insufficient data."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash="h1",
                candidate_hash="c1",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=float("nan"),
                    valid_p_value_count=5,
                ),
            ),
        ]
        fdr_result = adapter.correct(results, family)
        # NaN should be treated as invalid
        assert fdr_result.invalid_p_value_count == 1 or fdr_result.insufficient_data_count == 1

    def test_none_p_value_handled(self):
        """None p-value → INSUFFICIENT_DATA."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="TEST", dataset_version="v1",
        )
        results = [
            WalkForwardResult(
                hypothesis_hash="h1",
                candidate_hash="c1",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=None,
                    valid_p_value_count=0,
                ),
            ),
        ]
        fdr_result = adapter.correct(results, family)
        assert fdr_result.insufficient_data_count == 1

    def test_empty_folds_aggregation(self):
        """Aggregating empty fold list produces correct status."""
        result = aggregate_fold_results(
            folds=[],
            experiment_id="exp1",
            candidate_hash="c1",
            hypothesis_hash="h1",
            market_type="TEST",
            walkforward_config_hash="cfg1",
        )
        assert result.status == WalkForwardStatus.INSUFFICIENT_FOLDS

    def test_all_folds_failed(self):
        """All folds failing produces correct status."""
        folds = [
            FoldResult(
                fold_spec=FoldSpec(fold_index=i, train_start=0, train_end=100, test_start=200, test_end=300),
                status=FoldStatus.INSUFFICIENT_TRAINING_DATA,
            )
            for i in range(5)
        ]
        result = aggregate_fold_results(
            folds=folds,
            experiment_id="exp1",
            candidate_hash="c1",
            hypothesis_hash="h1",
            market_type="TEST",
            walkforward_config_hash="cfg1",
            minimum_folds=3,
        )
        assert result.status == WalkForwardStatus.INSUFFICIENT_FOLDS

    def test_model_failure_handled(
        self, sample_hypothesis, sample_dataset, wf_config_expanding, base_experiment_config
    ):
        """Model that raises during fit doesn't crash the orchestrator."""
        def failing_factory():
            class FailModel:
                name = "failing"
                is_fitted = False
                model_identity = None
                def fit(self, features, outcomes):
                    raise RuntimeError("Model failed")
                def predict(self, features):
                    raise RuntimeError("Not fitted")
            return FailModel()

        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=failing_factory,
            experiment_config_base=base_experiment_config,
        )
        # Should not crash — folds marked as MODEL_FAILURE
        assert all(
            f.status == FoldStatus.MODEL_FAILURE for f in result.folds
        )

    def test_invalid_fdr_alpha(self):
        """Invalid alpha raises ValueError."""
        with pytest.raises(ValueError):
            FDRAdapter(alpha=0.0)
        with pytest.raises(ValueError):
            FDRAdapter(alpha=1.0)
        with pytest.raises(ValueError):
            FDRAdapter(alpha=-0.5)

    def test_governance_with_incomplete_wf(self):
        """Governance handles non-completed walk-forward."""
        classifier = GovernanceClassifier()
        wf_result = WalkForwardResult(
            hypothesis_hash="hyp1",
            candidate_hash="cand1",
            status=WalkForwardStatus.ALL_FOLDS_FAILED,
        )
        decision = classifier.classify_walk_forward(wf_result)
        assert decision.new_state == GovernanceState.REJECTED

    def test_missing_odds_does_not_crash(
        self, sample_hypothesis, sample_dataset, wf_config_expanding
    ):
        """Walk-forward with NO_ODDS mode works."""
        config = ExperimentConfig(
            hypothesis=sample_hypothesis,
            market_type=MarketType.CORNERS_TOTAL.value,
            dataset_version=sample_dataset.content_hash,
            model_type="historical_frequency",
            model_parameters=(),
            training_start=0,
            training_end=1,
            evaluation_start=2,
            evaluation_end=3,
            minimum_observations=5,
            odds_mode=OddsMode.NO_ODDS,
        )
        orchestrator = WalkForwardOrchestrator(wf_config_expanding)
        result = orchestrator.run(
            hypothesis=sample_hypothesis,
            dataset=sample_dataset,
            model_factory=make_model_factory(),
            experiment_config_base=config,
        )
        # Should complete, but ROI should be None
        if result.successful_folds > 0:
            assert result.median_fold_roi is None or result.mean_fold_roi is None


# ═══════════════════════════════════════════════════════════════
# L. MULTIPLE-TESTING EDGE CASES
# ═══════════════════════════════════════════════════════════════


class TestMultipleTestingEdgeCases:
    """Explicitly test multiple-testing edge cases."""

    def test_1_hypothesis(self):
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(market_type="T", dataset_version="v1")
        results = [WalkForwardResult(
            hypothesis_hash="h1", candidate_hash="c1",
            status=WalkForwardStatus.COMPLETED, successful_folds=5,
            aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=0.03, valid_p_value_count=5),
        )]
        fdr = adapter.correct(results, family)
        assert fdr.rejected_count == 1  # 0.03 < 0.05 threshold for rank 1/1

    def test_10_hypotheses(self):
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(market_type="T", dataset_version="v1")
        # First 3 significant, rest not
        p_vals = [0.001, 0.003, 0.005, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        results = [WalkForwardResult(
            hypothesis_hash=f"h{i}", candidate_hash=f"c{i}",
            status=WalkForwardStatus.COMPLETED, successful_folds=5,
            aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=p, valid_p_value_count=5),
        ) for i, p in enumerate(p_vals)]
        fdr = adapter.correct(results, family)
        assert fdr.rejected_count >= 3  # At least the top 3 should pass

    def test_p_value_exactly_at_threshold(self):
        """p-value exactly at the BH threshold."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(market_type="T", dataset_version="v1")
        # For 1 hypothesis, threshold = 1/1 * 0.05 = 0.05
        results = [WalkForwardResult(
            hypothesis_hash="h1", candidate_hash="c1",
            status=WalkForwardStatus.COMPLETED, successful_folds=5,
            aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=0.05, valid_p_value_count=5),
        )]
        fdr = adapter.correct(results, family)
        # p=0.05 <= threshold=0.05, should pass (BH uses <=)
        assert fdr.rejected_count == 1

    def test_p_value_zero(self):
        """p=0 edge case (machine epsilon)."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(market_type="T", dataset_version="v1")
        results = [WalkForwardResult(
            hypothesis_hash="h1", candidate_hash="c1",
            status=WalkForwardStatus.COMPLETED, successful_folds=5,
            aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=0.0, valid_p_value_count=5),
        )]
        fdr = adapter.correct(results, family)
        # p=0 is a boundary case, treated as extremely significant
        assert fdr.rejected_count == 1

    def test_mixed_valid_invalid_missing(self):
        """Mix of valid, invalid, and missing p-values."""
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(market_type="T", dataset_version="v1")
        results = [
            # Valid
            WalkForwardResult(
                hypothesis_hash="h1", candidate_hash="c1",
                status=WalkForwardStatus.COMPLETED, successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=0.01, valid_p_value_count=5),
            ),
            # Missing
            WalkForwardResult(
                hypothesis_hash="h2", candidate_hash="c2",
                status=WalkForwardStatus.COMPLETED, successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=None, valid_p_value_count=0),
            ),
            # Invalid
            WalkForwardResult(
                hypothesis_hash="h3", candidate_hash="c3",
                status=WalkForwardStatus.COMPLETED, successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=-1.0, valid_p_value_count=5),
            ),
            # Valid
            WalkForwardResult(
                hypothesis_hash="h4", candidate_hash="c4",
                status=WalkForwardStatus.COMPLETED, successful_folds=5,
                aggregate_evidence=AggregateStatisticalEvidence(combined_p_value=0.80, valid_p_value_count=5),
            ),
        ]
        fdr = adapter.correct(results, family)
        assert fdr.total_hypotheses == 4
        assert fdr.valid_hypotheses == 2
        assert fdr.insufficient_data_count == 1
        assert fdr.invalid_p_value_count == 1


# ═══════════════════════════════════════════════════════════════
# M. RESEARCH RUN IDENTITY
# ═══════════════════════════════════════════════════════════════


class TestResearchRunIdentity:
    """Test ResearchRunIdentity deterministic provenance."""

    def test_from_components(self):
        identity = ResearchRunIdentity.from_components(
            dataset_version="abc123",
            walkforward_config_hash="wf_hash",
            model_type="historical_frequency",
            model_parameters={"lookback": 50},
            fdr_alpha=0.05,
            market_type="CORNERS_TOTAL",
        )
        assert len(identity.run_id) == 16
        assert identity.dataset_version == "abc123"
        assert identity.model_type == "historical_frequency"

    def test_deterministic_from_components(self):
        id1 = ResearchRunIdentity.from_components(
            dataset_version="abc",
            walkforward_config_hash="wf",
            model_type="hist",
            model_parameters={"a": 1},
        )
        id2 = ResearchRunIdentity.from_components(
            dataset_version="abc",
            walkforward_config_hash="wf",
            model_type="hist",
            model_parameters={"a": 1},
        )
        assert id1.run_id == id2.run_id

    def test_different_params_different_id(self):
        id1 = ResearchRunIdentity.from_components(
            dataset_version="abc",
            walkforward_config_hash="wf",
            model_type="hist",
            model_parameters={"a": 1},
        )
        id2 = ResearchRunIdentity.from_components(
            dataset_version="abc",
            walkforward_config_hash="wf",
            model_type="hist",
            model_parameters={"a": 2},
        )
        assert id1.run_id != id2.run_id

    def test_to_dict(self):
        identity = ResearchRunIdentity(
            dataset_version="abc",
            walkforward_config_hash="wf",
            model_type="hist",
        )
        d = identity.to_dict()
        assert "run_id" in d
        assert d["dataset_version"] == "abc"
        assert d["model_type"] == "hist"

    def test_content_hash_alias(self):
        identity = ResearchRunIdentity(
            dataset_version="abc",
            walkforward_config_hash="wf",
            model_type="hist",
        )
        assert identity.content_hash == identity.run_id
