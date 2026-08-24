"""Feature engineering module: calculators and assembly pipeline.

Exports the main calculators and the FeatureAssembler.
"""

from src.features.assembler import FeatureAssembler
from src.features.referee_volatility import RefereeVolatilityCalculator
from src.features.rolling_form import RollingFormCalculator
from src.features.xg_efficiency import XGEfficiencyCalculator

__all__ = [
    "FeatureAssembler",
    "RefereeVolatilityCalculator",
    "RollingFormCalculator",
    "XGEfficiencyCalculator",
]
