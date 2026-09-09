"""Prior-only referee features (cards / fouls families only).

The live ``/matches/{id}/referee`` endpoint returns the assigned referee plus a
``career`` summary. That career summary is a CURRENT-STATE aggregate: using it
as a historical pre-match feature would leak future matches into the past. So
for historical evaluation we derive referee rates STRICTLY from fixtures the
referee officiated before the forecast cutoff.

Referee features are only added to card/foul-type families, never to every
market automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

#: Families for which a referee prior is defensible.
REFEREE_APPLICABLE_FAMILIES: frozenset[str] = frozenset({"CARDS", "FIRST_HALF_CARDS", "FOULS"})


@dataclass(frozen=True)
class RefereeMatchObservation:
    """One prior match a referee officiated."""

    referee_id: str
    kickoff_ts: float
    total_cards: Optional[int] = None
    total_fouls: Optional[int] = None
    penalties: Optional[int] = None


@dataclass(frozen=True)
class RefereeState:
    """Prior-only referee rates as of a forecast cutoff.

    Rates are None when no prior match reported the underlying count (never 0).
    """

    referee_id: str
    matches: int
    cards_per_match: Optional[float]
    fouls_per_match: Optional[float]
    penalties_per_match: Optional[float]

    def to_features(self, family: str) -> dict[str, float]:
        """Feature vector, only for applicable families; missing stays absent."""
        if family not in REFEREE_APPLICABLE_FAMILIES:
            return {}
        feats: dict[str, float] = {}
        if self.cards_per_match is not None:
            feats["ref_cards_per_match"] = self.cards_per_match
        if self.fouls_per_match is not None:
            feats["ref_fouls_per_match"] = self.fouls_per_match
        if self.penalties_per_match is not None:
            feats["ref_penalties_per_match"] = self.penalties_per_match
        return feats


def build_referee_state(
    referee_id: str,
    observations: Iterable[RefereeMatchObservation],
    *,
    cutoff_ts: float,
    window: Optional[int] = None,
) -> RefereeState:
    """Build prior-only referee state (kickoff < cutoff only)."""
    prior = sorted(
        (o for o in observations if o.referee_id == referee_id and o.kickoff_ts < cutoff_ts),
        key=lambda o: o.kickoff_ts,
    )
    if window is not None and window > 0:
        prior = prior[-window:]
    if not prior:
        return RefereeState(referee_id=referee_id, matches=0, cards_per_match=None,
                            fouls_per_match=None, penalties_per_match=None)

    def _mean(attr: str) -> Optional[float]:
        vals = [getattr(o, attr) for o in prior if getattr(o, attr) is not None]
        return (sum(vals) / len(vals)) if vals else None

    return RefereeState(
        referee_id=referee_id,
        matches=len(prior),
        cards_per_match=_mean("total_cards"),
        fouls_per_match=_mean("total_fouls"),
        penalties_per_match=_mean("penalties"),
    )
