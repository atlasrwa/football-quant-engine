"""Lineup normalization and confirmed-XI state (point-in-time safe).

The live ``/lineups`` endpoint returns, for upcoming matches, the confirmed
starting XI only once the official team sheet is announced (~1h before
kickoff); speculative pre-announcement predictions are NOT exposed. For played
matches it returns the actual XI. The response carries NO capture timestamp,
so the only trustworthy ``observed_at`` for a lineup is OUR OWN retrieval time
recorded at prospective capture.

Consequences enforced here:

- A normalized lineup carries the ``observed_at`` we captured it at. Without
  our own timestamp, it cannot be used at any historical forecast cutoff.
- Stable player IDs are mandatory. Players are NEVER joined by display name.
- ``availability_reason`` defaults to UNKNOWN. Absence from the XI is never
  interpreted as injury/suspension. An explicit reason may only come from the
  dedicated injuries-suspensions endpoint.
- Confirmed-XI derived features (continuity, formation delta) are DELTAS versus
  the team's prior-only expected state, never the raw squad quality (the
  champion's team random effects already absorb the level).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class AvailabilityReason(str, Enum):
    """Why a usual starter is absent. Only set from EXPLICIT provider records."""

    UNKNOWN = "UNKNOWN"  # default: absence is never assumed to be injury
    INJURY = "INJURY"
    SUSPENSION = "SUSPENSION"


class LineupError(ValueError):
    """Raised when a lineup cannot be normalized safely (fails neutrally)."""


@dataclass(frozen=True)
class LineupPlayer:
    """One player in a normalized lineup. Stable id mandatory."""

    player_id: str
    position: Optional[str]
    jersey_number: Optional[int]
    is_starter: bool

    def __post_init__(self) -> None:
        if not self.player_id or not isinstance(self.player_id, str):
            raise LineupError("player_id (stable) is required; name joins are forbidden")


@dataclass(frozen=True)
class TeamLineup:
    """Normalized team sheet for one side."""

    team_id: str
    formation: Optional[str]
    starting_xi: tuple[LineupPlayer, ...]
    bench: tuple[LineupPlayer, ...]

    @property
    def starter_ids(self) -> frozenset[str]:
        return frozenset(p.player_id for p in self.starting_xi)

    @property
    def bench_ids(self) -> frozenset[str]:
        return frozenset(p.player_id for p in self.bench)


@dataclass(frozen=True)
class NormalizedLineup:
    """Both sides of a fixture lineup with OUR capture timestamp.

    Attributes:
        fixture_id: Canonical fixture id.
        confirmed: Whether the provider marked the sheet confirmed.
        home: Home team sheet.
        away: Away team sheet.
        observed_at: OUR retrieval time (unix). None ONLY for a historical
            payload with no accompanying prospective capture — such a lineup is
            not PIT-usable and downstream gates will reject it.
    """

    fixture_id: str
    confirmed: bool
    home: TeamLineup
    away: TeamLineup
    observed_at: Optional[float]

    @property
    def pit_usable(self) -> bool:
        """Whether this lineup has a trustworthy own-capture timestamp."""
        return self.observed_at is not None


def _players(raw: Any, *, starter: bool) -> tuple[LineupPlayer, ...]:
    if not isinstance(raw, list):
        return ()
    out = []
    for p in raw:
        if not isinstance(p, Mapping):
            continue
        pid = p.get("id")
        if not pid:
            # A player without a stable id cannot be included safely.
            raise LineupError("lineup entry missing stable player id")
        jersey = p.get("jersey_number")
        out.append(
            LineupPlayer(
                player_id=str(pid),
                position=p.get("position"),
                jersey_number=int(jersey) if isinstance(jersey, int) else None,
                is_starter=starter,
            )
        )
    return tuple(out)


def _team(raw: Any) -> TeamLineup:
    if not isinstance(raw, Mapping):
        raise LineupError("team lineup block missing")
    tid = raw.get("id")
    if not tid:
        raise LineupError("team lineup missing stable team id")
    return TeamLineup(
        team_id=str(tid),
        formation=raw.get("formation"),
        starting_xi=_players(raw.get("starting_xi"), starter=True),
        bench=_players(raw.get("substitutes"), starter=False),
    )


def normalize_lineup(
    payload: Optional[Mapping[str, Any]],
    *,
    fixture_id: str,
    observed_at: Optional[float],
) -> Optional[NormalizedLineup]:
    """Normalize a verified ``/lineups`` payload.

    Returns None when the lineup has not been announced (provider 404 → None
    upstream, or empty payload) — a missing lineup fails NEUTRALLY (it is not
    an empty XI). ``observed_at`` MUST be our own capture time; pass None only
    for a historical payload with no prospective capture, which will be marked
    not PIT-usable.
    """
    if payload is None:
        return None
    data = payload.get("data", payload)
    if not isinstance(data, Mapping) or "home" not in data or "away" not in data:
        return None
    return NormalizedLineup(
        fixture_id=fixture_id,
        confirmed=bool(data.get("confirmed", False)),
        home=_team(data.get("home")),
        away=_team(data.get("away")),
        observed_at=observed_at,
    )


# ---------------------------------------------------------------------------
# DELTA features vs the team's prior-only expected XI state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedXIState:
    """Prior-only expectation of a team's starting XI.

    Derived STRICTLY from historical lineups captured before the forecast
    cutoff (see player_state.build_usual_starting_probabilities). Maps
    player_id -> usual starting probability in [0,1]; the modal recent
    formation is likewise prior-only.
    """

    usual_starting_probability: Mapping[str, float]
    modal_recent_formation: Optional[str]


@dataclass(frozen=True)
class LineupDelta:
    """How different today's confirmed XI is from the prior-only expectation.

    All fields are DELTAS / structural comparisons, not absolute squad quality.
    ``missing_usual_starters`` counts players whose usual-start probability was
    high but who are NOT in today's XI. ``availability_reasons`` maps those
    player ids to a reason (default UNKNOWN).
    """

    fixture_id: str
    team_id: str
    xi_continuity_score: float
    unexpected_absence_score: float
    unexpected_inclusion_score: float
    missing_usual_starters: int
    formation_changed: Optional[bool]
    same_as_modal_recent_formation: Optional[bool]
    availability_reasons: Mapping[str, AvailabilityReason]

    def to_features(self) -> dict[str, float]:
        """Numeric feature vector for the residual model (missing stays absent)."""
        feats: dict[str, float] = {
            "xi_continuity_score": self.xi_continuity_score,
            "unexpected_absence_score": self.unexpected_absence_score,
            "unexpected_inclusion_score": self.unexpected_inclusion_score,
            "missing_usual_starters": float(self.missing_usual_starters),
        }
        if self.formation_changed is not None:
            feats["formation_changed"] = 1.0 if self.formation_changed else 0.0
        if self.same_as_modal_recent_formation is not None:
            feats["same_as_modal_recent_formation"] = (
                1.0 if self.same_as_modal_recent_formation else 0.0
            )
        return feats


def compute_lineup_delta(
    team_lineup: TeamLineup,
    expected: ExpectedXIState,
    *,
    fixture_id: str,
    usual_threshold: float = 0.5,
    availability: Optional[Mapping[str, AvailabilityReason]] = None,
) -> LineupDelta:
    """Compute confirmed-XI deltas vs the prior-only expected state.

    - xi_continuity_score: expected mass of today's starters (sum of usual
      probabilities of players who ARE starting) / total expected mass.
    - unexpected_absence_score: expected mass of usual starters who are NOT in
      today's XI.
    - unexpected_inclusion_score: count of today's starters whose usual-start
      probability was low (< usual_threshold), normalized by XI size.
    - missing_usual_starters: usual starters (prob >= threshold) absent today.

    ``availability`` (from the EXPLICIT injuries endpoint) annotates the missing
    players; anything not listed there stays UNKNOWN — never fabricated.
    """
    usual = dict(expected.usual_starting_probability)
    starters = team_lineup.starter_ids
    total_expected = sum(usual.values()) or 1.0

    present_mass = sum(prob for pid, prob in usual.items() if pid in starters)
    absent_mass = sum(prob for pid, prob in usual.items() if pid not in starters)

    xi_continuity = present_mass / total_expected
    unexpected_absence = absent_mass / total_expected

    xi_size = max(len(starters), 1)
    unexpected_inclusions = sum(
        1 for pid in starters if usual.get(pid, 0.0) < usual_threshold
    )
    unexpected_inclusion_score = unexpected_inclusions / xi_size

    usual_starters = {pid for pid, prob in usual.items() if prob >= usual_threshold}
    missing = usual_starters - starters
    reasons = {
        pid: (availability or {}).get(pid, AvailabilityReason.UNKNOWN) for pid in missing
    }

    formation_changed: Optional[bool] = None
    same_modal: Optional[bool] = None
    if expected.modal_recent_formation is not None and team_lineup.formation is not None:
        same_modal = team_lineup.formation == expected.modal_recent_formation
        formation_changed = not same_modal

    return LineupDelta(
        fixture_id=fixture_id,
        team_id=team_lineup.team_id,
        xi_continuity_score=xi_continuity,
        unexpected_absence_score=unexpected_absence,
        unexpected_inclusion_score=unexpected_inclusion_score,
        missing_usual_starters=len(missing),
        formation_changed=formation_changed,
        same_as_modal_recent_formation=same_modal,
        availability_reasons=reasons,
    )
