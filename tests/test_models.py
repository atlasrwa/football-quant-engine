"""Validation tests for all core data models."""

import pytest

from src.models.match import Match
from src.models.features import MatchFeatures
from src.models.config import StrategyConfig
from src.models.results import BetRecord, FoldResult, BacktestResult


# ---------------------------------------------------------------------------
# Match tests
# ---------------------------------------------------------------------------

class TestMatch:
    """Tests for the Match dataclass."""

    def _valid_match(self, **overrides) -> Match:
        defaults = dict(
            id=1001,
            date_unix=1700000000,
            league_id=4759,
            season="2023",
            home_team="Arsenal",
            away_team="Chelsea",
            home_goals=2,
            away_goals=1,
            total_goals=3,
            home_xg=1.8,
            away_xg=1.2,
            referee="Michael Oliver",
            over_under_line=2.5,
            over_odds=1.85,
            under_odds=2.05,
        )
        defaults.update(overrides)
        return Match(**defaults)

    def test_valid_construction(self):
        m = self._valid_match()
        assert m.id == 1001
        assert m.total_goals == 3
        assert m.referee == "Michael Oliver"

    def test_optional_fields_none(self):
        m = self._valid_match(referee=None, over_odds=None, under_odds=None)
        assert m.referee is None
        assert m.over_odds is None
        assert m.under_odds is None

    def test_total_goals_mismatch_raises(self):
        with pytest.raises(ValueError, match="total_goals"):
            self._valid_match(total_goals=5)

    def test_negative_xg_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            self._valid_match(home_xg=-0.5)

    def test_negative_away_xg_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            self._valid_match(away_xg=-1.0)

    def test_zero_over_under_line_raises(self):
        with pytest.raises(ValueError, match="over_under_line"):
            self._valid_match(over_under_line=0.0)

    def test_frozen_immutability(self):
        m = self._valid_match()
        with pytest.raises(AttributeError):
            m.home_goals = 5  # type: ignore

    def test_zero_xg_valid(self):
        m = self._valid_match(home_xg=0.0, away_xg=0.0)
        assert m.home_xg == 0.0
        assert m.away_xg == 0.0


# ---------------------------------------------------------------------------
# MatchFeatures tests
# ---------------------------------------------------------------------------

class TestMatchFeatures:
    """Tests for the MatchFeatures dataclass."""

    def _valid_features(self, **overrides) -> MatchFeatures:
        defaults = dict(
            match_id=1001,
            date_unix=1700000000,
            home_xg_eff_delta_rolling=0.15,
            away_xg_eff_delta_rolling=-0.05,
            home_rolling_form=0.72,
            away_rolling_form=0.55,
            referee_volatility_index=1.35,
            total_goals=3,
            over_under_line=2.5,
            over_odds=1.85,
            under_odds=2.05,
        )
        defaults.update(overrides)
        return MatchFeatures(**defaults)

    def test_valid_construction(self):
        f = self._valid_features()
        assert f.match_id == 1001
        assert f.home_rolling_form == 0.72

    def test_home_form_out_of_range_raises(self):
        with pytest.raises(ValueError, match="home_rolling_form"):
            self._valid_features(home_rolling_form=1.5)

    def test_home_form_negative_raises(self):
        with pytest.raises(ValueError, match="home_rolling_form"):
            self._valid_features(home_rolling_form=-0.1)

    def test_away_form_out_of_range_raises(self):
        with pytest.raises(ValueError, match="away_rolling_form"):
            self._valid_features(away_rolling_form=2.0)

    def test_negative_referee_volatility_raises(self):
        with pytest.raises(ValueError, match="referee_volatility_index"):
            self._valid_features(referee_volatility_index=-0.5)

    def test_boundary_form_values(self):
        f = self._valid_features(home_rolling_form=0.0, away_rolling_form=1.0)
        assert f.home_rolling_form == 0.0
        assert f.away_rolling_form == 1.0

    def test_optional_odds_none(self):
        f = self._valid_features(over_odds=None, under_odds=None)
        assert f.over_odds is None
        assert f.under_odds is None


# ---------------------------------------------------------------------------
# StrategyConfig tests
# ---------------------------------------------------------------------------

class TestStrategyConfig:
    """Tests for the StrategyConfig dataclass."""

    def test_default_construction(self):
        cfg = StrategyConfig()
        assert cfg.train_window == 100
        assert cfg.test_window == 20
        assert cfg.step_size == 20
        assert cfg.base_stake == 1.0
        assert cfg.random_seed == 42

    def test_custom_values(self):
        cfg = StrategyConfig(train_window=200, base_stake=2.0, min_edge_threshold=0.10)
        assert cfg.train_window == 200
        assert cfg.base_stake == 2.0
        assert cfg.min_edge_threshold == 0.10

    def test_zero_train_window_raises(self):
        with pytest.raises(ValueError, match="train_window"):
            StrategyConfig(train_window=0)

    def test_zero_test_window_raises(self):
        with pytest.raises(ValueError, match="test_window"):
            StrategyConfig(test_window=0)

    def test_zero_step_size_raises(self):
        with pytest.raises(ValueError, match="step_size"):
            StrategyConfig(step_size=0)

    def test_zero_base_stake_raises(self):
        with pytest.raises(ValueError, match="base_stake"):
            StrategyConfig(base_stake=0.0)

    def test_max_less_than_min_multiplier_raises(self):
        with pytest.raises(ValueError, match="max_stake_multiplier"):
            StrategyConfig(max_stake_multiplier=0.1, min_stake_multiplier=0.5)

    def test_edge_threshold_out_of_range_raises(self):
        with pytest.raises(ValueError, match="min_edge_threshold"):
            StrategyConfig(min_edge_threshold=1.5)

    def test_negative_edge_threshold_raises(self):
        with pytest.raises(ValueError, match="min_edge_threshold"):
            StrategyConfig(min_edge_threshold=-0.01)


