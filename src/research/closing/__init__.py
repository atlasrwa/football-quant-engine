"""Batch 12 — Closing Odds Provider & Genuine CLV.

Provides:
- ClosingOddsProvider abstraction (independent of pre-match odds)
- Odds normalization and fixture mapping
- Genuine CLV validation (only from verified closing observations)
- Multi-source support (Pinnacle, Betfair, configurable fallback)

Closing odds are EVALUATION-ONLY information.
They must NEVER be used for prediction, staking, or eligibility.
"""

from src.research.closing.provider import (
    ClosingOddsProvider,
    ClosingOddsObservation,
    ClosingOddsStatus,
    DeterministicClosingOddsProvider,
)
from src.research.closing.validation import (
    ClosingLineValidator,
    ClosingValidationResult,
)
from src.research.closing.clv_engine import (
    CLVEngine,
    CLVCalculation,
    CLVMethodology,
)
from src.research.closing.normalization import (
    OddsNormalizer,
    NormalizedFixtureMapping,
    MappingConfidence,
)

__all__ = [
    "ClosingOddsProvider",
    "ClosingOddsObservation",
    "ClosingOddsStatus",
    "DeterministicClosingOddsProvider",
    "ClosingLineValidator",
    "ClosingValidationResult",
    "CLVEngine",
    "CLVCalculation",
    "CLVMethodology",
    "OddsNormalizer",
    "NormalizedFixtureMapping",
    "MappingConfidence",
]
