"""Layer 1: Data Analysis & Backtesting.

Proprietary x-Metric computation (xC, xB, xO), strategy evaluation,
walk-forward backtesting, statistical validation, FDR control, market
friction modelling, and no-code strategy building.
"""

from src.engine.analysis.xmetrics import XMetricCoefficients, XMetricEngine
from src.engine.analysis.evaluator import (
    Condition,
    HypothesisSignal,
    Signal,
    Strategy,
    StrategyEvaluator,
)
from src.engine.analysis.backtest import XBacktestConfig, XBetRecord, XMetricBacktester
from src.engine.analysis.validator import (
    StatisticalValidator,
    ValidationCriteria,
    ValidationVerdict,
)
from src.engine.analysis.fdr import (
    FDRController,
    FDRResult,
    QuarantineEntry,
    QuarantineStatus,
    QuarantineTracker,
)
from src.engine.analysis.friction import (
    FrictionAdjustedBacktester,
    MarketFrictionConfig,
    DEFAULT_LEAGUE_TIERS,
)
from src.engine.analysis.builder import StrategyBuilder
from src.engine.analysis.strategy_identity import StrategyIdentity, StrategyRegistry
from src.engine.analysis.data import (
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
    "HypothesisSignal",
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
    # Strategy Identity
    "StrategyIdentity",
    "StrategyRegistry",
    # Data
    "BaseDataLoader",
    "FootyStatsAdapter",
    "MATCH_RECORD_SCHEMA",
    "SyntheticDataLoader",
]
