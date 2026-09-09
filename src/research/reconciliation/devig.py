"""De-vigging — convert bookmaker decimal odds to fair probabilities.

Kept SEPARATE from raw odds storage (OddsSnapshot): raw prices are stored
verbatim; de-vigging is a derived transformation computed on demand. This
module never mutates stored odds.

Two standard methods are provided:
- multiplicative (proportional): fair_i = implied_i / overround. Simple and
  the most common; preserves the ratio of implied probabilities.
- shin (optional, iterative): estimates insider-trading proportion z. Provided
  for evaluation completeness; multiplicative is the default.

All functions validate inputs (odds >= 1.0) and return probabilities that sum
to 1.0. They operate on a set of mutually-exclusive-and-exhaustive selections
(e.g. {OVER, UNDER} or {HOME, DRAW, AWAY}).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class DevigResult:
    """Fair probabilities and the removed margin (overround - 1)."""
    fair_probabilities: dict[str, float]
    overround: float
    method: str

    @property
    def margin(self) -> float:
        """Bookmaker margin (overround - 1.0)."""
        return self.overround - 1.0


def _validate(odds: Mapping[str, float]) -> None:
    if len(odds) < 2:
        raise ValueError("De-vig requires at least 2 mutually exclusive selections")
    for name, o in odds.items():
        if o is None or o < 1.0:
            raise ValueError(f"Invalid decimal odds for {name!r}: {o!r} (must be >= 1.0)")


def implied_probabilities(odds: Mapping[str, float]) -> dict[str, float]:
    """Raw implied probabilities (1/odds), NOT margin-adjusted (sum > 1)."""
    _validate(odds)
    return {name: 1.0 / o for name, o in odds.items()}


def overround(odds: Mapping[str, float]) -> float:
    """Sum of raw implied probabilities (>= 1.0 for a vigged book)."""
    return sum(implied_probabilities(odds).values())


def devig_multiplicative(odds: Mapping[str, float]) -> DevigResult:
    """Proportional de-vig: fair_i = implied_i / sum(implied)."""
    implied = implied_probabilities(odds)
    total = sum(implied.values())
    fair = {name: p / total for name, p in implied.items()}
    return DevigResult(fair_probabilities=fair, overround=total, method="multiplicative")


def devig_shin(odds: Mapping[str, float], *, max_iter: int = 100, tol: float = 1e-10) -> DevigResult:
    """Shin (1992) de-vig estimating insider proportion z (iterative).

    Falls back to multiplicative behavior when z solves to ~0. Provided for
    evaluation; not the default.
    """
    implied = implied_probabilities(odds)
    total = sum(implied.values())
    pi = {k: v / total for k, v in implied.items()}  # normalized start

    z = 0.0
    for _ in range(max_iter):
        # Shin's fixed-point for z given normalized implied pi and overround.
        denom = sum(
            ((z * z + 4 * (1 - z) * (p ** 2) / total) ** 0.5) for p in implied.values()
        )
        new_z = max(0.0, (denom - (2 - 2 * z)) / (total - 2)) if total != 2 else 0.0
        if abs(new_z - z) < tol:
            z = new_z
            break
        z = new_z

    def fair(p_raw: float) -> float:
        return (((z * z + 4 * (1 - z) * (p_raw ** 2) / total)) ** 0.5 - z) / (2 * (1 - z)) if z < 1 else p_raw

    fair_unnorm = {k: fair(v) for k, v in implied.items()}
    s = sum(fair_unnorm.values()) or 1.0
    fair_probs = {k: v / s for k, v in fair_unnorm.items()}
    return DevigResult(fair_probabilities=fair_probs, overround=total, method="shin")


def devig(odds: Mapping[str, float], method: str = "multiplicative") -> DevigResult:
    """De-vig using the named method ("multiplicative" or "shin")."""
    if method == "multiplicative":
        return devig_multiplicative(odds)
    if method == "shin":
        return devig_shin(odds)
    raise ValueError(f"Unknown de-vig method {method!r}")
