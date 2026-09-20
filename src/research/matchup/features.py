"""PIT-safe feature builders for the contextual-matchup challenger.

All builders are STRICTLY point-in-time: for a target fixture F they read only prior
matches (kickoff_unix < F.kickoff_unix). Rolling windows never span a season-instance
(competition:season_id). Cold-start fails closed (returns None) below a minimum history.

Feature families (see EXPERIMENT design):
  team_state  : rolling FOR/AGAINST means of a stat, current-season, w5/w10/std
  home_away   : venue-conditioned team state (home team's home form, away team's away form)
  league_env  : leakage-safe competition baseline (prior matches this season-instance)
  opp_quality : shrunk attack/defense strength ratings (iterative, prior matches only)
  matchup     : explicit A-attack x B-defense combinations (sum/diff/geomean/product)

Nothing here reads the target fixture's own stats.
"""
from __future__ import annotations
import math
from collections import defaultdict
from typing import Any, Optional, Callable
import numpy as np

from src.research.matchup.corpus import MatchRecord, season_of

MIN_HISTORY = 3   # matches, current season-instance (mirrors champion MIN_CURRENT_SEASON_MATCHES)


# ---------------------------------------------------------------------------
# Stat accessors: given a MatchRecord and a stat name, return (home_value, away_value)
# with provider provenance. NULL != ZERO preserved (None propagates).
# ---------------------------------------------------------------------------
def _pair_from_base(rec: MatchRecord, a_field: str, b_field: str):
    h = rec.base.get(a_field); a = rec.base.get(b_field)
    return (h, a)


def stat_pair(rec: MatchRecord, stat: str):
    """Return (home_value, away_value) for a named concept, or (None, None)."""
    # goals (base)
    if stat == "goals":
        return (rec.base.get("homeGoalCount"), rec.base.get("awayGoalCount"))
    if stat == "xg":  # TheStatsAPI xG (post-match)
        return (rec.base.get("team_a_xg"), rec.base.get("team_b_xg"))
    if stat == "sot":
        return (rec.base.get("team_a_shotsOnTarget"), rec.base.get("team_b_shotsOnTarget"))
    if stat == "fouls":
        return (rec.base.get("team_a_fouls"), rec.base.get("team_b_fouls"))
    if stat == "cards":  # yellow + red
        yh, ya = rec.base.get("team_a_yellow_cards"), rec.base.get("team_b_yellow_cards")
        rh, ra = rec.base.get("team_a_red_cards") or 0, rec.base.get("team_b_red_cards") or 0
        return ((yh + rh) if yh is not None else None, (ya + ra) if ya is not None else None)
    if stat == "yellow_cards":
        return (rec.base.get("team_a_yellow_cards"), rec.base.get("team_b_yellow_cards"))
    # rich pairs (TheStatsAPI)
    if stat in rec.rich and rec.rich[stat] is not None:
        return rec.rich[stat]
    if stat in rec.extra and rec.extra[stat] is not None:
        return rec.extra[stat]
    # rich/extra concept present but null this match
    if stat in rec.rich or stat in rec.extra:
        return (None, None)
    raise KeyError(f"unknown stat {stat!r}")


ALL_STATS = [
    # outcome / core
    "goals", "xg", "sot", "cards", "yellow_cards", "fouls",
    # rich pressure / mechanism (TheStatsAPI)
    "corner_kicks", "big_chances", "big_chances_missed", "touches_in_penalty_area",
    "final_third_entries", "accurate_crosses", "tackles", "interceptions", "clearances",
    "ball_recoveries", "np_expected_goals", "shots_inside_box", "shots_outside_box",
    "blocked_shots", "accurate_long_balls", "saves", "high_claims",
    # extras
    "throw_ins", "free_kicks", "goal_kicks", "offsides", "possession", "total_shots",
    "shots_off_target", "hit_woodwork",
]


