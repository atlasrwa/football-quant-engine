"""cohort_policy_v1 — deterministic, PIT-safe conditional cohort engine.

This is the "deterministic query planner" of the architecture (brief §8, §11, §40): it
generates a *predefined* hierarchy of historical slices for a fixture. The LLM never
decides what to query; it only interprets these fixed cohorts. All numbers are computed
here in Python (brief §7).

Temporal rule (brief §10, §36): a cohort for fixture F reads ONLY prior matches
(kickoff_unix < F.kickoff_unix) within the same competition-season for team state, and
prior matches for league/cluster baselines. Never F itself, never the future.

Hierarchical conditioning (brief §12, §41): estimates shrink from specific->general via
empirical-Bayes partial pooling toward the parent tier, so a tiny exact cohort cannot
masquerade as strong evidence. Every estimate carries n, reliability and shrinkage level.

Style clusters (brief §13, §42) are DATA-DRIVEN: an opponent is described by a
standardized behavioral profile computed from its own prior matches, then bucketed into
deterministic style tags. We never derive style from club names.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Callable

from src.research.matchup.corpus import MatchRecord, season_of

MIN_HISTORY = 4          # cold-start floor (matches matchup layer)
SHRINK_K = 6.0           # empirical-Bayes strength: n/(n+K) weight toward parent


# ---- metric extraction from a MatchRecord for a given team & period ------------
# Returns (for_value, against_value) i.e. team's own vs conceded, or None if absent.
# period in {"all","first_half","second_half"}.

def _rich_pair(rec: MatchRecord, key: str):
    v = rec.rich.get(key)
    return v if (isinstance(v, (list, tuple)) and len(v) == 2) else None


def _half_cell(rec: MatchRecord, group: str, stat: str, period: str):
    """Read a half-split pair (home, away) directly from the raw stats payload cell,
    which the normalizer drops. Provenance: TheStatsAPI raw /stats."""
    raw = rec.extra.get(f"_half::{group}::{stat}")
    if not raw:
        return None
    cell = raw.get(period)
    if not cell:
        return None
    h, a = cell.get("home"), cell.get("away")
    if h is None or a is None:
        return None
    return (float(h), float(a))


# Canonical metric name -> where to read the "all-period" pair from a MatchRecord.
# ('rich', key) reads rec.rich[key]; ('extra', key) reads rec.extra[key].
ALL_METRICS = {
    "crosses": ("rich", "accurate_crosses"),
    "total_shots": ("extra", "total_shots"),
    "shots_on_target": ("rich", "shots_on_target"),
    "shots_inside_box": ("rich", "shots_inside_box"),
    "shots_outside_box": ("rich", "shots_outside_box"),
    "blocked_shots": ("rich", "blocked_shots"),
    "corners": ("rich", "corner_kicks"),
    "possession": ("extra", "possession"),
    "fouls": ("rich", "fouls"),
    "yellow_cards": (None, None),          # from base (see team_metric)
    "tackles": ("rich", "tackles"),
    "touches_in_box": ("rich", "touches_in_penalty_area"),
    "final_third_entries": ("rich", "final_third_entries"),
    "throw_ins": ("extra", "throw_ins"),
    "clearances": ("rich", "clearances"),
    "interceptions": ("rich", "interceptions"),
    "big_chances": ("rich", "big_chances"),
    "npxg": ("rich", "np_expected_goals"),
    "saves": ("rich", "saves"),
}

# Canonical metric name -> (raw group, raw stat) for half-split reads. Only stats
# verified present in the raw payload with first_half/second_half splits.
HALF_METRICS = {
    "crosses": ("passes", "accurate_crosses"),
    "total_shots": ("shots", "total_shots"),
    "shots_on_target": ("shots", "shots_on_target"),
    "shots_inside_box": ("shots", "shots_inside_box"),
    "blocked_shots": ("shots", "blocked_shots"),
    "corners": ("overview", "corner_kicks"),
    "possession": ("overview", "ball_possession"),
    "fouls": ("overview", "fouls"),
    "yellow_cards": ("overview", "yellow_cards"),
    "tackles": ("defending", "tackles"),
    "touches_in_box": ("attack", "touches_in_penalty_area"),
    "final_third_entries": ("passes", "final_third_entries"),
    "throw_ins": ("passes", "throw_ins"),
    "clearances": ("defending", "clearances"),
    "interceptions": ("defending", "interceptions"),
}


def team_metric(rec: MatchRecord, team: str, metric: str, side: str, period: str = "all"):
    """Return the value of `metric` for `team` in `rec`.
    side='for' -> team's own production; side='against' -> what team conceded.
    Uses half-split raw cell when period != 'all'."""
    is_home = (rec.home == team or rec.home_id == team)
    is_away = (rec.away == team or rec.away_id == team)
    if not (is_home or is_away):
        return None
    if metric in HALF_METRICS and period != "all":
        grp, stat = HALF_METRICS[metric]
        pair = _half_cell(rec, grp, stat, period)
        if pair is None:
            return None
        home_v, away_v = pair
    else:
        if period != "all":
            return None
        # yellow_cards comes from base fields (team_a/team_b)
        if metric == "yellow_cards":
            h = rec.base.get("team_a_yellow_cards")
            a = rec.base.get("team_b_yellow_cards")
            if h is None or a is None:
                return None
            home_v, away_v = float(h), float(a)
        else:
            src = ALL_METRICS.get(metric)
            if not src or src[0] is None:
                return None
            store = rec.rich if src[0] == "rich" else rec.extra
            pair = store.get(src[1])
            if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                return None
            if pair[0] is None or pair[1] is None:
                return None
            home_v, away_v = float(pair[0]), float(pair[1])
    own, opp = (home_v, away_v) if is_home else (away_v, home_v)
    return own if side == "for" else opp


# ---- style profiling (data-driven opponent clusters) ---------------------------
_STYLE_METRICS = ["possession", "crosses", "total_shots", "touches_in_box"]


def _team_style_vector(idx: "HistoryIndex", team: str, before_unix: int, season: str):
    """Standardized-ish behavioral fingerprint from the team's prior matches this season.
    Returns dict metric->mean or None if insufficient history. PIT-safe."""
    out = {}
    n_ok = 0
    for m in _STYLE_METRICS:
        vals = idx.prior_values(team, m, "for", before_unix, season, period="all")
        if len(vals) >= MIN_HISTORY:
            out[m] = sum(vals) / len(vals)
            n_ok += 1
    return out if n_ok >= 2 else None


def style_tags(profile: Optional[dict], league_ref: dict) -> list[str]:
    """Deterministic style buckets from the profile vs league reference means.
    league_ref: metric -> league mean. Tags are coarse and evidence-derived."""
    if not profile:
        return ["STYLE_UNKNOWN"]
    tags = []
    def hi(m):
        return m in profile and m in league_ref and league_ref[m] and profile[m] > 1.15 * league_ref[m]
    def lo(m):
        return m in profile and m in league_ref and league_ref[m] and profile[m] < 0.85 * league_ref[m]
    if hi("possession"):
        tags.append("HIGH_POSSESSION")
    if lo("possession"):
        tags.append("LOW_BLOCK_OR_DIRECT")
    if hi("crosses"):
        tags.append("HIGH_WIDTH")
    if hi("touches_in_box"):
        tags.append("HIGH_BOX_ENTRY")
    if hi("total_shots"):
        tags.append("SHOT_HEAVY")
    return tags or ["BALANCED"]


# ---- history index -------------------------------------------------------------
class HistoryIndex:
    def __init__(self, recs: list[MatchRecord]):
        self.recs = sorted(recs, key=lambda r: r.kickoff_unix)

    def current_season(self, team: str, before_unix: int) -> Optional[str]:
        """Season-instance of the team's most recent match BEFORE `before_unix`.

        This answers "which season did this team LAST PLAY IN?" -- not "which season does
        the target fixture belong to?". For a fixture early in a new season-instance, before
        the team has played in it, this returns the PREVIOUS season. Using it to filter
        current-season evidence therefore serves prior-season history as current-season
        state and lets cold-start floors be met by stale data.

        Use `target_season(target_record)` for any target-conditioned evidence. This
        function is retained because it answers a different, legitimate question, and its
        behaviour is deliberately unchanged.
        """
        seasons = [season_of(r) for r in self.recs
                   if r.kickoff_unix < before_unix and (r.home in (team,) or r.away in (team,)
                        or r.home_id == team or r.away_id == team)]
        return seasons[-1] if seasons else None

    @staticmethod
    def target_season(target: MatchRecord) -> str:
        """The season-instance the TARGET fixture itself belongs to.

        Derived from `season_of(target)` and from nothing else -- never inferred from either
        team's history, so both sides are filtered by one key and neither can drift into a
        different season. When a team has no prior matches in this season-instance the
        evidence builders find zero rows and abstain, which is the documented cold-start
        behaviour rather than a silent fallback to the prior season.
        """
        return season_of(target)

    def prior_records(self, team: str, before_unix: int, season: Optional[str],
                      venue: Optional[str] = None):
        out = []
        for r in self.recs:
            if r.kickoff_unix >= before_unix:
                continue
            if season is not None and season_of(r) != season:
                continue
            is_home = (r.home == team or r.home_id == team)
            is_away = (r.away == team or r.away_id == team)
            if not (is_home or is_away):
                continue
            if venue == "home" and not is_home:
                continue
            if venue == "away" and not is_away:
                continue
            out.append(r)
        return out

    def prior_values(self, team, metric, side, before_unix, season, venue=None, period="all"):
        vals = []
        for r in self.prior_records(team, before_unix, season, venue):
            v = team_metric(r, team, metric, side, period)
            if v is not None:
                vals.append(v)
        return vals


# ---- estimate with shrinkage ---------------------------------------------------
@dataclass
class Estimate:
    metric: str
    value: Optional[float]
    sample_n: int
    reliability: str          # LOW/MEDIUM/HIGH
    shrinkage_level: str      # which parent it was shrunk toward
    evidence_level: str       # cohort tier used
    scope: dict


def _reliability(n: int) -> str:
    if n >= 15:
        return "HIGH"
    if n >= MIN_HISTORY:
        return "MEDIUM"
    return "LOW"


def shrink(child_vals: list[float], parent_mean: Optional[float]) -> Optional[float]:
    """Empirical-Bayes partial pooling of a child cohort toward a parent mean."""
    n = len(child_vals)
    if n == 0:
        return parent_mean
    child_mean = sum(child_vals) / n
    if parent_mean is None:
        return child_mean if n >= MIN_HISTORY else None
    w = n / (n + SHRINK_K)
    return w * child_mean + (1 - w) * parent_mean
