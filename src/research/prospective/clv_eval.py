"""CLV-style prospective evaluation.

Once prospective snapshots exist, we can evaluate whether the model's early
disagreement points toward the LATER (sharper) market — evidence of
information even before enough match outcomes accumulate. This is research
evidence, NOT a betting-profitability claim.

For each fixture at the EARLY vintage we compare:

    disagreement_early = logit(p_model_early) - logit(p_market_early)
    market_move        = logit(p_market_late) - logit(p_market_early)

and report:
- directional CLV hit rate: fraction where sign(disagreement) == sign(move),
- mean signed logit movement in the disagreement direction,
- correlation between disagreement and later market move.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

_EPS = 1e-9


def _logit(p: float) -> Optional[float]:
    if not (0.0 < p < 1.0):
        return None
    return math.log(p / (1.0 - p))


@dataclass(frozen=True)
class CLVRow:
    """One fixture's early model/market and later market probabilities."""

    fixture_id: str
    p_model_early: float
    p_market_early: float
    p_market_late: float


@dataclass(frozen=True)
class CLVReport:
    n: int
    directional_hit_rate: Optional[float]
    mean_signed_move: Optional[float]
    correlation: Optional[float]

    def to_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "directional_hit_rate": self.directional_hit_rate,
            "mean_signed_move": self.mean_signed_move,
            "correlation": self.correlation,
        }


def evaluate_clv(rows: Sequence[CLVRow]) -> CLVReport:
    """Compute directional CLV metrics over fixtures with complete data."""
    disagreements: list[float] = []
    moves: list[float] = []
    for r in rows:
        lm_e = _logit(r.p_market_early)
        lm_l = _logit(r.p_market_late)
        lf_e = _logit(r.p_model_early)
        if lm_e is None or lm_l is None or lf_e is None:
            continue
        disagreements.append(lf_e - lm_e)
        moves.append(lm_l - lm_e)

    n = len(disagreements)
    if n == 0:
        return CLVReport(0, None, None, None)

    d = np.asarray(disagreements)
    mv = np.asarray(moves)

    # Directional hit rate over rows with a non-trivial disagreement.
    nonzero = np.abs(d) > _EPS
    if nonzero.any():
        hit = float(np.mean(np.sign(d[nonzero]) == np.sign(mv[nonzero])))
    else:
        hit = None

    # Mean signed move in the disagreement direction: sign(d) * move.
    mean_signed = float(np.mean(np.sign(d) * mv))

    corr: Optional[float] = None
    if n >= 2 and d.std() > _EPS and mv.std() > _EPS:
        corr = float(np.corrcoef(d, mv)[0, 1])

    return CLVReport(n=n, directional_hit_rate=hit, mean_signed_move=mean_signed, correlation=corr)
