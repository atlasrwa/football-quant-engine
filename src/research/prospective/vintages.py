"""Forecast vintages for prospective capture.

The champion-side vintage module (``src/research/forward/vintage.py``) defines
EARLY (~24h) and LATE (~60m) and is left untouched. Prospective capture needs
a finer ladder of *target capture windows*:

    EARLY  ~ T-24h
    MID    ~ T-6h
    LATE   ~ T-60m
    FINAL  ~ T-15m

These are TARGETS, not fabricated timestamps. When data is actually retrieved
at, say, T-52m, the stored ``observed_at`` is the real retrieval time — never
snapped to T-60m. The vintage only fixes the *forecast cutoff* used for
point-in-time lookups: an observation is consultable for a vintage iff

    observation.observed_at <= cutoff

and (for lineup-derived concepts) the vintage is late enough to have plausibly
seen a confirmed team sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional

#: Concepts derived from a confirmed team sheet. The live lineups endpoint only
#: exposes a confirmed XI ~1h before kickoff, so these are never consultable at
#: EARLY / MID vintages. (Mirrors forward.vintage.LINEUP_CONCEPTS, extended.)
LINEUP_CONCEPTS: Final = frozenset(
    {
        "confirmed_lineup",
        "confirmed_xi",
        "starting_xi",
        "formation",
        "bench",
        "assigned_referee",
        "referee",
    }
)


class ProspectiveVintage(Enum):
    """Target capture windows before kickoff."""

    EARLY = "EARLY"
    MID = "MID"
    LATE = "LATE"
    FINAL = "FINAL"

    @property
    def offset_seconds(self) -> int:
        """Approximate seconds before kickoff this vintage targets."""
        return {
            ProspectiveVintage.EARLY: 24 * 3600,
            ProspectiveVintage.MID: 6 * 3600,
            ProspectiveVintage.LATE: 60 * 60,
            ProspectiveVintage.FINAL: 15 * 60,
        }[self]

    @property
    def may_consult_lineups(self) -> bool:
        """Whether a confirmed team sheet could plausibly exist by this window.

        The provider announces the confirmed XI ~1h before kickoff, so only
        LATE (~60m) and FINAL (~15m) may consult lineup-derived concepts.
        EARLY/MID must not, even if a later snapshot exists.
        """
        return self in (ProspectiveVintage.LATE, ProspectiveVintage.FINAL)


@dataclass(frozen=True)
class ForecastCutoff:
    """A concrete point-in-time boundary for one fixture + vintage.

    Attributes:
        fixture_id: Canonical fixture id.
        vintage: The target capture window.
        kickoff_ts: Kickoff time (unix seconds).
        cutoff_ts: The PIT boundary; observations with ``observed_at`` after
            this are NOT consultable. Never after kickoff.
    """

    fixture_id: str
    vintage: ProspectiveVintage
    kickoff_ts: float
    cutoff_ts: float

    @property
    def consults_lineups(self) -> bool:
        return self.vintage.may_consult_lineups


def compute_cutoff(
    fixture_id: str,
    kickoff_ts: float,
    vintage: ProspectiveVintage,
) -> ForecastCutoff:
    """Compute the PIT cutoff for a fixture at a vintage.

    ``cutoff = kickoff - vintage.offset_seconds`` but never later than kickoff.
    """
    cutoff = min(kickoff_ts - vintage.offset_seconds, kickoff_ts)
    return ForecastCutoff(
        fixture_id=fixture_id,
        vintage=vintage,
        kickoff_ts=float(kickoff_ts),
        cutoff_ts=float(cutoff),
    )


def is_consultable(
    *,
    concept: str,
    observed_at: Optional[float],
    cutoff: ForecastCutoff,
) -> bool:
    """Whether an observation may be consulted for this forecast.

    Fails closed:
    - lineup-derived concepts are suppressed unless the vintage is late enough;
    - an observation with no ``observed_at`` is never consultable for a finite
      cutoff (we cannot prove it predates the forecast);
    - otherwise consultable iff ``observed_at <= cutoff_ts``.
    """
    if concept in LINEUP_CONCEPTS and not cutoff.consults_lineups:
        return False
    if observed_at is None:
        return False
    return float(observed_at) <= cutoff.cutoff_ts
