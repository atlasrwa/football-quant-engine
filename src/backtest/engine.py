"""Walk-Forward Backtest Engine.

Orchestrates the full backtest: fold iteration, signal generation,
staking, bet logging, and metrics aggregation.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional

from src.backtest.bet_log import BetLogger
from src.backtest.cross_validation import TemporalCrossValidator
from src.backtest.metrics import MetricsAggregator
from src.backtest.signal import SignalGenerator
from src.backtest.staking import StakingCalculator
from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.match import Match
from src.models.results import BacktestResult, BetRecord, FoldResult

logger = logging.getLogger(__name__)


class WalkForwardEngine:
    """Executes a walk-forward backtest over feature vectors.

    Flow per fold:
    1. Train: fit signal parameters on training window (MVP: no-op).
    2. Test: for each match in test window:
       a. Generate signal (OVER/UNDER with edge estimate).
       b. Compute volatility-adjusted stake.
       c. Log bet outcome.
    3. Aggregate metrics across all folds.
    """

    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        """Initialize WalkForwardEngine.

        Args:
            config: Strategy configuration. Uses defaults if None.
        """
        self._config = config or StrategyConfig()
        self._signal_gen = SignalGenerator(config=self._config)
        self._staking = StakingCalculator(config=self._config)
        self._cv = TemporalCrossValidator(config=self._config)
        self._metrics = MetricsAggregator()

    @property
    def config(self) -> StrategyConfig:
        """The strategy configuration."""
        return self._config

    def run(self, features: List[MatchFeatures]) -> BacktestResult:
        """Execute the full walk-forward backtest.

        Args:
            features: List of MatchFeatures sorted chronologically.

        Returns:
            Complete BacktestResult with metrics, fold breakdowns, and bet log.
        """
        # Generate folds
        folds = self._cv.generate_folds(features)
        if not folds:
            logger.warning("No folds generated — insufficient data")
            return self._empty_result()

        # Track team goal histories for variance calculation
        team_goal_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._config.variance_rolling_window)
        )

        # Initialize history from pre-fold data (before first fold)
        # Not strictly needed for walk-forward but seeds the variance calc
        all_bet_records: List[BetRecord] = []
        fold_results: List[FoldResult] = []

        for fold in folds:
            fold_bets = self._run_fold(fold.train_data, fold.test_data, team_goal_history)
            all_bet_records.extend(fold_bets)

            # Compute per-fold metrics
            fold_metrics = self._metrics.compute(fold_bets)
            fold_result = FoldResult(
                fold_index=fold.fold_index,
                train_start=fold.train_start,
                train_end=fold.train_end,
                test_start=fold.test_start,
                test_end=fold.test_end,
                net_roi_pct=fold_metrics.net_roi_pct,
                win_rate_pct=fold_metrics.win_rate_pct,
                num_bets=fold_metrics.total_bets,
            )
            fold_results.append(fold_result)

        # Compute aggregate metrics
        aggregate = self._metrics.compute(all_bet_records)

        result = BacktestResult(
            net_roi_pct=aggregate.net_roi_pct,
            win_rate_pct=aggregate.win_rate_pct,
            max_drawdown_pct=aggregate.max_drawdown_pct,
            p_value=aggregate.p_value,
            total_bets=aggregate.total_bets,
            total_staked=aggregate.total_staked,
            total_profit=aggregate.total_profit,
            fold_results=fold_results,
            bet_log=all_bet_records,
            strategy_config=self._config,
        )

        logger.info(
            "Backtest complete: %d bets, ROI=%.2f%%, p=%.4f",
            result.total_bets, result.net_roi_pct, result.p_value,
        )
        return result

    def _run_fold(
        self,
        train_data: List[MatchFeatures],
        test_data: List[MatchFeatures],
        team_goal_history: Dict[str, deque],
    ) -> List[BetRecord]:
        """Execute a single fold: train then test.

        Args:
            train_data: Training features (used to seed history).
            test_data: Test features to generate signals on.
            team_goal_history: Mutable team goal history (updated in place).

        Returns:
            List of BetRecords from this fold's test window.
        """
        # Train phase: update team goal history with training data
        # (MVP: no model fitting, just history seeding)
        for f in train_data:
            # We don't have team names in MatchFeatures directly,
            # so we track by match total goals generically
            # For variance, we use the total_goals from features
            pass  # History is maintained at engine level via _run_test_match

        # Test phase: generate signals and place bets
        bet_logger = BetLogger()

        for match_features in test_data:
            self._run_test_match(match_features, bet_logger, team_goal_history)

        return bet_logger.records

    def _run_test_match(
        self,
        features: MatchFeatures,
        bet_logger: BetLogger,
        team_goal_history: Dict[str, deque],
    ) -> None:
        """Process a single test match: signal → stake → bet.

        Two-phase architecture:
        1. Hypothesis layer: generate signal (prediction + edge)
        2. Market layer: look up odds, compute stake, place bet

        Args:
            features: Match feature vector.
            bet_logger: Logger to record the bet.
            team_goal_history: Team goal history for variance calc.
        """
        # ═══════════════════════════════════════════════════════════════
        # PHASE 1: HYPOTHESIS LAYER — signal generation (no odds)
        # ═══════════════════════════════════════════════════════════════
        prediction, edge = self._generate_signal(features)
        if prediction is None:
            return  # Edge below threshold, skip

        # ═══════════════════════════════════════════════════════════════
        # PHASE 2: MARKET LAYER — odds lookup, staking, bet placement
        # ═══════════════════════════════════════════════════════════════
        self._place_bet(features, prediction, edge, bet_logger, team_goal_history)

    def _generate_signal(
        self, features: MatchFeatures
    ) -> tuple:
        """HYPOTHESIS LAYER: Generate a directional signal with edge estimate.

        This method ONLY:
        - Runs the signal generator (composite score from features)
        - Produces a prediction direction and edge magnitude

        It NEVER reads odds, computes stake, or places bets.

        Args:
            features: Match feature vector.

        Returns:
            Tuple of (prediction, edge) or (None, None) if edge below threshold.
        """
        signal = self._signal_gen.generate(features)
        if signal is None:
            return None, None
        return signal  # (prediction: str, edge: float)

    def _place_bet(
        self,
        features: MatchFeatures,
        prediction: str,
        edge: float,
        bet_logger: BetLogger,
        team_goal_history: Dict[str, deque],
    ) -> None:
        """MARKET LAYER: Look up odds, compute stake, and place bet.

        This method ONLY:
        - Reads odds from the match features
        - Computes volatility-adjusted stake
        - Determines actual outcome for settlement
        - Logs the bet

        It NEVER generates signals or computes probabilities.

        Args:
            features: Match feature vector (for odds and outcome data).
            prediction: Direction from hypothesis layer ("OVER" or "UNDER").
            edge: Edge magnitude from hypothesis layer.
            bet_logger: Logger to record the bet.
            team_goal_history: Team goal history for variance calc.
        """
        # Compute variance for staking
        match_variance = features.referee_volatility_index
        stake = self._staking.compute_stake(match_variance)

        # Determine actual outcome
        actual_outcome = "OVER" if features.total_goals > features.over_under_line else "UNDER"

        # Determine odds — R03: missing odds suppress signal (no synthetic odds)
        if prediction == "OVER":
            odds = features.over_odds if features.over_odds and features.over_odds > 1.0 else None
        else:
            odds = features.under_odds if features.under_odds and features.under_odds > 1.0 else None

        if odds is None:
            return  # NO_SIGNAL — missing market data cannot create a bet

        # Log the bet
        bet_logger.log_bet(
            match_id=features.match_id,
            date_unix=features.date_unix,
            prediction=prediction,
            actual_outcome=actual_outcome,
            odds=odds,
            stake=stake,
        )

    def _empty_result(self) -> BacktestResult:
        """Return an empty BacktestResult when no folds can be generated."""
        return BacktestResult(
            net_roi_pct=0.0,
            win_rate_pct=0.0,
            max_drawdown_pct=0.0,
            p_value=1.0,
            total_bets=0,
            total_staked=0.0,
            total_profit=0.0,
            fold_results=[],
            bet_log=[],
            strategy_config=self._config,
        )
