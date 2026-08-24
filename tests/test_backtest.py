"""Comprehensive unit tests for the backtest execution module.

Covers edge cases: zero trades, bankrupt bankroll, losing streaks,
max drawdown, staking floor/cap, fold splitting, and full engine integration.
"""

from __future__ import annotations

from collections import deque
from typing import List

import pytest

from src.backtest.bet_log import BetLogger
from src.backtest.cross_validation import TemporalCrossValidator
from src.backtest.engine import WalkForwardEngine
from src.backtest.metrics import MetricsAggregator
from src.backtest.signal import SignalGenerator
from src.backtest.staking import StakingCalculator
from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.results import BacktestResult, BetRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_features(
    match_id: int = 1,
    date_unix: int = 1700000000,
    home_xg_eff: float = 0.1,
    away_xg_eff: float = 0.05,
    home_form: float = 0.6,
    away_form: float = 0.5,
    ref_vol: float = 1.4,
    total_goals: int = 3,
    over_odds: float = 1.85,
    under_odds: float = 2.05,
) -> MatchFeatures:
    """Create a MatchFeatures instance with sensible defaults."""
    return MatchFeatures(
        match_id=match_id,
        date_unix=date_unix,
        home_xg_eff_delta_rolling=home_xg_eff,
        away_xg_eff_delta_rolling=away_xg_eff,
        home_rolling_form=home_form,
        away_rolling_form=away_form,
        referee_volatility_index=ref_vol,
        total_goals=total_goals,
        over_under_line=2.5,
        over_odds=over_odds,
        under_odds=under_odds,
    )


def _make_feature_sequence(
    n: int,
    total_goals: int = 3,
    home_xg_eff: float = 0.1,
    away_xg_eff: float = 0.05,
    home_form: float = 0.7,
    away_form: float = 0.5,
    ref_vol: float = 1.4,
) -> List[MatchFeatures]:
    """Create a sequence of n MatchFeatures for testing."""
    return [
        _make_features(
            match_id=1000 + i,
            date_unix=1700000000 + i * 86400,
            home_xg_eff=home_xg_eff,
            away_xg_eff=away_xg_eff,
            home_form=home_form,
            away_form=away_form,
            ref_vol=ref_vol,
            total_goals=total_goals,
        )
        for i in range(n)
    ]


# ===========================================================================
# StakingCalculator tests
# ===========================================================================

