"""Proprietary x-Metric Suite (xC, xB, xO).

Vectorized computation, strategy evaluation, walk-forward backtesting,
and statistical validation for novel football betting metrics.
"""

from src.engine.xmetrics import XMetricCoefficients, XMetricEngine
from src.engine.evaluator import (
    Condition,
    Signal,
    Strategy,
    StrategyEvaluator,
)
from src.engine.backtest import XBacktestConfig, XBetRecord, XMetricBacktester
from src.engine.validator import (
    StatisticalValidator,
    ValidationCriteria,
    ValidationVerdict,
)

__all__ = [
    "XMetricCoefficients",
    "XMetricEngine",
    "Condition",
    "Signal",
    "Strategy",
    "StrategyEvaluator",
    "XBacktestConfig",
    "XBetRecord",
    "XMetricBacktester",
    "StatisticalValidator",
    "ValidationCriteria",
    "ValidationVerdict",
]
