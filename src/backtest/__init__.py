"""Backtest execution module: engine, staking, signals, metrics, and cross-validation.

Exports the main engine and supporting components.
"""

from src.backtest.bet_log import BetLogger
from src.backtest.cross_validation import Fold, TemporalCrossValidator
from src.backtest.engine import WalkForwardEngine
from src.backtest.metrics import MetricsAggregator, MetricsSummary
from src.backtest.signal import SignalGenerator
from src.backtest.staking import StakingCalculator

__all__ = [
    "BetLogger",
    "Fold",
    "MetricsAggregator",
    "MetricsSummary",
    "SignalGenerator",
    "StakingCalculator",
    "TemporalCrossValidator",
    "WalkForwardEngine",
]
