"""Point-in-time player state from prior match observations.

Player-state features for a fixture T may only use matches whose kickoff is
STRICTLY before the forecast cutoff of T. We build rolling per-90 rates from
per-match player-stats observations (``/matches/{id}/player-stats``), never
from final season aggregates (``/players/{id}/stats``), because a season
aggregate reflects the whole season including matches after T.

Missing stays missing. A per-90 rate with zero minutes of denominator is not
0.0 — it is absent. Transfers do not corrupt identity: players are keyed by
stable ``player_id`` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional

from src.research.observation.model import MISSING


@dataclass(frozen=True)
class PlayerMatchObservation:
    """One player's contribution in one prior match.

    Attributes:
        player_id: Stable player id.
        team_id: Team the player represented in that match (transfers change
            this across matches but never the identity).
        kickoff_ts: Kickoff of that match (unix). Used for the strict PIT gate.
        minutes: Minutes played (int). 0 is a genuine zero (named but unused).
        started: Whether the player started.
        goals / assists / shots / shots_on_target / cards: raw counts; None
            when the source did not report them (never coerced to 0).
    """

    player_id: str
    team_id: str
    kickoff_ts: float
    minutes: int
    started: bool
    goals: Optional[int] = None
    assists: Optional[int] = None
    shots: Optional[int] = None
    shots_on_target: Optional[int] = None
    cards: Optional[int] = None


@dataclass(frozen=True)
class PlayerState:
    """Prior-only rolling state for one player as of a forecast cutoff.

    Per-90 rates are None when the minutes denominator is zero (division is
    undefined, NOT zero). ``recent_minutes`` / ``starts`` count appearances in
    the window. ``days_since_last_appearance`` is None with no prior match.
    """

    player_id: str
    appearances: int
    starts: int
    total_minutes: int
    minutes_per_appearance: Optional[float]
    goals_per_90: Optional[float]
    assists_per_90: Optional[float]
    shots_per_90: Optional[float]
    shots_on_target_per_90: Optional[float]
    cards_per_90: Optional[float]
    recent_minutes: int
    starting_frequency: Optional[float]
    days_since_last_appearance: Optional[float]


def _per_90(total: Optional[int], minutes: int) -> Optional[float]:
    """Per-90 rate. Absent (None) when the numerator is missing OR minutes==0."""
    if total is None or minutes <= 0:
        return None
    return (total / minutes) * 90.0


def build_player_state(
    player_id: str,
    observations: Iterable[PlayerMatchObservation],
    *,
    cutoff_ts: float,
    window: Optional[int] = None,
    recent_window: int = 5,
) -> PlayerState:
    """Build prior-only player state.

    Only observations with ``kickoff_ts < cutoff_ts`` are used (strict: the
    current fixture and any future match are excluded). ``window`` optionally
    limits to the most recent N prior matches; ``recent_window`` defines the
    'recent minutes load' horizon.
    """
    prior = sorted(
        (o for o in observations if o.player_id == player_id and o.kickoff_ts < cutoff_ts),
        key=lambda o: o.kickoff_ts,
    )
    if window is not None and window > 0:
        prior = prior[-window:]

    if not prior:
        return PlayerState(
            player_id=player_id, appearances=0, starts=0, total_minutes=0,
            minutes_per_appearance=None, goals_per_90=None, assists_per_90=None,
            shots_per_90=None, shots_on_target_per_90=None, cards_per_90=None,
            recent_minutes=0, starting_frequency=None, days_since_last_appearance=None,
        )

    appearances = len(prior)
    starts = sum(1 for o in prior if o.started)
    total_minutes = sum(o.minutes for o in prior)

    def _sum(attr: str) -> Optional[int]:
        vals = [getattr(o, attr) for o in prior]
        if all(v is None for v in vals):
            return None
        return sum(v for v in vals if v is not None)

    recent_minutes = sum(o.minutes for o in prior[-recent_window:])
    last = prior[-1]
    days_since = (cutoff_ts - last.kickoff_ts) / 86400.0

    return PlayerState(
        player_id=player_id,
        appearances=appearances,
        starts=starts,
        total_minutes=total_minutes,
        minutes_per_appearance=(total_minutes / appearances) if appearances else None,
        goals_per_90=_per_90(_sum("goals"), total_minutes),
        assists_per_90=_per_90(_sum("assists"), total_minutes),
        shots_per_90=_per_90(_sum("shots"), total_minutes),
        shots_on_target_per_90=_per_90(_sum("shots_on_target"), total_minutes),
        cards_per_90=_per_90(_sum("cards"), total_minutes),
        recent_minutes=recent_minutes,
        starting_frequency=(starts / appearances) if appearances else None,
        days_since_last_appearance=days_since,
    )


def build_usual_starting_probabilities(
    observations: Iterable[PlayerMatchObservation],
    *,
    team_id: str,
    cutoff_ts: float,
    window_matches: int = 10,
) -> dict[str, float]:
    """Prior-only usual-starting probability per player for a team.

    Uses the team's most recent ``window_matches`` distinct prior match dates
    (kickoff < cutoff). For each player: (# of those matches they started) /
    (# matches considered). Strictly prior; never consults future lineups.
    """
    prior = [o for o in observations if o.team_id == team_id and o.kickoff_ts < cutoff_ts]
    if not prior:
        return {}
    match_ts = sorted({o.kickoff_ts for o in prior})[-window_matches:]
    considered = set(match_ts)
    n_matches = len(considered)
    if n_matches == 0:
        return {}
    starts: dict[str, int] = {}
    for o in prior:
        if o.kickoff_ts in considered and o.started:
            starts[o.player_id] = starts.get(o.player_id, 0) + 1
    return {pid: cnt / n_matches for pid, cnt in starts.items()}