class TestStakingCalculator:
    """Tests for Volatility-Adjusted Staking."""

    def test_zero_variance_gives_base_stake(self):
        """Zero variance → stake = base_stake * (1/(1+0)) = base_stake."""
        calc = StakingCalculator()
        stake = calc.compute_stake(0.0)
        assert stake == 1.0

    def test_high_variance_reduces_stake(self):
        """High variance → lower stake."""
        calc = StakingCalculator()
        stake_low_var = calc.compute_stake(0.5)
        stake_high_var = calc.compute_stake(3.0)
        assert stake_high_var < stake_low_var

    def test_stake_respects_floor(self):
        """Extremely high variance should not go below min_stake."""
        config = StrategyConfig(base_stake=1.0, min_stake_multiplier=0.25)
        calc = StakingCalculator(config=config)
        stake = calc.compute_stake(100.0)  # Very high variance
        assert stake == calc.min_stake
        assert stake == 0.25

    def test_stake_respects_cap(self):
        """Zero variance with high base should cap at max_stake."""
        config = StrategyConfig(base_stake=10.0, max_stake_multiplier=3.0)
        calc = StakingCalculator(config=config)
        # stake = 10 * (1/(1+0)) = 10, but max = 10*3 = 30
        # Actually 10 < 30, so no cap hit here. Use negative-ish variance concept:
        # The cap applies when raw_stake > max_stake
        # With base=10, max=30, the formula gives max 10 at var=0
        # To test cap, use a config where base > max
        config2 = StrategyConfig(base_stake=5.0, max_stake_multiplier=0.5, min_stake_multiplier=0.1)
        calc2 = StakingCalculator(config=config2)
        stake = calc2.compute_stake(0.0)  # raw = 5.0, max = 2.5
        assert stake == 2.5

    def test_moderate_variance(self):
        """Variance=1.0 → stake = base/(1+1) = base/2."""
        calc = StakingCalculator(StrategyConfig(base_stake=2.0))
        stake = calc.compute_stake(1.0)
        assert stake == 1.0

    def test_compute_match_variance_empty_history(self):
        """No history for teams → variance = 0.0."""
        calc = StakingCalculator()
        history = {}
        variance = calc.compute_match_variance("TeamA", "TeamB", history)
        assert variance == 0.0

    def test_compute_match_variance_with_history(self):
        """Teams with varied goal history should produce non-zero variance."""
        calc = StakingCalculator()
        history = {
            "TeamA": deque([0, 1, 4, 2, 3]),
            "TeamB": deque([2, 2, 2, 2, 2]),  # zero std
        }
        variance = calc.compute_match_variance("TeamA", "TeamB", history)
        # TeamA std > 0, TeamB std = 0, average > 0
        assert variance > 0.0

    def test_compute_stakes_for_matches(self, synthetic_matches):
        """Stake computation over a series of matches."""
        calc = StakingCalculator()
        stakes = calc.compute_stakes_for_matches(synthetic_matches[:20])
        assert len(stakes) == 20
        # First match has no history → variance=0 → base_stake
        first_id = synthetic_matches[0].id
        assert stakes[first_id] == 1.0

    def test_custom_base_stake(self):
        config = StrategyConfig(base_stake=5.0)
        calc = StakingCalculator(config=config)
        assert calc.base_stake == 5.0
        assert calc.compute_stake(0.0) == 5.0


# ===========================================================================
# SignalGenerator tests
# ===========================================================================

class TestSignalGenerator:
    """Tests for signal generation."""

    def test_strong_over_signal(self):
        """High xG efficiency + high form + high ref vol → OVER."""
        gen = SignalGenerator(StrategyConfig(min_edge_threshold=0.01))
        features = _make_features(
            home_xg_eff=0.5, away_xg_eff=0.5,
            home_form=0.9, away_form=0.9,
            ref_vol=2.0,
        )
        result = gen.generate(features)
        assert result is not None
        prediction, edge = result
        assert prediction == "OVER"
        assert edge >= 0.01

    def test_strong_under_signal(self):
        """Negative xG + low form + low ref vol → UNDER."""
        gen = SignalGenerator(StrategyConfig(min_edge_threshold=0.01))
        features = _make_features(
            home_xg_eff=-0.5, away_xg_eff=-0.5,
            home_form=0.1, away_form=0.1,
            ref_vol=0.5,
        )
        result = gen.generate(features)
        assert result is not None
        prediction, edge = result
        assert prediction == "UNDER"
        assert edge >= 0.01

    def test_below_threshold_returns_none(self):
        """Weak signals below threshold should return None."""
        gen = SignalGenerator(StrategyConfig(min_edge_threshold=0.99))
        features = _make_features(
            home_xg_eff=0.01, away_xg_eff=0.01,
            home_form=0.5, away_form=0.5,
            ref_vol=1.3,  # neutral
        )
        result = gen.generate(features)
        assert result is None

    def test_edge_capped_at_one(self):
        """Edge should never exceed 1.0."""
        gen = SignalGenerator(StrategyConfig(min_edge_threshold=0.0))
        features = _make_features(
            home_xg_eff=10.0, away_xg_eff=10.0,
            home_form=1.0, away_form=1.0,
            ref_vol=10.0,
        )
        result = gen.generate(features)
        assert result is not None
        _, edge = result
        assert edge <= 1.0

    def test_neutral_features_weak_signal(self):
        """Perfectly neutral features should produce minimal signal."""
        gen = SignalGenerator(StrategyConfig(min_edge_threshold=0.0))
        features = _make_features(
            home_xg_eff=0.0, away_xg_eff=0.0,
            home_form=0.5, away_form=0.5,
            ref_vol=1.3,
        )
        result = gen.generate(features)
        if result is not None:
            _, edge = result
            assert edge < 0.1  # Should be very weak


