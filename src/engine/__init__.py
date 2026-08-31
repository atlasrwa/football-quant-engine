"""Proprietary x-Metric Suite (xC, xB, xO).

Two-layer architecture:
    analysis/  — Data analysis, strategy evaluation, walk-forward backtesting,
                 statistical validation, FDR control, market friction, and
                 no-code strategy building.
    market/    — Market EV: closing line value, beat-the-bookie metrics,
                 prediction settlement, quarantine bridge, and signal dispatch.

Import directly from the layer you need:
    from src.engine.analysis import XMetricEngine, StrategyEvaluator
    from src.engine.market import CLVCalculator, CommunityBroadcaster

The top-level `src.engine` re-exports the analysis layer for convenience.
Market layer imports are available via `src.engine.market` to avoid circular
dependencies with the domain layer.
"""

# Layer 1: Analysis & Backtesting (eagerly re-exported)
from src.engine.analysis.xmetrics import XMetricCoefficients, XMetricEngine
from src.engine.analysis.evaluator import (
    Condition,
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
    # --- Layer 1: Analysis & Backtesting ---
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
    # Strategy Identity
    "StrategyIdentity",
    "StrategyRegistry",
    # Data
    "BaseDataLoader",
    "FootyStatsAdapter",
    "MATCH_RECORD_SCHEMA",
    "SyntheticDataLoader",
]