# ---------------------------------------------------------------------------
# BetRecord tests
# ---------------------------------------------------------------------------

class TestBetRecord:
    """Tests for the BetRecord dataclass."""

    def _valid_bet(self, **overrides) -> BetRecord:
        defaults = dict(
            match_id=1001,
            date_unix=1700000000,
            prediction="OVER",
            actual_outcome="OVER",
            odds=1.90,
            stake=1.0,
            profit_loss=0.90,
        )
        defaults.update(overrides)
        return BetRecord(**defaults)

    def test_valid_winning_bet(self):
        bet = self._valid_bet()
        assert bet.is_win is True
        assert bet.profit_loss == 0.90

    def test_valid_losing_bet(self):
        bet = self._valid_bet(actual_outcome="UNDER", profit_loss=-1.0)
        assert bet.is_win is False

    def test_invalid_prediction_raises(self):
        with pytest.raises(ValueError, match="prediction"):
            self._valid_bet(prediction="DRAW")

    def test_invalid_actual_outcome_raises(self):
        with pytest.raises(ValueError, match="actual_outcome"):
            self._valid_bet(actual_outcome="DRAW")

    def test_odds_below_one_raises(self):
        with pytest.raises(ValueError, match="odds"):
            self._valid_bet(odds=0.95)

    def test_odds_equal_one_raises(self):
        with pytest.raises(ValueError, match="odds"):
            self._valid_bet(odds=1.0)

    def test_zero_stake_raises(self):
        with pytest.raises(ValueError, match="stake"):
            self._valid_bet(stake=0.0)

    def test_negative_stake_raises(self):
        with pytest.raises(ValueError, match="stake"):
            self._valid_bet(stake=-1.0)


# ---------------------------------------------------------------------------
# FoldResult tests
# ---------------------------------------------------------------------------

class TestFoldResult:
    """Tests for the FoldResult dataclass."""

    def test_valid_construction(self):
        fr = FoldResult(
            fold_index=0,
            train_start=0,
            train_end=99,
            test_start=100,
            test_end=119,
            net_roi_pct=5.2,
            win_rate_pct=60.0,
            num_bets=15,
        )
        assert fr.fold_index == 0
        assert fr.num_bets == 15


# ---------------------------------------------------------------------------
# BacktestResult tests
# ---------------------------------------------------------------------------

class TestBacktestResult:
    """Tests for the BacktestResult dataclass."""

    def test_default_construction(self):
        result = BacktestResult(
            net_roi_pct=8.5,
            win_rate_pct=55.0,
            max_drawdown_pct=12.3,
            p_value=0.032,
            total_bets=150,
            total_staked=120.0,
            total_profit=10.2,
        )
        assert result.net_roi_pct == 8.5
        assert result.fold_results == []
        assert result.bet_log == []
        assert result.strategy_config == StrategyConfig()

    def test_summary_output(self):
        result = BacktestResult(
            net_roi_pct=8.5,
            win_rate_pct=55.0,
            max_drawdown_pct=12.3,
            p_value=0.032,
            total_bets=150,
            total_staked=120.0,
            total_profit=10.2,
        )
        summary = result.summary()
        assert "150 bets" in summary
        assert "+8.50%" in summary
        assert "55.0%" in summary
        assert "12.30%" in summary
        assert "0.0320" in summary

    def test_with_fold_results_and_bets(self):
        fold = FoldResult(
            fold_index=0,
            train_start=0,
            train_end=99,
            test_start=100,
            test_end=119,
            net_roi_pct=5.0,
            win_rate_pct=60.0,
            num_bets=10,
        )
        bet = BetRecord(
            match_id=1001,
            date_unix=1700000000,
            prediction="OVER",
            actual_outcome="OVER",
            odds=1.90,
            stake=1.0,
            profit_loss=0.90,
        )
        result = BacktestResult(
            net_roi_pct=5.0,
            win_rate_pct=60.0,
            max_drawdown_pct=8.0,
            p_value=0.05,
            total_bets=10,
            total_staked=10.0,
            total_profit=0.5,
            fold_results=[fold],
            bet_log=[bet],
        )
        assert len(result.fold_results) == 1
        assert len(result.bet_log) == 1
        assert result.bet_log[0].is_win is True