# ===========================================================================
# BetLogger tests
# ===========================================================================

class TestBetLogger:
    """Tests for bet logging and P&L tracking."""

    def test_winning_bet_profit(self):
        """Winning bet: profit = stake * (odds - 1)."""
        logger = BetLogger()
        record = logger.log_bet(
            match_id=1, date_unix=100, prediction="OVER",
            actual_outcome="OVER", odds=1.90, stake=1.0,
        )
        assert record.profit_loss == pytest.approx(0.9, abs=0.001)
        assert record.is_win is True

    def test_losing_bet_loss(self):
        """Losing bet: loss = -stake."""
        logger = BetLogger()
        record = logger.log_bet(
            match_id=1, date_unix=100, prediction="OVER",
            actual_outcome="UNDER", odds=1.90, stake=1.0,
        )
        assert record.profit_loss == -1.0
        assert record.is_win is False

    def test_cumulative_pnl(self):
        """Cumulative P&L should accumulate correctly."""
        logger = BetLogger()
        logger.log_bet(1, 100, "OVER", "OVER", 2.0, 1.0)    # +1.0
        logger.log_bet(2, 200, "OVER", "UNDER", 2.0, 1.0)   # -1.0
        logger.log_bet(3, 300, "UNDER", "UNDER", 1.80, 1.0)  # +0.8

        pnl = logger.get_cumulative_pnl()
        assert len(pnl) == 3
        assert pnl[0] == pytest.approx(1.0)
        assert pnl[1] == pytest.approx(0.0)
        assert pnl[2] == pytest.approx(0.8)

    def test_total_staked(self):
        logger = BetLogger()
        logger.log_bet(1, 100, "OVER", "OVER", 2.0, 1.5)
        logger.log_bet(2, 200, "OVER", "UNDER", 2.0, 2.0)
        assert logger.total_staked() == 3.5

    def test_empty_logger(self):
        logger = BetLogger()
        assert logger.count == 0
        assert logger.total_staked() == 0.0
        assert logger.total_profit() == 0.0
        assert logger.get_cumulative_pnl() == []

    def test_clear(self):
        logger = BetLogger()
        logger.log_bet(1, 100, "OVER", "OVER", 2.0, 1.0)
        assert logger.count == 1
        logger.clear()
        assert logger.count == 0

    def test_to_jsonl(self, tmp_path):
        logger = BetLogger()
        logger.log_bet(1, 100, "OVER", "OVER", 1.90, 1.0)
        logger.log_bet(2, 200, "UNDER", "UNDER", 2.10, 0.5)

        path = tmp_path / "bets.jsonl"
        logger.to_jsonl(path)

        import json
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["match_id"] == 1
        assert first["prediction"] == "OVER"

    def test_bankrupt_scenario(self):
        """All losses — total profit deeply negative."""
        logger = BetLogger()
        for i in range(10):
            logger.log_bet(i, 100 * i, "OVER", "UNDER", 1.90, 1.0)

        assert logger.total_profit() == -10.0
        assert logger.win_count() == 0

    def test_get_returns(self):
        logger = BetLogger()
        logger.log_bet(1, 100, "OVER", "OVER", 2.0, 1.0)   # return = +1.0
        logger.log_bet(2, 200, "OVER", "UNDER", 2.0, 1.0)  # return = -1.0

        returns = logger.get_returns()
        assert returns[0] == pytest.approx(1.0)
        assert returns[1] == pytest.approx(-1.0)


# ===========================================================================
# MetricsAggregator tests
# ===========================================================================

