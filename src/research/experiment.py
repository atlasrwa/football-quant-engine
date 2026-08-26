"""Research experiment execution and walk-forward evaluation.

A ResearchExperiment tracks the complete lifecycle of testing a hypothesis:
dataset → features → model → backtest → validation → result.

Integrates with existing walk-forward infrastructure via adapters.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np

from src.research.candidate_generator import ResearchHypothesis
from src.research.ev_calculator import EVCalculator, EVResult
from src.research.market import MarketDirection, ResearchMarket
from src.research.probability import ProbabilityEstimate, ProbabilityModel


class ExperimentStatus(Enum):
    """Experiment lifecycle status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class BetResult:
    """Result of a single simulated bet."""
    match_index: int
    direction: str
    odds: float
    model_probability: float
    expected_value: float
    actual_outcome: Optional[str]  # "OVER", "UNDER", or None (push)
    profit_loss: float
    is_win: bool


@dataclass
class ExperimentResult:
    """Complete result of a research experiment."""
    hypothesis_id: str
    market: str
    status: ExperimentStatus
    n_samples: int
    n_bets: int
    n_wins: int
    win_rate: float
    total_profit_loss: float
    roi_pct: float
    avg_ev: float
    avg_odds: float
    max_drawdown: float
    sharpe_ratio: float
    p_value: Optional[float] = None
    is_significant: bool = False
    bets: list[BetResult] = field(default_factory=list)
    error: Optional[str] = None
    model_name: str = ""
    dataset_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def content_hash(self) -> str:
        canonical = json.dumps({
            "hypothesis_id": self.hypothesis_id,
            "market": self.market,
            "n_bets": self.n_bets,
            "roi_pct": round(self.roi_pct, 4),
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class ResearchExperiment:
    """Executes a research hypothesis through walk-forward evaluation.

    Walk-forward protocol:
    1. Split data into folds (train/test windows)
    2. For each fold:
       a. Train probability model on training window
       b. Generate predictions on test window
       c. Calculate EV against market odds
       d. Record bet outcomes
    3. Aggregate results across all folds
    4. Run statistical significance test
    """

    def __init__(
        self,
        train_window: int = 200,
        test_window: int = 50,
        step_size: int = 50,
        min_ev_threshold: float = 0.0,
        min_odds: float = 1.30,
        max_odds: float = 5.00,
    ) -> None:
        self._train_window = train_window
        self._test_window = test_window
        self._step_size = step_size
        self._min_ev = min_ev_threshold
        self._min_odds = min_odds
        self._max_odds = max_odds

    def run(
        self,
        hypothesis: ResearchHypothesis,
        matches: list[dict[str, Any]],
        feature_values: list[dict[str, float]],
        market: ResearchMarket,
        model: ProbabilityModel,
    ) -> ExperimentResult:
        """Execute a complete walk-forward experiment.

        Args:
            hypothesis: The hypothesis to test.
            matches: Match dicts sorted chronologically.
            feature_values: Computed feature values (same index as matches).
            market: The target market.
            model: Probability model to use.

        Returns:
            ExperimentResult with full statistics.
        """
        n = len(matches)
        if n < self._train_window + self._test_window:
            return ExperimentResult(
                hypothesis_id=hypothesis.hypothesis_id,
                market=market.market_type.value,
                status=ExperimentStatus.FAILED,
                n_samples=n,
                n_bets=0, n_wins=0, win_rate=0.0,
                total_profit_loss=0.0, roi_pct=0.0,
                avg_ev=0.0, avg_odds=0.0,
                max_drawdown=0.0, sharpe_ratio=0.0,
                error="Insufficient data for walk-forward",
            )

        all_bets: list[BetResult] = []

        # Walk-forward folds
        start = 0
        while start + self._train_window + self._test_window <= n:
            train_end = start + self._train_window
            test_end = train_end + self._test_window

            train_features = feature_values[start:train_end]
            train_matches = matches[start:train_end]
            test_features = feature_values[train_end:test_end]
            test_matches = matches[train_end:test_end]

            # Build training outcomes
            train_outcomes = self._build_outcomes(train_matches, market)

            # Filter training data to only matches where hypothesis conditions met
            # (for model training we use all data — conditions applied at prediction time)
            model.fit(train_features, train_outcomes)

            # Generate predictions on test window
            fold_bets = self._evaluate_test_window(
                hypothesis, test_matches, test_features, market, model
            )
            all_bets.extend(fold_bets)

            start += self._step_size

        # Aggregate results
        return self._aggregate(hypothesis, market, all_bets, n, model.name)

    def _build_outcomes(
        self, matches: list[dict], market: ResearchMarket
    ) -> list[bool]:
        """Build outcome labels for training (True = OVER won)."""
        outcomes = []
        for m in matches:
            target_val = m.get(market.target_field)
            if target_val is not None:
                result = market.resolve_outcome(float(target_val))
                outcomes.append(result == MarketDirection.OVER)
            else:
                outcomes.append(False)
        return outcomes

    def _evaluate_test_window(
        self,
        hypothesis: ResearchHypothesis,
        matches: list[dict],
        features: list[dict[str, float]],
        market: ResearchMarket,
        model: ProbabilityModel,
    ) -> list[BetResult]:
        """Evaluate hypothesis on test window, generate bets."""
        bets: list[BetResult] = []

        for i, (m, feat) in enumerate(zip(matches, features)):
            # Check hypothesis conditions
            if not self._conditions_met(hypothesis, feat):
                continue

            # Get odds
            over_odds_field = market.odds_over_field
            under_odds_field = market.odds_under_field
            over_odds = m.get(over_odds_field)
            under_odds = m.get(under_odds_field)

            if over_odds is None or under_odds is None:
                continue
            if over_odds <= self._min_odds or over_odds >= self._max_odds:
                if under_odds <= self._min_odds or under_odds >= self._max_odds:
                    continue

            # Get probability estimate
            estimate = model.predict(feat)

            # Calculate EV
            direction = MarketDirection.OVER if hypothesis.direction == "OVER" else MarketDirection.UNDER
            ev_result = EVCalculator.compute(
                estimate, market, over_odds, under_odds, direction
            )
            if ev_result is None:
                continue

            # Only bet if EV meets threshold
            if ev_result.expected_value < self._min_ev:
                continue

            # Determine actual outcome
            target_val = m.get(market.target_field)
            if target_val is None:
                continue
            actual = market.resolve_outcome(float(target_val))

            # Settlement
            chosen_odds = ev_result.market_odds
            if actual is None:  # Push
                profit = 0.0
                is_win = False
            elif actual == direction:
                profit = chosen_odds - 1.0  # Unit stake
                is_win = True
            else:
                profit = -1.0
                is_win = False

            bets.append(BetResult(
                match_index=i,
                direction=hypothesis.direction,
                odds=chosen_odds,
                model_probability=ev_result.model_probability,
                expected_value=ev_result.expected_value,
                actual_outcome=actual.value if actual else None,
                profit_loss=profit,
                is_win=is_win,
            ))

        return bets

    def _conditions_met(
        self, hypothesis: ResearchHypothesis, features: dict[str, float]
    ) -> bool:
        """Check if hypothesis conditions are met for given features."""
        for fid, op, threshold in hypothesis.conditions:
            val = features.get(fid)
            if val is None:
                return False
            if op == ">" and not (val > threshold):
                return False
            elif op == "<" and not (val < threshold):
                return False
            elif op == ">=" and not (val >= threshold):
                return False
            elif op == "<=" and not (val <= threshold):
                return False
        return True

    def _aggregate(
        self,
        hypothesis: ResearchHypothesis,
        market: ResearchMarket,
        bets: list[BetResult],
        n_samples: int,
        model_name: str = "",
    ) -> ExperimentResult:
        """Aggregate bet results into experiment statistics."""
        n_bets = len(bets)
        if n_bets == 0:
            return ExperimentResult(
                hypothesis_id=hypothesis.hypothesis_id,
                market=market.market_type.value,
                status=ExperimentStatus.COMPLETED,
                n_samples=n_samples,
                n_bets=0, n_wins=0, win_rate=0.0,
                total_profit_loss=0.0, roi_pct=0.0,
                avg_ev=0.0, avg_odds=0.0,
                max_drawdown=0.0, sharpe_ratio=0.0,
            )

        profits = [b.profit_loss for b in bets]
        n_wins = sum(1 for b in bets if b.is_win)
        total_pnl = sum(profits)
        roi_pct = (total_pnl / n_bets) * 100.0
        avg_ev = float(np.mean([b.expected_value for b in bets]))
        avg_odds = float(np.mean([b.odds for b in bets]))

        # Max drawdown
        cumulative = np.cumsum(profits)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Sharpe ratio (annualized assuming ~1 bet/day)
        if len(profits) > 1:
            mean_p = np.mean(profits)
            std_p = np.std(profits, ddof=1)
            sharpe = float(mean_p / std_p * np.sqrt(252)) if std_p > 0 else 0.0
        else:
            sharpe = 0.0

        # Statistical significance (1-tailed t-test: H0 mean_profit <= 0)
        from scipy import stats as sp_stats
        p_value = None
        is_significant = False
        if n_bets >= 30:
            t_stat, two_tail_p = sp_stats.ttest_1samp(profits, 0.0)
            p_value = float(two_tail_p / 2.0) if t_stat > 0 else 1.0
            is_significant = p_value < 0.05

        return ExperimentResult(
            hypothesis_id=hypothesis.hypothesis_id,
            market=market.market_type.value,
            status=ExperimentStatus.COMPLETED,
            n_samples=n_samples,
            n_bets=n_bets,
            n_wins=n_wins,
            win_rate=n_wins / n_bets,
            total_profit_loss=total_pnl,
            roi_pct=roi_pct,
            avg_ev=avg_ev,
            avg_odds=avg_odds,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            p_value=p_value,
            is_significant=is_significant,
            bets=bets,
            model_name=model_name,
        )
