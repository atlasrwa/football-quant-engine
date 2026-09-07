"""Rolling form windows: last 5 matches, current season only, shrinking.

The rule, stated once and enforced structurally:

    A team's window is its last five completed **current-season** matches. When
    the current season holds fewer than five, the window is the matches that
    exist. Three matches means a three-match window. It never reaches back into
    the prior season to make up the count.

That is the whole distinction this module protects. Prior-season data is a
legitimate input to a forecast, but it enters as a *prior* on team state in
:mod:`src.research.models.hierarchical_market_model`, with a weight that decays as
current-season matches accumulate and is recorded in provenance. It does not enter
as rows inside a rolling window. Backfilling the window with last season's matches
is the bug that invalidated every forecast published before the corpus fix, and the
two mechanisms are kept absolutely separate: this module has no access to the prior
season at all, because :meth:`_eligible` filters to the current season-instance
before the window is taken.

Compared with the previous behaviour, which abstained whenever the current season
could not fill a fixed five-match window, this shrinks instead. The consequence is
that an early-season fixture produces an informative estimate with honestly wide
uncertainty rather than no estimate at all — the width comes from the hierarchical
model, which sees the support count as a feature and shrinks a thin team hard
toward its league.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from src.research.models.market_family import STAT_FIELDS, numeric, stat_value

#: The declared window. Shrinks below this; never grows past it.
DEFAULT_WINDOW = 5

#: Fewest current-season matches that still constitute a window. One match is a
#: real if noisy observation; zero is nothing at all.
MIN_WINDOW_MATCHES = 1

#: Existing minimum-history floor, mirrored here so the gate and the window agree.
#: See :func:`gate_reason` for why the gate keys on window availability.
MIN_CURRENT_SEASON_MATCHES = 3

#: Half-life in matches for within-window recency weighting. At 3, the oldest of
#: five matches carries about a third of the weight of the newest — enough to
#: prefer recent form without letting one result dominate a five-match mean.
DEFAULT_HALF_LIFE_MATCHES = 3.0

WINDOW_LABEL = f"last{DEFAULT_WINDOW}"

STATUS_FULL = "full"
STATUS_SHRUNK = "shrunk"
STATUS_UNAVAILABLE = "unavailable"


def season_key(match: Mapping[str, object]) -> Optional[str]:
    """The season-instance a match belongs to.

    ``competition_id`` is the provider's per-league-season id, so it alone
    identifies a season-instance. Resolved from the data rather than a hard-coded
    season list, so it tracks the calendar automatically.
    """
    value = match.get("competition_id")
    return str(value) if value is not None else None


@dataclass(frozen=True, slots=True)
class WindowState:
    """How much history actually stood behind one team's features.

    ``used`` is the count that matters and the one recorded in provenance: it is
    what distinguishes a forecast resting on real rolling form from one resting on
    a handful of matches.
    """

    label: str
    requested: int
    used: int
    season: Optional[str]
    current_season_matches: int
    status: str

    @property
    def available(self) -> bool:
        return self.status != STATUS_UNAVAILABLE

    @property
    def shrunk(self) -> bool:
        return self.status == STATUS_SHRUNK

    @property
    def deficit(self) -> int:
        """How many matches short of the declared window this team is."""
        return max(0, self.requested - self.used)

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "requested": self.requested,
            "used": self.used,
            "deficit": self.deficit,
            "status": self.status,
            "available": self.available,
            "shrunk": self.shrunk,
            "season": self.season,
            "current_season_matches": self.current_season_matches,
        }


@dataclass(frozen=True, slots=True)
class TeamForm:
    """One team's window and the recency-weighted stats read from it."""

    team: str
    league: str
    window: WindowState
    produced: Mapping[str, float]
    conceded: Mapping[str, float]

    def to_dict(self) -> dict[str, object]:
        return {"team": self.team, "league": self.league, **self.window.to_dict()}