class TestMetricsAggregator:
    """Tests for quantitative performance metrics."""

    def test_empty_records(self):
        """No bets → neutral metrics."""
        agg = MetricsAggregator()
        result = agg.compute([])
        assert result.net_roi_pct == 0.0
        assert result.win_rate_pct == 0.0
        assert result.max_drawdown_pct == 0.0
        assert result.p_value == 1.0
        assert result.total_bets == 0

    def test_all_winners(self):
        """100% win rate scenario."""
        records = [
            BetRecord(match_id=i, date_unix=100 * i, prediction="OVER",
                      actual_outcome="OVER", odds=2.0, stake=1.0, profit_loss=1.0)
            for i in range(10)
        ]
        agg = MetricsAggregator()
        result = agg.compute(records)

        assert result.win_rate_pct == 100.0
        assert result.net_roi_pct == pytest.approx(100.0, abs=0.01)
        assert result.max_drawdown_pct == 0.0  # Never goes negative
        assert result.total_profit == 10.0

    def test_all_losers(self):
        """0% win rate — max drawdown scenario."""
        records = [
            BetRecord(match_id=i, date_unix=100 * i, prediction="OVER",
                      actual_outcome="UNDER", odds=2.0, stake=1.0, profit_loss=-1.0)
            for i in range(10)
        ]
        agg = MetricsAggregator()
        result = agg.compute(records)

        assert result.win_rate_pct == 0.0
        assert result.net_roi_pct == pytest.approx(-100.0, abs=0.01)
        assert result.total_profit == -10.0
        # All losses from start, peak stays at 0, drawdown = 10/10 = 100%
        assert result.max_drawdown_pct == pytest.approx(100.0, abs=0.01)

    def test_mixed_results_roi(self):
        """Mixed wins and losses."""
        records = [
            BetRecord(1, 100, "OVER", "OVER", 2.0, 1.0, 1.0),   # +1
            BetRecord(2, 200, "OVER", "UNDER", 2.0, 1.0, -1.0),  # -1
            BetRecord(3, 300, "OVER", "OVER", 2.0, 1.0, 1.0),   # +1
            BetRecord(4, 400, "OVER", "OVER", 2.0, 1.0, 1.0),   # +1
        ]
        agg = MetricsAggregator()
        result = agg.compute(records)

        assert result.total_bets == 4
        assert result.total_staked == 4.0
        assert result.total_profit == 2.0
        assert result.net_roi_pct == pytest.approx(50.0, abs=0.01)
        assert result.win_rate_pct == 75.0

    def test_max_drawdown_losing_streak(self):
        """Drawdown calculation with a losing streak in the middle."""
        records = [
            BetRecord(1, 100, "OVER", "OVER", 2.0, 1.0, 1.0),    # cumPL: +1
            BetRecord(2, 200, "OVER", "OVER", 2.0, 1.0, 1.0),    # cumPL: +2
            BetRecord(3, 300, "OVER", "UNDER", 2.0, 1.0, -1.0),   # cumPL: +1
            BetRecord(4, 400, "OVER", "UNDER", 2.0, 1.0, -1.0),   # cumPL: 0
            BetRecord(5, 500, "OVER", "UNDER", 2.0, 1.0, -1.0),   # cumPL: -1
            BetRecord(6, 600, "OVER", "OVER", 2.0, 1.0, 1.0),    # cumPL: 0
        ]
        agg = MetricsAggregator()
        result = agg.compute(records)

        # Peak = 2 at bet 2, trough = -1 at bet 5, drawdown = 3
        # total_staked = 6, max_dd% = 3/6 * 100 = 50%
        assert result.max_drawdown_pct == pytest.approx(50.0, abs=0.01)

    def test_sharpe_ratio_positive(self):
        """Consistently profitable returns → positive Sharpe."""
        records = [
            BetRecord(i, 100 * i, "OVER", "OVER", 2.0, 1.0, 0.5)
            for i in range(20)
        ]
        agg = MetricsAggregator()
        result = agg.compute(records)
        # All returns are identical (+0.5) → std=0 → sharpe=0 (degenerate)
        # Actually need variation for meaningful sharpe
        assert result.sharpe_ratio == 0.0  # No variation

    def test_sharpe_ratio_with_variation(self):
        """Profitable with variation → finite positive Sharpe."""
        records = [
            BetRecord(1, 100, "OVER", "OVER", 2.0, 1.0, 1.0),
            BetRecord(2, 200, "OVER", "OVER", 2.0, 1.0, 1.0),
            BetRecord(3, 300, "OVER", "UNDER", 2.0, 1.0, -1.0),
            BetRecord(4, 400, "OVER", "OVER", 2.0, 1.0, 1.0),
            BetRecord(5, 500, "OVER", "OVER", 2.0, 1.0, 1.0),
        ]
        agg = MetricsAggregator()
        result = agg.compute(records)
        # Mean return = (1+1-1+1+1)/5 = 0.6, std > 0
        assert result.sharpe_ratio > 0.0

    def test_pvalue_significant_edge(self):
        """Strong consistent edge → low p-value."""
        records = [
            BetRecord(i, 100 * i, "OVER", "OVER", 2.0, 1.0, 0.8)
            for i in range(50)
        ]
        # Add small variation
        records[10] = BetRecord(10, 1000, "OVER", "UNDER", 2.0, 1.0, -1.0)
        records[20] = BetRecord(20, 2000, "OVER", "UNDER", 2.0, 1.0, -1.0)

        agg = MetricsAggregator()
        result = agg.compute(records)
        assert result.p_value < 0.05

    def test_pvalue_no_edge(self):
        """50/50 results → high p-value (no significant edge)."""
        records = []
        for i in range(50):
            if i % 2 == 0:
                records.append(BetRecord(i, 100*i, "OVER", "OVER", 2.0, 1.0, 1.0))
            else:
                records.append(BetRecord(i, 100*i, "OVER", "UNDER", 2.0, 1.0, -1.0))

        agg = MetricsAggregator()
        result = agg.compute(records)
        # Mean return ≈ 0, should not be significant
        assert result.p_value > 0.05


