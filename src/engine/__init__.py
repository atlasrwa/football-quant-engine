"""Proprietary x-Metric Suite (xC, xB, xO).

Vectorized computation, strategy evaluation, walk-forward backtesting,
statistical validation, FDR control, market friction, and no-code strategy
building for novel football betting metrics.
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
from src.engine.fdr import (
    FDRController,
    FDRResult,
    QuarantineEntry,
    QuarantineStatus,
    QuarantineTracker,
)
from src.engine.friction import (
    FrictionAdjustedBacktester,
    MarketFrictionConfig,
    DEFAULT_LEAGUE_TIERS,
)
from src.engine.builder import StrategyBuilder
from src.engine.data import (
    BaseDataLoader,
    FootyStatsAdapter,
    MATCH_RECORD_SCHEMA,
    SyntheticDataLoader,
)

__all__ = [
    # x-Metrics
    "XMetricCoefficients",
    "XMetricEngine",
    # Evaluator
    "Condition",
    "Signal",
    "Strategy",
    "StrategyEvaluator",
    # Backtest
    "XBacktestConfig",
    "XBetRecord",
    "XMetricBacktester",
    # Validator
    "StatisticalValidator",
    "ValidationCriteria",
    "ValidationVerdict",
    # FDR & Quarantine
    "FDRController",
    "FDRResult",
    "QuarantineEntry",
    "QuarantineStatus",
    "QuarantineTracker",
    # Friction
    "FrictionAdjustedBacktester",
    "MarketFrictionConfig",
    "DEFAULT_LEAGUE_TIERS",
    # Builder
    "StrategyBuilder",
    # Data
    "BaseDataLoader",
    "FootyStatsAdapter",
    "MATCH_RECORD_SCHEMA",
    "SyntheticDataLoader",
]
