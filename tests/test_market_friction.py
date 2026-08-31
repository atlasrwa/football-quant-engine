"""Unit tests for market friction and liquidity engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.engine.analysis.backtest import XBacktestConfig, XBetRecord
from src.engine.analysis.evaluator import Condition, Strategy
from src.engine.analysis.friction import (
    DEFAULT_LEAGUE_TIERS,
    FrictionAdjustedBacktester,
    MarketFrictionConfig,
)


class TestMarketFrictionConfig:
    """Tests for MarketFrictionConfig."""

    def test_default_values(self):
        """Default config has expected margin values."""
        config = MarketFrictionConfig()

        assert config.margin_match_odds == 0.030
        assert config.margin_corners == 0.060
        assert config.margin_cards == 0.060
        assert config.margin_offsides == 0.060

    def test_get_margin_corners(self):
        """Corner markets return corners margin."""
        config = MarketFrictionConfig()

        assert config.get_margin("corners_over_under") == 0.060
        assert config.get_margin("xC_corners") == 0.060

    def test_get_margin_cards(self):
        """Card markets return cards margin."""
        config = MarketFrictionConfig()

        assert config.get_margin("cards_over_under") == 0.060
        assert config.get_margin("xB_bookings") == 0.060

    def test_get_margin_offsides(self):
        """Offside markets return offsides margin."""
        config = MarketFrictionConfig()

        assert config.get_margin("offsides_over_under") == 0.060
        assert config.get_margin("xO_offsides") == 0.060

    def test_get_margin_match_odds(self):
        """Unknown/match odds markets return match odds margin."""
        config = MarketFrictionConfig()

        assert config.get_margin("match_odds") == 0.030
        assert config.get_margin("asian_handicap") == 0.030
        assert config.get_margin("unknown_market") == 0.030

    def test_get_slippage_by_tier(self):
        """Slippage BPS correct by tier."""
        config = MarketFrictionConfig()

        assert config.get_slippage_bps(1) == 15
        assert config.get_slippage_bps(2) == 30
        assert config.get_slippage_bps(3) == 50

    def test_get_slippage_unknown_tier(self):
        """Unknown tier defaults to tier 3 (most conservative)."""
        config = MarketFrictionConfig()

        assert config.get_slippage_bps(99) == 50

    def test_get_liquidity_cap_by_tier(self):
        """Liquidity caps correct by tier."""
        config = MarketFrictionConfig()

        assert config.get_liquidity_cap(1) == 10.0
        assert config.get_liquidity_cap(2) == 5.0
        assert config.get_liquidity_cap(3) == 2.0

    def test_custom_values(self):
        """Custom config values override defaults."""
        config = MarketFrictionConfig(
            margin_corners=0.10,
            slippage_bps_tier1=25,
            liquidity_cap_tier1=20.0,
        )

        assert config.get_margin("corners") == 0.10
        assert config.get_slippage_bps(1) == 25
        assert config.get_liquidity_cap(1) == 20.0


class TestFrictionAdjustedBacktester:
    """Tests for FrictionAdjustedBacktester."""

    def _make_df(self, n: int = 300) -> pd.DataFrame:
        """Create a DataFrame suitable for backtesting with friction."""
        rng = np.random.default_rng(123)
        return pd.DataFrame({
            "date_unix": np.arange(n) * 86400,
            "league_id": rng.choice([1625, 4759, 3001], n),
            "home_xC": rng.uniform(1.5, 3.5, n),
            "away_xC": rng.uniform(1.5, 3.5, n),
            "over_odds": rng.uniform(1.70, 2.50, n),
            "under_odds": rng.uniform(1.70, 2.50, n),
            "actual_total": rng.uniform(0, 6, n),
            "market_line": np.full(n, 2.5),
        })

    def _make_strategy(self) -> Strategy:
        """Create a test strategy targeting corners."""
        return Strategy(
            name="High xC Over",
            metric="xC",
            market="corners_over_under",
            conditions=(Condition(field="home_xC", op=">", value=2.5),),
            logic="and",
            direction="OVER",
            min_odds=1.50,
        )

    def test_friction_reduces_roi(self):
        """Friction-adjusted backtest has lower ROI than vanilla."""
        from src.engine.analysis.backtest import XMetricBacktester

        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        df = self._make_df(300)
        strategy = self._make_strategy()

        # Vanilla
        vanilla = XMetricBacktester(config=config)
        vanilla_result = vanilla.run(df, [strategy])

        # Friction
        friction_bt = FrictionAdjustedBacktester(config=config)
        friction_result = friction_bt.run(df, [strategy])

        # Friction should reduce ROI (or at minimum not increase it)
        if vanilla_result.total_bets > 0 and friction_result.total_bets > 0:
            assert friction_result.net_roi_pct <= vanilla_result.net_roi_pct

    def test_vig_reduces_odds(self):
        """_apply_vig reduces odds by margin percentage."""
        bt = FrictionAdjustedBacktester()

        # 6% margin on corners
        result = bt._apply_vig(2.00, "corners_over_under")
        expected = 2.00 * (1.0 - 0.06)
        assert result == pytest.approx(expected)

        # 3% margin on match odds
        result = bt._apply_vig(2.00, "match_odds")
        expected = 2.00 * (1.0 - 0.03)
        assert result == pytest.approx(expected)

    def test_slippage_reduces_odds(self):
        """_apply_slippage reduces odds by BPS percentage."""
        bt = FrictionAdjustedBacktester()

        # Tier 1: 15 bps
        result = bt._apply_slippage(2.00, 1)
        expected = 2.00 - (15 / 10000.0) * 2.00
        assert result == pytest.approx(expected)

        # Tier 3: 50 bps
        result = bt._apply_slippage(2.00, 3)
        expected = 2.00 - (50 / 10000.0) * 2.00
        assert result == pytest.approx(expected)

    def test_liquidity_cap_enforced(self):
        """_cap_stake limits stake to tier cap."""
        bt = FrictionAdjustedBacktester()

        assert bt._cap_stake(15.0, 1) == 10.0  # Tier 1 cap
        assert bt._cap_stake(3.0, 2) == 3.0    # Below cap
        assert bt._cap_stake(5.0, 3) == 2.0    # Tier 3 cap

    def test_effective_odds_floor(self):
        """Effective odds never go below 1.01."""
        # With extreme friction, odds could theoretically go below 1.0
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20, min_odds=1.01)
        friction = MarketFrictionConfig(
            margin_corners=0.50,  # 50% margin — extreme
            slippage_bps_tier3=500,  # 5% slippage — extreme
        )
        bt = FrictionAdjustedBacktester(config=config, friction=friction)

        # Even with extreme friction, effective odds should be >= 1.01
        df = self._make_df(300)
        result = bt.run(df, [self._make_strategy()])

        for bet in result.bet_records:
            assert bet.odds >= 1.01

    def test_league_tier_lookup(self):
        """League tier correctly maps from DEFAULT_LEAGUE_TIERS."""
        bt = FrictionAdjustedBacktester()

        # Premier League = Tier 1
        row = pd.Series({"league_id": 1625})
        assert bt._get_league_tier(row) == 1

        # Eredivisie = Tier 2
        row = pd.Series({"league_id": 4759})
        assert bt._get_league_tier(row) == 2

        # Unknown = Tier 3
        row = pd.Series({"league_id": 9999})
        assert bt._get_league_tier(row) == 3

    def test_custom_league_tiers(self):
        """Custom league tier mapping is respected."""
        custom_tiers = {9999: 1}  # Treat league 9999 as tier 1
        bt = FrictionAdjustedBacktester(league_tiers=custom_tiers)

        row = pd.Series({"league_id": 9999})
        assert bt._get_league_tier(row) == 1

    def test_backtest_with_no_data(self):
        """Empty DataFrame returns empty result."""
        bt = FrictionAdjustedBacktester(
            config=XBacktestConfig(train_window=200, test_window=50, step_size=50)
        )
        df = self._make_df(50)  # Too small

        result = bt.run(df, [self._make_strategy()])
        assert result.total_bets == 0

    def test_bet_records_have_friction_adjusted_odds(self):
        """Bet records contain friction-adjusted (lower) odds."""
        config = XBacktestConfig(train_window=50, test_window=20, step_size=20)
        bt = FrictionAdjustedBacktester(config=config)
        df = self._make_df(300)

        result = bt.run(df, [self._make_strategy()])

        if result.total_bets > 0:
            # All recorded odds should be less than the max raw odds (2.50)
            # due to vig + slippage deduction
            max_raw = 2.50
            # With 6% vig + slippage, max effective ≈ 2.50 * 0.94 * 0.995 ≈ 2.34
            for bet in result.bet_records:
                assert bet.odds < max_raw

    def test_combined_friction_impact(self):
        """Combined vig + slippage gives expected compound reduction."""
        bt = FrictionAdjustedBacktester()

        raw_odds = 2.00
        market = "corners_over_under"
        tier = 2

        after_vig = bt._apply_vig(raw_odds, market)  # 2.0 * 0.94 = 1.88
        after_slip = bt._apply_slippage(after_vig, tier)  # 1.88 - 30/10000 * 1.88

        expected_vig = 2.00 * (1 - 0.06)
        expected_slip = expected_vig - (30 / 10000) * expected_vig

        assert after_vig == pytest.approx(expected_vig)
        assert after_slip == pytest.approx(expected_slip)
