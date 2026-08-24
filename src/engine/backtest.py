"""Walk-forward out-of-sample backtest engine for x-Metrics.

Performs chronological time-series backtesting with sliding train/test
windows. Reports Net ROI, CLV, Total P&L, and Max Drawdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from src.engine.evaluator import Signal, Strategy, StrategyEvaluator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StrategyIdentityInfo:
    """Lightweight strategy identity for PredictionEvent emission during backtest.

    This is a simple data carrier — NOT the authoritative StrategyIdentity.
    It provides the minimum fields needed by PredictionEventFactory.from_backtest_bet()
    without coupling the backtester directly to the strategy_identity module.
    """

    strategy_id: str
    strategy_version: int
    content_hash: str
    model_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class XBacktestConfig:
    """Configuration for x-Metric backtesting."""

    train_window: int = 200
    test_window: int = 50
    step_size: int = 50
    base_stake: float = 1.0
    min_odds: float = 1.50
    max_odds: float = 5.00

    def __post_init__(self) -> None:
        if self.train_window < 1:
            raise ValueError("train_window must be >= 1")
        if self.test_window < 1:
            raise ValueError("test_window must be >= 1")
        if self.step_size < 1:
            raise ValueError("step_size must be >= 1")
        if self.base_stake <= 0:
            raise ValueError("base_stake must be > 0")


@dataclass(frozen=True, slots=True)
class XBetRecord:
    """Record of a single bet placed during backtesting."""

    match_index: int
    strategy_name: str
    direction: str
    odds: float
    stake: float
    outcome: str  # "WIN" | "LOSS" | "VOID"
    profit_loss: float
    model_edge_pct: float  # Renamed from 'clv' — this is NOT CLV, it is model edge
    clv: float | None = None  # Real CLV (requires closing odds); None = unavailable


@dataclass(frozen=True, slots=True)
class FoldMetrics:
    """Metrics for a single walk-forward fold."""

    fold_index: int
    n_bets: int
    total_staked: float
    profit_loss: float
    roi_pct: float
    win_rate: float


@dataclass(frozen=True, slots=True)
class XBacktestResult:
    """Aggregate results from a full walk-forward backtest."""

    total_bets: int
    total_staked: float
    total_profit_loss: float
    net_roi_pct: float
    avg_model_edge_pct: float  # Renamed from avg_clv_pct — NOT real CLV
    max_drawdown_pct: float
    win_rate: float
    folds: tuple[FoldMetrics, ...]
    bet_records: tuple[XBetRecord, ...]
    prediction_events: tuple = ()  # PredictionEvent objects (when strategy identity available)

    def summary(self) -> dict:
        """Return a summary dict suitable for serialization."""
        return {
            "total_bets": self.total_bets,
            "total_staked": round(self.total_staked, 2),
            "total_profit_loss": round(self.total_profit_loss, 2),
            "net_roi_pct": round(self.net_roi_pct, 2),
            "avg_model_edge_pct": round(self.avg_model_edge_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "win_rate": round(self.win_rate, 2),
            "n_folds": len(self.folds),
            "n_prediction_events": len(self.prediction_events),
        }


class XMetricBacktester:
    """Walk-forward backtester for x-Metric strategies.

    Ensures look-ahead-free operation: coefficients and strategies
    are frozen during test windows — no information from the future
    leaks into past predictions.
    """

    def __init__(
        self,
        config: XBacktestConfig | None = None,
        evaluator: StrategyEvaluator | None = None,
        strategy_identities: Dict[str, "StrategyIdentityInfo"] | None = None,
    ) -> None:
        self.config = config or XBacktestConfig()
        self.evaluator = evaluator or StrategyEvaluator()
        # Optional mapping: strategy_name → identity info for PredictionEvent emission
        self._strategy_identities = strategy_identities or {}

    def run(
        self,
        df: pd.DataFrame,
        strategies: List[Strategy],
        outcome_col: str = "actual_total",
        line_col: str = "market_line",
    ) -> XBacktestResult:
        """Execute full walk-forward backtest.

        Args:
            df: DataFrame sorted by date_unix with x-Metric columns computed.
            strategies: List of strategies to evaluate.
            outcome_col: Column containing actual match outcome for settlement.
            line_col: Column containing the market line for settlement.

        Returns:
            XBacktestResult with full metrics and bet records.
        """
        df = df.sort_values("date_unix").reset_index(drop=True)
        folds = self._generate_folds(len(df))

        if not folds:
            logger.warning("Insufficient data for walk-forward folds")
            return self._empty_result()

        all_bets: List[XBetRecord] = []
        all_predictions: list = []  # PredictionEvent objects
        fold_metrics: List[FoldMetrics] = []

        for fold_idx, (train_range, test_range) in enumerate(folds):
            train_df = df.iloc[train_range[0]:train_range[1]]
            test_df = df.iloc[test_range[0]:test_range[1]]

            fold_bets, fold_predictions = self._run_fold(
                train_df, test_df, strategies, outcome_col, line_col
            )
            all_bets.extend(fold_bets)
            all_predictions.extend(fold_predictions)

            # Compute fold-level metrics
            fm = self._compute_fold_metrics(fold_idx, fold_bets)
            fold_metrics.append(fm)

        # Aggregate
        result = self._aggregate_results(all_bets, fold_metrics, all_predictions)
        logger.info(
            "Backtest complete: %d folds, %d bets, ROI=%.2f%%, MaxDD=%.2f%%",
            len(folds),
            result.total_bets,
            result.net_roi_pct,
            result.max_drawdown_pct,
        )
        return result

    def _generate_folds(self, n: int) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Generate sliding train/test window ranges.

        Returns list of ((train_start, train_end), (test_start, test_end)).
        """
        folds = []
        start = 0
        while start + self.config.train_window + self.config.test_window <= n:
            train_start = start
            train_end = start + self.config.train_window
            test_start = train_end
            test_end = test_start + self.config.test_window
            folds.append(((train_start, train_end), (test_start, test_end)))
            start += self.config.step_size
        return folds

    def _run_fold(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        strategies: List[Strategy],
        outcome_col: str,
        line_col: str,
    ) -> Tuple[List[XBetRecord], list]:
        """Execute a single fold: evaluate strategies on test data, settle bets.

        Returns:
            Tuple of (bet_records, prediction_events).
        """
        # Evaluate signals on test window only
        signals = self.evaluator.evaluate(test_df.reset_index(drop=True), strategies)

        bets: List[XBetRecord] = []
        predictions: list = []  # PredictionEvent objects

        for signal in signals:
            # Map signal index back to test_df row
            if signal.match_index >= len(test_df):
                continue

            row = test_df.iloc[signal.match_index]
            odds = signal.odds

            # Filter by odds bounds
            if odds < self.config.min_odds or odds > self.config.max_odds:
                continue

            # Settle the bet
            outcome, profit_loss = self._settle_bet(
                row, signal, odds, outcome_col, line_col
            )

            # Model edge (NOT CLV — real CLV requires closing odds which are unavailable)
            model_edge_pct = signal.edge * 100.0

            bet = XBetRecord(
                match_index=int(test_df.index[signal.match_index]),
                strategy_name=signal.strategy_name,
                direction=signal.direction,
                odds=odds,
                stake=self.config.base_stake,
                outcome=outcome,
                profit_loss=profit_loss,
                model_edge_pct=model_edge_pct,
                clv=None,  # Real CLV unavailable without closing odds
            )
            bets.append(bet)

            # Emit PredictionEvent if strategy identity is available
            identity_info = self._strategy_identities.get(signal.strategy_name)
            if identity_info is not None:
                prediction = self._create_prediction_event(
                    row, signal, odds, model_edge_pct, outcome, identity_info
                )
                if prediction is not None:
                    predictions.append(prediction)

        return bets, predictions

    def _settle_bet(
        self,
        row: pd.Series,
        signal: Signal,
        odds: float,
        outcome_col: str,
        line_col: str,
    ) -> Tuple[str, float]:
        """Determine bet outcome and profit/loss.

        For OVER/UNDER: compare actual total against market line.
        """
        actual = row.get(outcome_col)
        line = row.get(line_col)

        if pd.isna(actual) or pd.isna(line):
            return "VOID", 0.0

        actual = float(actual)
        line = float(line)
        stake = self.config.base_stake

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

        # Push (exact line hit) = void
        if actual == line:
            return "VOID", 0.0

        if won:
            return "WIN", stake * (odds - 1.0)
        else:
            return "LOSS", -stake

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

    def _aggregate_results(
        self,
        all_bets: List[XBetRecord],
        fold_metrics: List[FoldMetrics],
        prediction_events: list | None = None,
    ) -> XBacktestResult:
        """Compute aggregate backtest results from all bets."""
        if not all_bets:
            return self._empty_result()

        total_staked = sum(b.stake for b in all_bets)
        total_pl = sum(b.profit_loss for b in all_bets)
        wins = sum(1 for b in all_bets if b.outcome == "WIN")
        settled = sum(1 for b in all_bets if b.outcome != "VOID")
        clv_values = [b.model_edge_pct for b in all_bets]

        # Max drawdown from cumulative P&L
        max_dd = self._compute_max_drawdown(all_bets)

        return XBacktestResult(
            total_bets=len(all_bets),
            total_staked=total_staked,
            total_profit_loss=total_pl,
            net_roi_pct=(total_pl / total_staked * 100.0) if total_staked > 0 else 0.0,
            avg_model_edge_pct=float(np.mean(clv_values)) if clv_values else 0.0,
            max_drawdown_pct=max_dd,
            win_rate=(wins / settled * 100.0) if settled > 0 else 0.0,
            folds=tuple(fold_metrics),
            bet_records=tuple(all_bets),
            prediction_events=tuple(prediction_events or []),
        )

    def _compute_max_drawdown(self, bets: List[XBetRecord]) -> float:
        """Compute max drawdown as percentage of total staked."""
        if not bets:
            return 0.0

        cumulative = np.cumsum([b.profit_loss for b in bets])
        peak = np.maximum.accumulate(cumulative)
        drawdowns = peak - cumulative
        max_dd = float(np.max(drawdowns))
        total_staked = sum(b.stake for b in bets)

        return (max_dd / total_staked * 100.0) if total_staked > 0 else 0.0

    def _create_prediction_event(
        self,
        row: pd.Series,
        signal: Signal,
        odds: float,
        model_edge_pct: float,
        outcome: str,
        identity_info: "StrategyIdentityInfo",
    ):
        """Create a PredictionEvent from a settled backtest bet.

        Returns None if required data is missing from the row.
        """
        from src.domain.factories import PredictionEventFactory

        # Extract match identity from row (graceful fallback for missing columns)
        match_id = int(row.get("match_id", 0))
        match_date_unix = int(row.get("date_unix", 0))
        home_team = str(row.get("home_team", "Unknown"))
        away_team = str(row.get("away_team", "Unknown"))
        league_id = int(row.get("league_id", 0))
        market_line_val = row.get("market_line")
        market_line = float(market_line_val) if pd.notna(market_line_val) else 2.5

        return PredictionEventFactory.from_backtest_bet(
            strategy_id=identity_info.strategy_id,
            strategy_version=identity_info.strategy_version,
            strategy_content_hash=identity_info.content_hash,
            match_id=match_id,
            match_date_unix=match_date_unix,
            home_team=home_team,
            away_team=away_team,
            league_id=league_id,
            direction=signal.direction,
            odds=odds,
            model_edge_pct=model_edge_pct,
            outcome=outcome,
            market_type="OVER_UNDER",
            market_line=market_line,
            model_version_id=identity_info.model_version_id,
        )

    def _empty_result(self) -> XBacktestResult:
        """Return an empty result for edge cases."""
        return XBacktestResult(
            total_bets=0,
            total_staked=0.0,
            total_profit_loss=0.0,
            net_roi_pct=0.0,
            avg_model_edge_pct=0.0,
            max_drawdown_pct=0.0,
            win_rate=0.0,
            folds=(),
            bet_records=(),
        )
