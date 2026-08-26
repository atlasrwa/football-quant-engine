"""Batch 5 — Walk-Forward Validation.

Multi-period out-of-sample evaluation that answers:
"Does this relationship survive repeated testing across time?"

Architecture:
    WalkForwardConfig → FoldGenerator → WalkForwardOrchestrator
    → FoldResult[] → WalkForwardResult → FDR integration

Key guarantees:
- Models refitted per fold (no look-ahead)
- Strict temporal ordering (train < validation < test)
- Expanding and rolling window support
- Deterministic fold boundaries
- Reproducible results
"""

from src.research.walkforward.config import (
    WalkForwardConfig,
    WindowType,
)
from src.research.walkforward.folds import FoldGenerator
from src.research.walkforward.orchestrator import WalkForwardOrchestrator
from src.research.walkforward.result import (
    FoldResult,
    FoldStatus,
    WalkForwardResult,
    WalkForwardStatus,
)

__all__ = [
    "WalkForwardConfig",
    "WindowType",
    "FoldGenerator",
    "WalkForwardOrchestrator",
    "FoldResult",
    "FoldStatus",
    "WalkForwardResult",
    "WalkForwardStatus",
]