# ---------------------------------------------------------------------------
# History index: per team, ordered list of (kickoff, rec, side) within season.
# ---------------------------------------------------------------------------
class HistoryIndex:
    def __init__(self, recs: list[MatchRecord]):
        self.by_team: dict[str, list[tuple[int, MatchRecord, str]]] = defaultdict(list)
        for r in recs:
            self.by_team[r.home_id].append((r.kickoff_unix, r, "home"))
            self.by_team[r.away_id].append((r.kickoff_unix, r, "away"))
        for t in self.by_team:
            self.by_team[t].sort(key=lambda x: x[0])
        self.recs = recs

    def current_season(self, team_id: str, before: int) -> Optional[str]:
        """Season-instance of the team's most recent match BEFORE `before`.

        NOTE: this is the season the team LAST PLAYED IN, which is not necessarily the
        season a target fixture belongs to. For a fixture in a new season-instance before
        the team has played in it, this returns the PREVIOUS season. Feeding that to
        `_roll` produces prior-season numbers labelled as current-season form, and lets
        `MIN_HISTORY` be satisfied by stale data instead of failing closed.

        Use `target_season(rec)` for any current-season feature. This function is kept
        because it answers a different, legitimate question ("when did this team last
        play?"), and its behaviour is deliberately unchanged.
        """
        rows = [(k, r) for k, r, _ in self.by_team.get(team_id, []) if k < before]
        if not rows:
            return None
        return season_of(max(rows, key=lambda t: t[0])[1])

    @staticmethod
    def target_season(rec: MatchRecord) -> str:
        """The season-instance the TARGET fixture itself belongs to.

        This is the correct season for a current-season feature: it is a property of the
        fixture being predicted, never of the history available for it. When a team has no
        prior matches in this season-instance, `_roll` then sees zero rows and abstains,
        which is the documented cold-start behaviour.
        """
        return season_of(rec)

    def prior_rows(self, team_id: str, before: int, season: Optional[str], venue: Optional[str] = None):
        rows = []
        for k, r, side in self.by_team.get(team_id, []):
            if k >= before:
                continue
            if season is not None and season_of(r) != season:
                continue
            if venue is not None and side != venue:
                continue
            rows.append((k, r, side))
        return rows


def _roll(idx: HistoryIndex, team_id: str, stat: str, side: str, window: Optional[int],
          before: int, season: str, venue: Optional[str] = None) -> Optional[float]:
    """Rolling mean of `stat` FOR/AGAINST for a team, current-season, PIT-safe.

    side='for' -> team's own value; 'against' -> opponent's value in team's matches.
    venue: None (all), 'home', or 'away' (venue-conditioned).
    """
    rows = idx.prior_rows(team_id, before, season, venue=venue)
    if window:
        rows = rows[-window:]
        if len(rows) < window:
            return None
    else:
        if len(rows) < MIN_HISTORY:
            return None
    vals = []
    for _, r, row_side in rows:
        try:
            hv, av = stat_pair(r, stat)
        except KeyError:
            return None
        if side == "for":
            v = hv if row_side == "home" else av
        else:  # against = opponent value
            v = av if row_side == "home" else hv
        if v is None:
            continue
        vals.append(float(v))
    if not vals:
        return None
    # require at least MIN_HISTORY non-null for std window; window already length-checked
    if window is None and len(vals) < MIN_HISTORY:
        return None
    return float(np.mean(vals))


# ---------------------------------------------------------------------------
# League environment (leakage-safe): mean of a concept over PRIOR matches this
# season-instance (both teams' totals). Requires min prior matches.
# ---------------------------------------------------------------------------
class LeagueEnvironment:
    def __init__(self, recs: list[MatchRecord]):
        # per season-instance, chronological list of (kickoff, totals dict)
        self.by_season: dict[str, list[tuple[int, dict]]] = defaultdict(list)
        for r in recs:
            self.by_season[season_of(r)].append((r.kickoff_unix, r))
        for s in self.by_season:
            self.by_season[s].sort(key=lambda x: x[0])

    def env(self, rec: MatchRecord, stat: str, min_matches: int = 20) -> Optional[float]:
        s = season_of(rec)
        rows = [rr for k, rr in self.by_season.get(s, []) if k < rec.kickoff_unix]
        if len(rows) < min_matches:
            return None
        totals = []
        for rr in rows:
            try:
                hv, av = stat_pair(rr, stat)
            except KeyError:
                return None
            if hv is None or av is None:
                continue
            totals.append(float(hv) + float(av))
        if len(totals) < min_matches:
            return None
        return float(np.mean(totals))