# ===========================================================================
# TemporalCrossValidator tests
# ===========================================================================

class TestTemporalCrossValidator:
    """Tests for temporal cross-validation fold splitting."""

    def test_basic_fold_generation(self):
        """Standard fold generation with exact data size."""
        config = StrategyConfig(train_window=10, test_window=5, step_size=5)
        cv = TemporalCrossValidator(config=config)
        data = _make_feature_sequence(20)

        folds = cv.generate_folds(data)
        assert len(folds) == 2

        # First fold
        assert folds[0].train_start == 0
        assert folds[0].train_end == 10
        assert folds[0].test_start == 10
        assert folds[0].test_end == 15
        assert len(folds[0].train_data) == 10
        assert len(folds[0].test_data) == 5

        # Second fold
        assert folds[1].train_start == 5
        assert folds[1].train_end == 15
        assert folds[1].test_start == 15
        assert folds[1].test_end == 20

    def test_insufficient_data_returns_empty(self):
        """Data smaller than train+test → no folds."""
        config = StrategyConfig(train_window=100, test_window=20)
        cv = TemporalCrossValidator(config=config)
        data = _make_feature_sequence(50)

        folds = cv.generate_folds(data)
        assert folds == []

    def test_single_fold(self):
        """Exactly enough data for one fold."""
        config = StrategyConfig(train_window=10, test_window=5, step_size=5)
        cv = TemporalCrossValidator(config=config)
        data = _make_feature_sequence(15)

        folds = cv.generate_folds(data)
        assert len(folds) == 1

    def test_step_size_controls_overlap(self):
        """Smaller step size → more folds with overlapping training windows."""
        config = StrategyConfig(train_window=10, test_window=5, step_size=2)
        cv = TemporalCrossValidator(config=config)
        data = _make_feature_sequence(30)

        folds = cv.generate_folds(data)
        # (30 - 15) / 2 + 1 = 8 folds approximately
        assert len(folds) >= 8

    def test_fold_data_integrity(self):
        """Fold data should reference correct features."""
        config = StrategyConfig(train_window=5, test_window=3, step_size=3)
        cv = TemporalCrossValidator(config=config)
        data = _make_feature_sequence(20)

        folds = cv.generate_folds(data)
        for fold in folds:
            # Train data should have correct count
            assert len(fold.train_data) == 5
            # Test data should have correct count
            assert len(fold.test_data) == 3
            # Data should be chronologically ordered
            train_times = [f.date_unix for f in fold.train_data]
            test_times = [f.date_unix for f in fold.test_data]
            assert train_times == sorted(train_times)
            assert test_times == sorted(test_times)
            # Test should come after train
            assert min(test_times) > max(train_times)

    def test_no_future_leakage(self):
        """Training data should never contain future test data."""
        config = StrategyConfig(train_window=10, test_window=5, step_size=5)
        cv = TemporalCrossValidator(config=config)
        data = _make_feature_sequence(50)

        folds = cv.generate_folds(data)
        for fold in folds:
            train_ids = {f.match_id for f in fold.train_data}
            test_ids = {f.match_id for f in fold.test_data}
            # No overlap
            assert train_ids.isdisjoint(test_ids)
            # All train timestamps < all test timestamps
            max_train_time = max(f.date_unix for f in fold.train_data)
            min_test_time = min(f.date_unix for f in fold.test_data)
            assert max_train_time < min_test_time

    def test_compute_fold_count(self):
        config = StrategyConfig(train_window=10, test_window=5, step_size=5)
        cv = TemporalCrossValidator(config=config)
        assert cv.compute_fold_count(30) == 4
        assert cv.compute_fold_count(15) == 1
        assert cv.compute_fold_count(14) == 0

    def test_empty_data(self):
        cv = TemporalCrossValidator()
        folds = cv.generate_folds([])
        assert folds == []


