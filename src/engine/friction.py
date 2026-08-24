"""Bookmaker market friction and liquidity engine.

Models realistic execution costs: vig/margin deduction, slippage/line-drag,
and liquidity caps per league tier. Wraps XMetricBacktester to produce
friction-adjusted backtest results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from src.engine.backtest import (
    XBacktestConfig,
    XBacktestResult,
    XBetRecord,
    XMetricBacktester,
    FoldMetrics,
)
from src.engine.evaluator import Strategy, StrategyEvaluator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarketFrictionConfig:
    """Configurable market friction parameters.

    Vig margins represent the bookmaker's hold percentage deducted from odds.
    Slippage represents line movement between signal and fill.
    Liquidity caps limit maximum stake per match.
    """

    # Vig margins by market type (fractional, e.g. 0.03 = 3%)
    margin_match_odds: float = 0.030
    margin_corners: float = 0.060
    margin_cards: float = 0.060
    margin_offsides: float = 0.060

    # Slippage in basis points (100 bps = 1%)
    slippage_bps_tier1: int = 15
    slippage_bps_tier2: int = 30
    slippage_bps_tier3: int = 50

    # Liquidity caps (max units per match)
    liquidity_cap_tier1: float = 10.0
    liquidity_cap_tier2: float = 5.0
    liquidity_cap_tier3: float = 2.0

    def get_margin(self, market: str) -> float:
        """Get vig margin for a market type.

        Args:
            market: Market identifier (e.g. "corners_over_under", "match_odds").

        Returns:
            Margin as decimal fraction.
        """
        market_lower = market.lower()
        if "corner" in market_lower or "xc" in market_lower:
            return self.margin_corners
        elif "card" in market_lower or "xb" in market_lower or "booking" in market_lower:
            return self.margin_cards
        elif "offside" in market_lower or "xo" in market_lower:
            return self.margin_offsides
        else:
            return self.margin_match_odds

    def get_slippage_bps(self, league_tier: int) -> int:
        """Get slippage in basis points for a league tier.

        Args:
            league_tier: 1 (top), 2 (major), or 3 (lower).

        Returns:
            Slippage in basis points.
        """
        if league_tier == 1:
            return self.slippage_bps_tier1
        elif league_tier == 2:
            return self.slippage_bps_tier2
        else:
            return self.slippage_bps_tier3

    def get_liquidity_cap(self, league_tier: int) -> float:
        """Get maximum stake per match for a league tier.

        Args:
            league_tier: 1 (top), 2 (major), or 3 (lower).

        Returns:
            Maximum units allowed per match.
        """
        if league_tier == 1:
            return self.liquidity_cap_tier1
        elif league_tier == 2:
            return self.liquidity_cap_tier2
        else:
            return self.liquidity_cap_tier3


# Default league tier mapping (league_id → tier)
DEFAULT_LEAGUE_TIERS: dict[int, int] = {
    # Tier 1: Top 5 European leagues
    1625: 1,  # Premier League
    1635: 1,  # La Liga
    1640: 1,  # Serie A
    1645: 1,  # Bundesliga
    1632: 1,  # Ligue 1
    # Tier 2: Major leagues
    4759: 2,  # Eredivisie
    1947: 2,  # Primeira Liga
    2012: 2,  # Championship
    # Everything else defaults to Tier 3
}


class FrictionAdjustedBacktester:
    """Wraps XMetricBacktester with realistic market friction.

    Applies vig deduction, slippage, and liquidity caps to produce
    more realistic backtest results.
    """

    def __init__(
        self,
        config: XBacktestConfig | None = None,
        friction: MarketFrictionConfig | None = None,
        league_tiers: dict[int, int] | None = None,
        evaluator: StrategyEvaluator | None = None,
    ) -> None:
        """Initialize friction-adjusted backtester.

        Args:
            config: Backtest configuration.
            friction: Market friction parameters.
            league_tiers: Mapping of league_id → tier (1/2/3).
            evaluator: Strategy evaluator instance.
        """
        self.config = config or XBacktestConfig()
        self.friction = friction or MarketFrictionConfig()
        self.league_tiers = league_tiers or DEFAULT_LEAGUE_TIERS
        self.evaluator = evaluator or StrategyEvaluator()
        self._backtester = XMetricBacktester(config=self.config, evaluator=self.evaluator)

    def run(
        self,
        df: pd.DataFrame,
        strategies: List[Strategy],
        outcome_col: str = "actual_total",
        line_col: str = "market_line",
    ) -> XBacktestResult:
        """Execute walk-forward backtest with friction applied.

        Friction is applied at bet settlement time:
        1. Odds reduced by market vig
        2. Odds further reduced by slippage
        3. Stakes capped by liquidity limits

        Args:
            df: DataFrame with x-Metric columns and league_id.
            strategies: Strategies to evaluate.
            outcome_col: Actual outcome column.
            line_col: Market line column.

        Returns:
            XBacktestResult with friction-adjusted P&L.
        """
        df = df.sort_values("date_unix").reset_index(drop=True)
        folds = self._backtester._generate_folds(len(df))

        if not folds:
            logger.warning("Insufficient data for walk-forward folds")
            return self._backtester._empty_result()

        all_bets: List[XBetRecord] = []
        fold_metrics: List[FoldMetrics] = []

        for fold_idx, (train_range, test_range) in enumerate(folds):
            train_df = df.iloc[train_range[0]:train_range[1]]
            test_df = df.iloc[test_range[0]:test_range[1]]

            fold_bets = self._run_fold_with_friction(
                train_df, test_df, strategies, outcome_col, line_col
            )
            all_bets.extend(fold_bets)

            fm = self._compute_fold_metrics(fold_idx, fold_bets)
            fold_metrics.append(fm)

        result = self._backtester._aggregate_results(all_bets, fold_metrics)
        logger.info(
            "Friction backtest complete: %d folds, %d bets, ROI=%.2f%% (after friction)",
            len(folds),
            result.total_bets,
            result.net_roi_pct,
        )
        return result

    def _run_fold_with_friction(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        strategies: List[Strategy],
        outcome_col: str,
        line_col: str,
    ) -> List[XBetRecord]:
        """Execute fold with friction applied to each bet."""
        signals = self.evaluator.evaluate(
            test_df.reset_index(drop=True), strategies
        )

        bets: List[XBetRecord] = []
        for signal in signals:
            if signal.match_index >= len(test_df):
                continue

            row = test_df.iloc[signal.match_index]
            raw_odds = signal.odds

            # Determine market and league tier
            market = self._get_market_from_strategy(signal.strategy_name, strategies)
            league_tier = self._get_league_tier(row)

            # Apply friction pipeline
            odds_after_vig = self._apply_vig(raw_odds, market)
            odds_after_slippage = self._apply_slippage(odds_after_vig, league_tier)
            effective_odds = max(odds_after_slippage, 1.01)  # Floor at 1.01

            # Filter by odds bounds (using effective odds)
            if effective_odds < self.config.min_odds or effective_odds > self.config.max_odds:
                continue

            # Apply liquidity cap to stake
            raw_stake = self.config.base_stake
            capped_stake = self._cap_stake(raw_stake, league_tier)

            # Settle the bet with friction-adjusted odds
            outcome, profit_loss = self._settle_bet(
                row, signal, effective_odds, capped_stake, outcome_col, line_col
            )

            clv = signal.edge * 100.0

            bets.append(
                XBetRecord(
                    match_index=int(test_df.index[signal.match_index]),
                    strategy_name=signal.strategy_name,
                    direction=signal.direction,
                    odds=effective_odds,
                    stake=capped_stake,
                    outcome=outcome,
                    profit_loss=profit_loss,
                    clv=clv,
                )
            )

        return bets

    def _apply_vig(self, odds: float, market: str) -> float:
        """Reduce odds by market-specific vig/margin.

        effective_odds = odds * (1 - margin)
        """
        margin = self.friction.get_margin(market)
        return odds * (1.0 - margin)

    def _apply_slippage(self, odds: float, league_tier: int) -> float:
        """Apply line drag based on league tier.

        fill_odds = odds - (slippage_bps / 10000) * odds
        """
        bps = self.friction.get_slippage_bps(league_tier)
        return odds - (bps / 10000.0) * odds

    def _cap_stake(self, stake: float, league_tier: int) -> float:
        """Enforce liquidity cap on stake."""
        cap = self.friction.get_liquidity_cap(league_tier)
        return min(stake, cap)

    def _settle_bet(
        self,
        row: pd.Series,
        signal,
        odds: float,
        stake: float,
        outcome_col: str,
        line_col: str,
    ) -> tuple[str, float]:
        """Determine outcome with friction-adjusted parameters."""
        actual = row.get(outcome_col)
        line = row.get(line_col)

        if pd.isna(actual) or pd.isna(line):
            return "VOID", 0.0

        actual = float(actual)
        line = float(line)

        if signal.direction == "OVER":
            won = actual > line
        elif signal.direction == "UNDER":
            won = actual < line
        elif signal.direction == "BACK":
            won = actual > line
        elif signal.direction == "LAY":
            won = actual < line
        else:
            return "VOID", 0.0

        if actual == line:
            return "VOID", 0.0

        if won:
            return "WIN", stake * (odds - 1.0)
        else:
            return "LOSS", -stake

    def _get_market_from_strategy(
        self, strategy_name: str, strategies: List[Strategy]
    ) -> str:
        """Look up market type from strategy name."""
        for s in strategies:
            if s.name == strategy_name:
                return s.market
        return "match_odds"

    def _get_league_tier(self, row: pd.Series) -> int:
        """Determine league tier from row data."""
        league_id = row.get("league_id")
        if pd.notna(league_id):
            return self.league_tiers.get(int(league_id), 3)
        return 3  # Default to most conservative tier

    def _compute_fold_metrics(
        self, fold_index: int, bets: List[XBetRecord]
    ) -> FoldMetrics:
        """Compute metrics for a single fold."""
        if not bets:
            return FoldMetrics(
                fold_index=fold_index,
                n_bets=0,
                total_staked=0.0,
                profit_loss=0.0,
                roi_pct=0.0,
                win_rate=0.0,
            )

        total_staked = sum(b.stake for b in bets)
        profit_loss = sum(b.profit_loss for b in bets)
        wins = sum(1 for b in bets if b.outcome == "WIN")
        settled = sum(1 for b in bets if b.outcome != "VOID")

        return FoldMetrics(
            fold_index=fold_index,
            n_bets=len(bets),
            total_staked=total_staked,
            profit_loss=profit_loss,
            roi_pct=(profit_loss / total_staked * 100.0) if total_staked > 0 else 0.0,
            win_rate=(wins / settled * 100.0) if settled > 0 else 0.0,
        )