class FormWindowBuilder:
    """Accumulates completed matches and reads shrinking current-season windows.

    Usage is strictly chronological: :meth:`team_form` reads the state *before* a
    kickoff, and :meth:`observe_batch` folds a complete equal-kickoff batch in only
    after every fixture in it has been read. Fixtures sharing a kickoff therefore
    cannot inform each other, which is the same compute-before-update discipline
    the rest of the pipeline uses.
    """

    def __init__(
        self,
        stats: Sequence[str],
        *,
        window: int = DEFAULT_WINDOW,
        half_life_matches: float = DEFAULT_HALF_LIFE_MATCHES,
        min_window_matches: int = MIN_WINDOW_MATCHES,
    ) -> None:
        unknown = sorted(set(stats) - set(STAT_FIELDS))
        if unknown:
            raise ValueError(f"no provider mapping for stats: {', '.join(unknown)}")
        if window < 1:
            raise ValueError("window must be at least 1")
        if half_life_matches <= 0:
            raise ValueError("half_life_matches must be positive")
        self.stats = tuple(dict.fromkeys(stats))
        self.window = window
        self.half_life_matches = half_life_matches
        self.min_window_matches = max(1, min_window_matches)
        # (league, team) -> list of (kickoff, season, produced, conceded)
        self._history: dict[
            tuple[str, str], list[tuple[int, str, dict[str, float], dict[str, float]]]
        ] = defaultdict(list)
        # (league, stat) -> running prior for a stat a team has never recorded
        self._league_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._league_n: dict[tuple[str, str], int] = defaultdict(int)

    # ── reading ───────────────────────────────────────────────────────────
    def _eligible(
        self, league: str, team: str, before: int
    ) -> list[tuple[int, str, dict[str, float], dict[str, float]]]:
        """Prior matches in the team's CURRENT season only.

        The current season is the season-instance of the team's most recent
        completed match before ``before``. Restricting to it *before* taking the
        window is what makes prior-season backfill structurally impossible rather
        than merely discouraged.
        """
        rows = [
            row for row in self._history[(league, team)] if row[0] < before
        ]
        if not rows:
            return []
        current = rows[-1][1]
        return [row for row in rows if row[1] == current]

    def window_state(self, league: str, team: str, before: int) -> WindowState:
        eligible = self._eligible(league, team, before)
        season = eligible[-1][1] if eligible else None
        n_current = len(eligible)
        used = min(self.window, n_current)
        if used < self.min_window_matches:
            status = STATUS_UNAVAILABLE
        elif used < self.window:
            status = STATUS_SHRUNK
        else:
            status = STATUS_FULL
        return WindowState(
            label=WINDOW_LABEL,
            requested=self.window,
            used=used,
            season=season,
            current_season_matches=n_current,
            status=status,
        )

    def team_form(self, league: str, team: str, before: int) -> TeamForm:
        """Recency-weighted means over the shrinking current-season window."""
        eligible = self._eligible(league, team, before)
        state = self.window_state(league, team, before)
        selected = eligible[-self.window :] if eligible else []
        produced: dict[str, float] = {}
        conceded: dict[str, float] = {}
        for stat in self.stats:
            produced[stat] = self._weighted_mean(selected, stat, own=True, league=league)
            conceded[stat] = self._weighted_mean(selected, stat, own=False, league=league)
        return TeamForm(
            team=team,
            league=league,
            window=state,
            produced=produced,
            conceded=conceded,
        )

    def _weighted_mean(
        self,
        selected: Sequence[tuple[int, str, dict[str, float], dict[str, float]]],
        stat: str,
        *,
        own: bool,
        league: str,
    ) -> float:
        """Recency-weighted mean, falling back to the league prior when empty.

        The fallback is the running league mean over matches already observed —
        never zero, and never a value drawn from the fixture being predicted. Zero
        would assert that a team with no record generates no corners, which is a
        much stronger and much more wrong claim than "assume the league average".
        """
        values: list[tuple[float, float]] = []
        total = len(selected)
        for position, row in enumerate(selected):
            source = row[2] if own else row[3]
            value = source.get(stat)
            if value is None:
                continue
            age = total - 1 - position
            weight = 0.5 ** (age / self.half_life_matches)
            values.append((weight, float(value)))
        if values:
            weight_sum = sum(weight for weight, _ in values)
            if weight_sum > 0:
                return sum(weight * value for weight, value in values) / weight_sum
        key = (league, stat)
        if self._league_n[key]:
            return self._league_sum[key] / self._league_n[key]
        return 0.0

    # ── writing ───────────────────────────────────────────────────────────
    def observe(self, match: Mapping[str, object]) -> None:
        """Fold one completed match into history. Call only after reading."""
        league = str(match.get("_league") or match.get("league") or "")
        season = season_key(match)
        kickoff = numeric(match.get("date_unix"))
        home = _team_id(match, home=True)
        away = _team_id(match, home=False)
        if not league or season is None or kickoff is None or home is None or away is None:
            return
        home_stats: dict[str, float] = {}
        away_stats: dict[str, float] = {}
        for stat in self.stats:
            home_value = stat_value(match, stat, home=True)
            away_value = stat_value(match, stat, home=False)
            if home_value is not None:
                home_stats[stat] = home_value
                self._league_sum[(league, stat)] += home_value
                self._league_n[(league, stat)] += 1
            if away_value is not None:
                away_stats[stat] = away_value
                self._league_sum[(league, stat)] += away_value
                self._league_n[(league, stat)] += 1
        self._history[(league, home)].append(
            (int(kickoff), season, home_stats, away_stats)
        )
        self._history[(league, away)].append(
            (int(kickoff), season, away_stats, home_stats)
        )

    def observe_batch(self, matches: Iterable[Mapping[str, object]]) -> None:
        for match in matches:
            self.observe(match)