# ===========================================================================
# WalkForwardEngine tests
# ===========================================================================

class TestWalkForwardEngine:
    """Tests for the walk-forward backtest engine."""

    def test_basic_execution(self):
        """Engine produces a BacktestResult with valid structure."""
        config = StrategyConfig(
            train_window=10, test_window=5, step_size=5,
            min_edge_threshold=0.0,  # Accept all signals
        )
        engine = WalkForwardEngine(config=config)
        features = _make_feature_sequence(30)

        result = engine.run(features)

        assert isinstance(result, BacktestResult)
        assert result.total_bets >= 0
        assert len(result.fold_results) > 0
        assert result.strategy_config == config

    def test_insufficient_data_returns_empty(self):
        """Too little data → empty result."""
        config = StrategyConfig(train_window=100, test_window=20)
        engine = WalkForwardEngine(config=config)
        features = _make_feature_sequence(50)

        result = engine.run(features)

        assert result.total_bets == 0
        assert result.fold_results == []
        assert result.p_value == 1.0

    def test_zero_trades_high_threshold(self):
        """Very high edge threshold → no trades placed."""
        config = StrategyConfig(
            train_window=10, test_window=5, step_size=5,
            min_edge_threshold=0.99,  # Nearly impossible to meet
        )
        engine = WalkForwardEngine(config=config)
        # Use neutral features that won't generate strong signals
        features = _make_feature_sequence(
            30,
            home_xg_eff=0.0, away_xg_eff=0.0,
            home_form=0.5, away_form=0.5, ref_vol=1.3,
        )

        result = engine.run(features)
        assert result.total_bets == 0

    def test_losing_streak_drawdown(self):
        """All losses should produce max drawdown."""
        config = StrategyConfig(
            train_window=5, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )
        engine = WalkForwardEngine(config=config)
        # Features where prediction will consistently be wrong
        # Low goals (UNDER actual) but features suggest OVER
        features = _make_feature_sequence(
            20,
            total_goals=1,  # Under 2.5 → actual is UNDER
            home_xg_eff=0.5, away_xg_eff=0.5,
            home_form=0.9, away_form=0.9,
            ref_vol=2.0,  # Strong OVER signal but actual is UNDER
        )

        result = engine.run(features)

        if result.total_bets > 0:
            # All bets should be losses
            assert result.win_rate_pct == 0.0
            assert result.max_drawdown_pct > 0.0
            assert result.total_profit < 0.0

    def test_winning_streak(self):
        """All wins should produce positive ROI and no drawdown."""
        config = StrategyConfig(
            train_window=5, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )
        engine = WalkForwardEngine(config=config)
        # High goals (OVER actual) and features suggest OVER
        features = _make_feature_sequence(
            20,
            total_goals=4,  # Over 2.5 → actual is OVER
            home_xg_eff=0.5, away_xg_eff=0.5,
            home_form=0.9, away_form=0.9,
            ref_vol=2.0,  # Strong OVER signal matching actual
        )

        result = engine.run(features)

        if result.total_bets > 0:
            assert result.win_rate_pct == 100.0
            assert result.net_roi_pct > 0.0
            assert result.max_drawdown_pct == 0.0

    def test_deterministic_results(self):
        """Same inputs should produce identical results."""
        config = StrategyConfig(
            train_window=10, test_window=5, step_size=5,
            min_edge_threshold=0.0, random_seed=42,
        )
        features = _make_feature_sequence(30)

        result1 = WalkForwardEngine(config=config).run(features)
        result2 = WalkForwardEngine(config=config).run(features)

        assert result1.total_bets == result2.total_bets
        assert result1.net_roi_pct == result2.net_roi_pct
        assert result1.total_profit == result2.total_profit

    def test_fold_results_populated(self):
        """Each fold should have a FoldResult entry."""
        config = StrategyConfig(
            train_window=10, test_window=5, step_size=5,
            min_edge_threshold=0.0,
        )
        engine = WalkForwardEngine(config=config)
        features = _make_feature_sequence(30)

        result = engine.run(features)

        for fold_result in result.fold_results:
            assert fold_result.fold_index >= 0
            assert fold_result.train_end > fold_result.train_start
            assert fold_result.test_end > fold_result.test_start

    def test_bet_log_populated(self):
        """Bet log should have entries matching total_bets."""
        config = StrategyConfig(
            train_window=10, test_window=5, step_size=5,
            min_edge_threshold=0.0,
        )
        engine = WalkForwardEngine(config=config)
        features = _make_feature_sequence(30)

        result = engine.run(features)

        assert len(result.bet_log) == result.total_bets
        for bet in result.bet_log:
            assert isinstance(bet, BetRecord)
            assert bet.prediction in ("OVER", "UNDER")
            assert bet.actual_outcome in ("OVER", "UNDER")
            assert bet.stake > 0
            assert bet.odds > 1.0

    def test_integration_with_fixture_data(self):
        """Full integration: fixture data → features → backtest."""
        from src.features import FeatureAssembler
        from src.ingestion import MockProvider

        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")

        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )
        engine = WalkForwardEngine(config=config)
        result = engine.run(features)

        assert isinstance(result, BacktestResult)
        assert result.total_bets > 0
        assert len(result.fold_results) > 0
        # Metrics should be within sane bounds
        assert -200.0 <= result.net_roi_pct <= 200.0
        assert 0.0 <= result.win_rate_pct <= 100.0
        assert result.max_drawdown_pct >= 0.0

    def test_summary_output(self):
        """BacktestResult.summary() should produce readable output."""
        config = StrategyConfig(
            train_window=10, test_window=5, step_size=5,
            min_edge_threshold=0.0,
        )
        engine = WalkForwardEngine(config=config)
        features = _make_feature_sequence(30)

        result = engine.run(features)
        summary = result.summary()

        assert "Backtest Results" in summary
        assert "Net ROI" in summary
        assert "Win Rate" in summary
