"""Market movement between forecast vintages (prospective-only).

Because we prospectively store multiple snapshots per fixture, we can measure
how the market moved between vintages in log-odds space:

    delta_market_logit = logit(p_late) - logit(p_early)

These moves are PROSPECTIVE-ONLY. They are never backfilled for historical
fixtures where timestamped snapshots do not exist (the API's opening/last_seen
carry no timestamp, so no historical movement series can be reconstructed).

Two uses are kept SEPARATE (mixing them conflates a target with a feature):
- as a research TARGET: did our model anticipate the later market?
  (see clv_eval.py)
- as a late-forecast FEATURE: what did the market absorb between vintages?
  (a movement value observed at a cutoff may feed the residual at a later
  vintage, never earlier).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional

from src.research.prospective.vintages import ProspectiveVintage

_EPS = 1e-9


def _logit(p: float) -> Optional[float]:
    if not (0.0 < p < 1.0):
        return None
    return math.log(p / (1.0 - p))


#: Ordered adjacent-vintage move names.
MOVE_NAMES = (
    "opening_to_early_move",
    "early_to_mid_move",
    "mid_to_late_move",
    "late_to_final_move",
)

_ADJACENT = (
    ("opening", "early", "opening_to_early_move"),
    ("early", "mid", "early_to_mid_move"),
    ("mid", "late", "mid_to_late_move"),
    ("late", "final", "late_to_final_move"),
)


@dataclass(frozen=True)
class MarketMovement:
    """Log-odds moves between adjacent vintages for one (fixture, market, line).

    A move is None when either endpoint snapshot is missing or degenerate — it
    is never fabricated or zero-filled.
    """

    fixture_id: str
    market: str
    line: Optional[float]
    selection: str
    moves: Mapping[str, Optional[float]]

    def total_move(self) -> Optional[float]:
        """Sum of available adjacent moves, or None if none are available."""
        vals = [v for v in self.moves.values() if v is not None]
        return sum(vals) if vals else None


def compute_movement(
    *,
    fixture_id: str,
    market: str,
    line: Optional[float],
    selection: str,
    vintage_probs: Mapping[str, Optional[float]],
) -> MarketMovement:
    """Compute adjacent-vintage log-odds moves.

    ``vintage_probs`` maps a stage label ("opening"/"early"/"mid"/"late"/
    "final") to the fair probability observed at that stage (or None). Only
    moves whose BOTH endpoints are present and non-degenerate are populated.
    """
    moves: dict[str, Optional[float]] = {}
    for a, b, name in _ADJACENT:
        pa = vintage_probs.get(a)
        pb = vintage_probs.get(b)
        if pa is None or pb is None:
            moves[name] = None
            continue
        la, lb = _logit(pa), _logit(pb)
        moves[name] = None if la is None or lb is None else lb - la
    return MarketMovement(
        fixture_id=fixture_id, market=market, line=line, selection=selection, moves=moves
    )


def vintage_stage_label(vintage: ProspectiveVintage) -> str:
    """Map a ProspectiveVintage to its movement stage label."""
    return {
        ProspectiveVintage.EARLY: "early",
        ProspectiveVintage.MID: "mid",
        ProspectiveVintage.LATE: "late",
        ProspectiveVintage.FINAL: "final",
    }[vintage]
