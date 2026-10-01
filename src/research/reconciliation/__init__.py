"""Market-probability reconciliation for the QFE V2 reboot.

Provider blending was intentionally removed from main. Football evidence is
accepted only through provider-scoped semantic contracts. This package now
contains only explicit conversion of bookmaker prices into no-vig market
probabilities.
"""

from src.research.reconciliation.devig import (
    DevigResult,
    devig,
    devig_multiplicative,
    devig_shin,
    implied_probabilities,
    overround,
)

__all__ = [
    "DevigResult",
    "devig",
    "devig_multiplicative",
    "devig_shin",
    "implied_probabilities",
    "overround",
]
