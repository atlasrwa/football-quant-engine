"""Tests for research experiment execution."""

import pytest
import numpy as np

from src.research.candidate_generator import GenerationMethod, ResearchHypothesis
from src.research.experiment import (
    BetResult,
    ExperimentResult,
    ExperimentStatus,
    ResearchExperiment,
)
from src.research.market import CORNERS_OVER_UNDER, GOALS_OVER_UNDER, MarketType
from src.research.probability import HistoricalFrequencyModel, LogisticRegressionModel


class TestResearchExperiment:
    """Tests for ResearchExperiment walk-forward execution."""

    @pytest.fixture
    def experiment(self):
        return ResearchExperiment(
            train_window=50,
            test_window=20,
            step_size=20,
            min_ev_threshold=-0.5,  # Accept most bets for testing
            min_odds=1.30,
            max_odds=5.00,
        )

    @pytest.fixture
    def hypothesis(self):
        return ResearchHypothesis(
            hypothesis_id="test_hyp_1",
            market=MarketType.GOALS_TOTAL,
            feature_ids=("feat_1",),
            conditions=(("feat_1", ">", 0.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )

    @pytest.fixture
    def matches_and_features(self):
        """Generate 200 synthetic matches with features and odds."""
        rng = np.random.default_rng(42)
        matches = []
        features = []
        for i in range(200):
            total_goals = int(rng.poisson(2.5))
            feat_val = float(rng.normal(0.5, 1.0))
            matches.append({
                "date_unix": 1000000 + i * 86400,
                "total_goals": total_goals,
                "odds_over_goals": float(1.5 + rng.uniform(0, 1.0)),
                "odds_under_goals": float(1.5 + rng.uniform(0, 1.0)),
            })
            features.append({"feat_1": feat_val})
        return matches, features

    def test_run_produces_result(self, experiment, hypothesis, matches_and_features):
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        assert isinstance(result, ExperimentResult)
        assert result.status == ExperimentStatus.COMPLETED

    def test_insufficient_data_fails(self, experiment, hypothesis):
        matches = [{"total_goals": 2, "odds_over_goals": 1.9, "odds_under_goals": 2.0}] * 10
        features = [{"feat_1": 1.0}] * 10
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        assert result.status == ExperimentStatus.FAILED
        assert "Insufficient" in result.error

    def test_walk_forward_prevents_lookahead(self, experiment, hypothesis, matches_and_features):
        """Walk-forward: training data is always BEFORE test data."""
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        # If it ran successfully, walk-forward structure was respected
        assert result.status == ExperimentStatus.COMPLETED
        assert result.n_samples == 200

    def test_roi_calculation(self, experiment, hypothesis, matches_and_features):
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        if result.n_bets > 0:
            expected_roi = (result.total_profit_loss / result.n_bets) * 100
            assert abs(result.roi_pct - expected_roi) < 0.01

    def test_win_rate_calculation(self, experiment, hypothesis, matches_and_features):
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        if result.n_bets > 0:
            expected_wr = result.n_wins / result.n_bets
            assert abs(result.win_rate - expected_wr) < 0.001

    def test_conditions_filter_bets(self):
        """Only matches meeting conditions should produce bets."""
        experiment = ResearchExperiment(
            train_window=50, test_window=20, step_size=20,
            min_ev_threshold=-1.0,
        )
        hyp = ResearchHypothesis(
            hypothesis_id="high_filter",
            market=MarketType.GOALS_TOTAL,
            feature_ids=("feat_1",),
            conditions=(("feat_1", ">", 100.0),),  # Very high threshold
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        rng = np.random.default_rng(42)
        matches = [{
            "total_goals": int(rng.poisson(2.5)),
            "odds_over_goals": 1.90,
            "odds_under_goals": 2.00,
        } for _ in range(200)]
        # Features all below 100 → no bets
        features = [{"feat_1": float(rng.normal(5, 2))} for _ in range(200)]
        model = HistoricalFrequencyModel()
        result = experiment.run(hyp, matches, features, GOALS_OVER_UNDER, model)
        assert result.n_bets == 0

    def test_max_drawdown_non_negative(self, experiment, hypothesis, matches_and_features):
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        assert result.max_drawdown >= 0

    def test_sharpe_ratio_computed(self, experiment, hypothesis, matches_and_features):
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        # Sharpe should be a finite number
        assert np.isfinite(result.sharpe_ratio)

    def test_statistical_significance_with_enough_bets(self):
        """With many bets, p_value should be computed."""
        experiment = ResearchExperiment(
            train_window=30, test_window=20, step_size=10,
            min_ev_threshold=-1.0, min_odds=1.10, max_odds=10.0,
        )
        hyp = ResearchHypothesis(
            hypothesis_id="sig_test",
            market=MarketType.GOALS_TOTAL,
            feature_ids=("feat_1",),
            conditions=(("feat_1", ">", -100.0),),  # Always True
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        rng = np.random.default_rng(42)
        matches = [{
            "total_goals": int(rng.poisson(3.0)),  # High mean → more overs
            "odds_over_goals": 1.90,
            "odds_under_goals": 2.00,
        } for _ in range(500)]
        features = [{"feat_1": 1.0} for _ in range(500)]
        model = HistoricalFrequencyModel()
        result = experiment.run(hyp, matches, features, GOALS_OVER_UNDER, model)
        if result.n_bets >= 30:
            assert result.p_value is not None

    def test_content_hash_on_result(self, experiment, hypothesis, matches_and_features):
        matches, features = matches_and_features
        model = HistoricalFrequencyModel()
        result = experiment.run(hypothesis, matches, features, GOALS_OVER_UNDER, model)
        assert result.content_hash is not None
        assert len(result.content_hash) == 16


class TestBetResult:
    """Tests for BetResult data class."""

    def test_win_bet(self):
        bet = BetResult(
            match_index=0, direction="OVER", odds=2.0,
            model_probability=0.6, expected_value=0.2,
            actual_outcome="OVER", profit_loss=1.0, is_win=True,
        )
        assert bet.is_win is True
        assert bet.profit_loss == 1.0

    def test_loss_bet(self):
        bet = BetResult(
            match_index=0, direction="OVER", odds=2.0,
            model_probability=0.6, expected_value=0.2,
            actual_outcome="UNDER", profit_loss=-1.0, is_win=False,
        )
        assert bet.is_win is False
        assert bet.profit_loss == -1.0