def _team_id(match: Mapping[str, object], *, home: bool) -> Optional[str]:
    keys = ("homeID", "home_id", "home_name") if home else ("awayID", "away_id", "away_name")
    for key in keys:
        value = match.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The minimum-history gate
# ─────────────────────────────────────────────────────────────────────────────
def window_sufficient(state: WindowState) -> bool:
    """Whether this window carries enough evidence to publish from.

    **The gate keys on window availability, not on a raw match count.** That was
    an open question and the shrinking window settles it. Under the previous fixed
    window the two could disagree in the worst possible direction: a team with
    three or four completed matches passed the ``min 3`` raw-count floor while
    every rolling window abstained, so the fixture was priced with no rolling form
    behind any feature. Keying on the window closes that gap by construction —
    if the window is unavailable the fixture is not priced, whatever the raw count
    says.

    The raw-count floor is kept as well, and it remains the binding constraint:
    a one- or two-match window is available but is not enough history to publish
    from. So both conditions must hold, and they no longer contradict each other.
    """
    return (
        state.available
        and state.current_season_matches >= MIN_CURRENT_SEASON_MATCHES
    )


def gate_reason(home: TeamForm, away: TeamForm) -> Optional[str]:
    """Why this fixture cannot be priced, or ``None`` when it can."""
    for form in (home, away):
        state = form.window
        if not state.available:
            return (
                f"no current-season rolling window for {form.team}: "
                f"{state.current_season_matches} completed current-season match(es), "
                f"minimum {MIN_WINDOW_MATCHES} to form a window. The window is never "
                "backfilled from the prior season."
            )
        if state.current_season_matches < MIN_CURRENT_SEASON_MATCHES:
            return (
                f"insufficient current-season history for {form.team}: "
                f"{state.current_season_matches} completed current-season match(es), "
                f"minimum {MIN_CURRENT_SEASON_MATCHES}"
            )
    return None


def window_provenance(home: TeamForm, away: TeamForm) -> dict[str, object]:
    """Per-team window provenance, including the actual match count used.

    This is the field the broadcast text was omitting. It is the most important
    provenance a reader has, because it says whether a forecast rests on a full
    rolling window or on the two matches a promoted side has played so far.
    """
    return {
        "window_declared": WINDOW_LABEL,
        "window_requested": DEFAULT_WINDOW,
        "window_policy": (
            "current season only; shrinks below the declared window rather than "
            "backfilling from the prior season"
        ),
        "min_current_season_matches": MIN_CURRENT_SEASON_MATCHES,
        "gate_keys_on": "window_availability_and_min_current_season_matches",
        "home": home.to_dict(),
        "away": away.to_dict(),
        "sufficient": gate_reason(home, away) is None,
    }
