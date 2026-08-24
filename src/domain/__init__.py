"""Phase 2 Domain Model — Reproducibility and Prediction Foundation.

This module contains the canonical domain objects for the prediction platform:

Provenance Chain:
    Strategy (existing) → StrategyVersion (existing)
        ↓
    DatasetVersion → FeatureVersion → ModelVersion
        ↓
    BacktestRun → ValidationRun
        ↓
    MarketDefinition → MarketPrice
        ↓
    PredictionEvent → Settlement

All types are:
- Frozen (immutable after construction)
- Deterministically hashable where applicable
- Serializable to dict/JSON
- Independent of persistence layer (no database coupling)
"""

from src.domain.provenance import DatasetVersion, FeatureVersion, ModelVersion
from src.domain.backtest_run import BacktestRun, ValidationRun
from src.domain.market import MarketDefinition, MarketPrice
from src.domain.prediction import PredictionEvent, PredictionStatus
from src.domain.settlement import Settlement, SettlementOutcome

__all__ = [
    "DatasetVersion",
    "FeatureVersion",
    "ModelVersion",
    "BacktestRun",
    "ValidationRun",
    "MarketDefinition",
    "MarketPrice",
    "PredictionEvent",
    "PredictionStatus",
    "Settlement",
    "SettlementOutcome",
]
