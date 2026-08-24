"""Unit tests for the x-Metric walk-forward backtest engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.engine.backtest import (
    FoldMetrics,
    XBacktestConfig,
    XBacktestResult,
    XBetRecord,
    XMetricBacktester,
)
from src.engine.evaluator import Condition, Strategy, StrategyEvaluator


class TestXBacktestConfig:
    """Tests for XBacktestConfig validation."""

    def test_default_config(self):
        """Default config creates successfully."""
        config = XBacktestConfig()
        assert config.train_window == 200
        assert config.test_window == 50
        assert config.step_size == 50

    def test_invalid_train_window(self):
        """train_window < 1 raises ValueError."""
        with pytest.raises(ValueError, match="train_window"):
            XBacktestConfig(train_window=0)

    def test_invalid_test_window(self):
        """test_window < 1 raises ValueError."""
        with pytest.raises(ValueError, match="test_window"):
            XBacktestConfig(test_window=0)

    def test_invalid_step_size(self):
        """step_size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="step_size"):
            XBacktestConfig(step_size=0)

    def test_invalid_base_stake(self):
        """base_stake <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="base_stake"):
            XBacktestConfig(base_stake=0.0)


class TestFoldGeneration:
    """Tests for walk-forward fold generation."""

    def test_basic_fold_generation(self):
        """Folds are generated correctly with default step."""
        config = XBacktestConfig(train_window=10, test_window=5, step_size=5)
        bt = XMetricBacktester(config=config)
        folds = bt._generate_folds(30)

        # 30 rows: folds at [0:10]→[10:15], [5:15]→[15:20], [10:20]→[20:25], [15:25]→[25:30]
        assert len(folds) == 4
        assert folds[0] == ((0, 10), (10, 15))
        assert folds[1] == ((5, 15), (15, 20))
        assert folds[2] == ((10, 20), (20, 25))
        assert folds[3] == ((15, 25), (25, 30))

    def test_insufficient_data_no_folds(self):
        """No folds when data is shorter than train+test."""
        config = XBacktestConfig(train_window=100, test_window=50, step_size=50)
        bt = XMetricBacktester(config=config)
        folds = bt._generate_folds(100)  # need 150 minimum

        assert len(folds) == 0

    def test_exact_fit_one_fold(self):
        """Exactly train+test rows produces one fold."""
        config = XBacktestConfig(train_window=10, test_window=5, step_size=5)
        bt = XMetricBacktester(config=config)
        folds = bt._generate_folds(15)

        assert len(folds) == 1
        assert folds[0] == ((0, 10), (10, 15))

    def test_no_overlap_in_train_test(self):
        """Train and test ranges never overlap within a fold."""
        config = XBacktestConfig(train_window=20, test_window=10, step_size=10)
        bt = XMetricBacktester(config=config)
        folds = bt._generate_folds(100)

        for (ts, te), (xs, xe) in folds:
            # Test starts where train ends
            assert xs == te
            # No overlap
            assert set(range(ts, te)).isdisjoint(set(range(xs, xe)))


class TestBacktestExecution:
    """Tests for full backtest execution."""

    def _make_df(self, n: int = 300) -> pd.DataFrame:
        """Create synthetic DataFrame with x-Metrics and outcomes."""
        rng = np.random.default_rng(123)
        return pd.DataFrame({
            "date_unix": np.arange(n) * 86400,
            "home_xC": rng.uniform(1.5, 3.5, n),
            "away_xC": rng.uniform(1.5, 3.5, n),
            "over_odds": rng.uniform(1.70, 2.30, n),
            "under_odds": rng.uniform(1.70, 2.30, n),
            "actual_total": rng.uniform(0, 6, n),
            "market_line": np.full(n, 2.5),
        })

    def _make_strategy(self) -> Strategy:
        """Create a simple test strategy."""
        return Strategy(
            name="Test xC Over",
            metric="xC",
            market="corners_over_under",
            conditions=(Condition(field="home_xC", op=">", value=2.5),),
            logic="and",
            direction="OVER",
            min_odds=1.50,
        )

    def test_full_backtest_runs(self):
        """Full backtest completes and returns XBacktestResult."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)
        strategy = self._make_strategy()

        result = bt.run(df, [strategy])

        assert isinstance(result, XBacktestResult)
        assert result.total_bets > 0
        assert len(result.folds) > 0
        assert len(result.bet_records) == result.total_bets

    def test_backtest_with_no_signals(self):
        """Backtest with impossible conditions produces zero bets."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)

        # Condition that never matches
        strategy = Strategy(
            name="Impossible",
            metric="xC",
            market="corners",
            conditions=(Condition(field="home_xC", op=">", value=999.0),),
            logic="and",
            direction="OVER",
            min_odds=1.50,
        )

        result = bt.run(df, [strategy])
        assert result.total_bets == 0
        assert result.net_roi_pct == 0.0

    def test_backtest_insufficient_data(self):
        """Backtest with too little data returns empty result."""
        config = XBacktestConfig(train_window=200, test_window=50, step_size=50)
        bt = XMetricBacktester(config=config)
        df = self._make_df(100)  # not enough

        result = bt.run(df, [self._make_strategy()])
        assert result.total_bets == 0

    def test_bet_outcomes_are_valid(self):
        """All bet records have valid outcomes."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)

        result = bt.run(df, [self._make_strategy()])

        for bet in result.bet_records:
            assert bet.outcome in ("WIN", "LOSS", "VOID")
            if bet.outcome == "WIN":
                assert bet.profit_loss > 0
            elif bet.outcome == "LOSS":
                assert bet.profit_loss < 0
            else:
                assert bet.profit_loss == 0.0

    def test_max_drawdown_non_negative(self):
        """Max drawdown is always >= 0."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)

        result = bt.run(df, [self._make_strategy()])
        assert result.max_drawdown_pct >= 0.0

    def test_win_rate_bounds(self):
        """Win rate is between 0 and 100."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)

        result = bt.run(df, [self._make_strategy()])
        if result.total_bets > 0:
            assert 0.0 <= result.win_rate <= 100.0

    def test_look_ahead_freedom(self):
        """Test data in fold N never appears in train data of fold N."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        folds = bt._generate_folds(300)

        for (train_start, train_end), (test_start, test_end) in folds:
            # Train window always comes before test window
            assert train_end <= test_start

    def test_summary_dict(self):
        """XBacktestResult.summary() returns serializable dict."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)

        result = bt.run(df, [self._make_strategy()])
        summary = result.summary()

        assert isinstance(summary, dict)
        assert "total_bets" in summary
        assert "net_roi_pct" in summary
        assert "max_drawdown_pct" in summary
        assert "n_folds" in summary

    def test_odds_filter(self):
        """Bets outside [min_odds, max_odds] are filtered."""
        config = XBacktestConfig(
            train_window=50, test_window=20, step_size=20,
            min_odds=1.80, max_odds=2.20,
        )
        bt = XMetricBacktester(config=config)
        df = self._make_df(300)

        result = bt.run(df, [self._make_strategy()])
        for bet in result.bet_records:
            assert config.min_odds <= bet.odds <= config.max_odds