# ---------------------------------------------------------------------------
# Opponent-quality-adjusted attack/defense ratings (shrunk, PIT-safe).
# Iterative rating on PRIOR matches only, per season-instance:
#   att[t] = mean over prior matches of (team's `for` value / league mean) adjusted by opp def
# We use a simple 2-pass shrunk multiplicative rating (attack, defense) computed from
# all prior matches in the season-instance. Recomputed as-of each fixture would be O(n^2);
# instead we build an incremental rolling estimate updated match-by-match in time order.
# ---------------------------------------------------------------------------
class StrengthRatings:
    """Incremental shrunk attack/defense multipliers per (season, team) for a stat.

    Processed in kickoff order, one SIMULTANEITY GROUP at a time: every match sharing an
    exact `kickoff_unix` is snapshotted before any of them updates the running state. The
    rating available for fixture F therefore reflects only matches that kicked off STRICTLY
    before F -- never a match kicking off at the same instant -- and is independent of the
    order the input list happened to be in. Multiplicative model around the league running
    mean, with shrinkage toward 1.0 by match count.
    """
    def __init__(self, recs: list[MatchRecord], stat: str, shrink: float = 4.0):
        self.stat = stat
        self.att: dict[tuple[str, str], float] = {}   # (season, team) -> attack mult snapshot at fixture time
        self.deff: dict[tuple[str, str], float] = {}
        self._snap_att: dict[str, float] = {}
        self._snap_def: dict[str, float] = {}
        # running state
        season_sum: dict[str, float] = defaultdict(float)
        season_cnt: dict[str, int] = defaultdict(int)
        team_for_sum: dict[tuple, float] = defaultdict(float)
        team_ag_sum: dict[tuple, float] = defaultdict(float)
        team_cnt: dict[tuple, int] = defaultdict(int)

        # Group by EXACT kickoff instant and snapshot the whole group before updating any of
        # it. Iterating match-by-match in sorted order leaked across simultaneous fixtures:
        # the first match of a 15:00 round updated the running state, and every later match
        # in that same round then snapshotted a state containing a result that had not
        # happened yet at its own kickoff. 56.6% of this corpus (3008/5319) shares a kickoff
        # with another match, so the leak was the common case rather than an edge case.
        # Grouping also makes the result independent of the input list's order, which the
        # plain `sorted()` tie-break silently determined.
        by_kickoff: dict[int, list[MatchRecord]] = defaultdict(list)
        for r in recs:
            by_kickoff[r.kickoff_unix].append(r)

        for kickoff in sorted(by_kickoff):
            group = by_kickoff[kickoff]

            # --- PASS 1: snapshot every match in the group against the SAME state ---------
            for r in group:
                s = season_of(r)
                try:
                    stat_pair(r, stat)
                except KeyError:
                    continue
                lm = (season_sum[s] / season_cnt[s]) if season_cnt[s] > 0 else None
                for team, key in ((r.home_id, (s, r.home_id)), (r.away_id, (s, r.away_id))):
                    c = team_cnt[key]
                    if lm and c > 0:
                        a_raw = (team_for_sum[key] / c) / lm if lm > 0 else 1.0
                        d_raw = (team_ag_sum[key] / c) / lm if lm > 0 else 1.0
                        w = c / (c + shrink)
                        self.att[key] = 1.0 + w * (a_raw - 1.0)
                        self.deff[key] = 1.0 + w * (d_raw - 1.0)
                    else:
                        self.att[key] = None
                        self.deff[key] = None
                # store per-fixture snapshot keyed by fixture+team
                self._snap_att[(r.fixture_id, r.home_id)] = self.att.get((s, r.home_id))
                self._snap_att[(r.fixture_id, r.away_id)] = self.att.get((s, r.away_id))
                self._snap_def[(r.fixture_id, r.home_id)] = self.deff.get((s, r.home_id))
                self._snap_def[(r.fixture_id, r.away_id)] = self.deff.get((s, r.away_id))

            # --- PASS 2: only now do the group's own results become the past --------------
            for r in group:
                s = season_of(r)
                try:
                    hv, av = stat_pair(r, stat)
                except KeyError:
                    continue
                if hv is not None and av is not None:
                    season_sum[s] += float(hv) + float(av); season_cnt[s] += 1
                    kh, ka = (s, r.home_id), (s, r.away_id)
                    team_for_sum[kh] += float(hv); team_ag_sum[kh] += float(av); team_cnt[kh] += 1
                    team_for_sum[ka] += float(av); team_ag_sum[ka] += float(hv); team_cnt[ka] += 1

    def attack(self, fixture_id: str, team_id: str) -> Optional[float]:
        return self._snap_att.get((fixture_id, team_id))

    def defense(self, fixture_id: str, team_id: str) -> Optional[float]:
        return self._snap_def.get((fixture_id, team_id))
