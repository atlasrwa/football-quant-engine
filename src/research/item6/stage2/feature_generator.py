"""ITEM 6 STAGE 2 deterministic PIT feature generator (`item6_stage2_feature_generator_v1`).

Computes the Stage-2 LLM-derived feature values for one fixture from ONLY the matches completed
strictly before its kickoff. No LLM call, no network, no per-fixture manual decision.

POINT-IN-TIME DISCIPLINE -- deliberately identical to the champion's `roll()`
-----------------------------------------------------------------------------
  * eligible rows are the team's history entries with `date_unix < before`;
  * further restricted to the season-instance of the team's most recent completed match
    before `before` (`current_season_key`), so a window never spans seasons;
  * a fixed window (W5) ABSTAINS unless it can be filled from the current season;
  * a season-to-date statistic requires >= MIN_CURRENT_SEASON_MATCHES rows;
  * any missing underlying field ABSTAINS (returns None). Nothing is zero-filled or
    mean-imputed at feature-construction time.

Using the same cutoff rule as M0 is what makes the M0/M1 comparison a comparison of
INFORMATION rather than of leakage discipline.

`team_a`/`team_b` are the provider's home/away sides; FOR/AGAINST flips with the team's role in
each historical match, exactly as the champion does it.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.research.item6.stage2 import feature_spec as FS
from src.research.item6.stage2 import provider_measurability as PM

FEATURE_GENERATOR_VERSION = "item6_stage2_feature_generator_v1"

MIN_CURRENT_SEASON_MATCHES = 3      # mirrors pilotC_stat_mixer.MIN_CURRENT_SEASON_MATCHES
W5 = 5

# canonical metric -> (team_a field, team_b field) for FULL_MATCH values.
FULL_FIELDS: Dict[str, Tuple[str, str]] = {
    "goals": ("homeGoalCount", "awayGoalCount"),
    "shots": ("team_a_shots", "team_b_shots"),
    "shots_on_target": ("team_a_shotsOnTarget", "team_b_shotsOnTarget"),
    "corner_kicks": ("team_a_corners", "team_b_corners"),
    "possession": ("team_a_possession", "team_b_possession"),
    "fouls": ("team_a_fouls", "team_b_fouls"),
    "yellow_cards": ("team_a_yellow_cards", "team_b_yellow_cards"),
    "red_cards": ("team_a_red_cards", "team_b_red_cards"),
    "offsides": ("team_a_offsides", "team_b_offsides"),
    "cards_2h": ("team_a_2h_cards", "team_b_2h_cards"),
}
# canonical metric -> period -> (team_a field, team_b field)
HALF_FIELDS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "corner_kicks": {"FIRST_HALF": ("team_a_fh_corners", "team_b_fh_corners"),
                     "SECOND_HALF": ("team_a_2h_corners", "team_b_2h_corners")},
    "goals": {"FIRST_HALF": ("ht_goals_team_a", "ht_goals_team_b"),
              "SECOND_HALF": ("__2h_goals__", "__2h_goals__")},
    "cards_2h": {"SECOND_HALF": ("team_a_2h_cards", "team_b_2h_cards")},
}


def _num(v) -> Optional[float]:
    """Provider value -> float, treating None and the -1 placeholder as MISSING."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f == -1.0 or math.isnan(f) or math.isinf(f):
        return None
    return f


def _side_field(fields: Tuple[str, str], role: str, perspective: str) -> str:
    """Pick team_a/team_b field for the team's own value (FOR) or its opponent's (AGAINST)."""
    a, b = fields
    own_is_a = (role == "home")
    if perspective == PM.PERSPECTIVE_FOR:
        return a if own_is_a else b
    return b if own_is_a else a


def _match_value(m: Dict, metric: str, perspective: str, period: str,
                 role: str) -> Optional[float]:
    if period == FS.PERIOD_FULL:
        fields = FULL_FIELDS.get(metric)
        if not fields:
            return None
        return _num(m.get(_side_field(fields, role, perspective)))
    per = (HALF_FIELDS.get(metric) or {}).get(period)
    if not per:
        return None
    if metric == "goals" and period == "SECOND_HALF":
        full = _match_value(m, "goals", perspective, FS.PERIOD_FULL, role)
        first = _match_value(m, "goals", perspective, "FIRST_HALF", role)
        if full is None or first is None:
            return None
        return full - first
    return _num(m.get(_side_field(per, role, perspective)))


def _eligible_rows(hist: Dict, team: str, before: float,
                   season_key_fn: Callable, season) -> List[Tuple[float, Dict, str]]:
    if season is None:
        return []
    return [(d, m, r) for d, m, r in hist.get(team, [])
            if d < before and season_key_fn(m) == season]


def rolling_stat(hist: Dict, team: str, metric: str, perspective: str, period: str,
                 window: Optional[int], before: float, *, season, season_key_fn
                 ) -> Optional[float]:
    """Rolling mean of a metric over CURRENT-SEASON completed matches strictly before `before`."""
    rows = _eligible_rows(hist, team, before, season_key_fn, season)
    if window:
        rows = rows[-window:]
        if len(rows) < window:
            return None
    elif len(rows) < MIN_CURRENT_SEASON_MATCHES:
        return None
    vals: List[float] = []
    for _, m, r in rows:
        v = _match_value(m, metric, perspective, period, r)
        if v is None:
            return None
        vals.append(v)
    return (sum(vals) / len(vals)) if vals else None


def second_half_share(hist: Dict, team: str, metric: str, perspective: str, before: float,
                      *, season, season_key_fn) -> Optional[float]:
    """Rolling mean of the SECOND-HALF SHARE of a metric: 2h / (fh + 2h), per prior match.

    A prior match whose total is zero has an UNDEFINED share (0/0). Such a match is SKIPPED,
    never imputed to 0.5, and the statistic abstains unless at least
    MIN_CURRENT_SEASON_MATCHES matches yielded a defined share. (Abstaining on the whole
    statistic instead would make the goals share unusable, since a single 0-0 prior match would
    erase it.) The estimand is therefore the mean second-half share over prior current-season
    matches in which the metric occurred at all; that definition is fixed here, before any
    outcome is observed.

    Abstains when the metric is not half-capable or when a half value is MISSING (as opposed to
    zero) -- a missing field is an integrity problem, not a legitimate zero.
    """
    if not PM.is_half_capable(metric):
        return None
    rows = _eligible_rows(hist, team, before, season_key_fn, season)
    if len(rows) < MIN_CURRENT_SEASON_MATCHES:
        return None
    shares: List[float] = []
    for _, m, r in rows:
        if metric == "cards_2h":           # itself a 2h count; share needs a full-match base
            second = _match_value(m, "cards_2h", perspective, "SECOND_HALF", r)
            total = _match_value(m, "yellow_cards", perspective, FS.PERIOD_FULL, r)
            if second is None or total is None:
                return None                # missing field: integrity abstain
            if total <= 0:
                continue                   # undefined share: skip this match
            shares.append(second / total)
            continue
        first = _match_value(m, metric, perspective, "FIRST_HALF", r)
        second = _match_value(m, metric, perspective, "SECOND_HALF", r)
        if first is None or second is None:
            return None                    # missing field: integrity abstain
        tot = first + second
        if tot <= 0:
            continue                       # undefined share: skip this match
        shares.append(second / tot)
    if len(shares) < MIN_CURRENT_SEASON_MATCHES:
        return None
    return sum(shares) / len(shares)


def banding_key(axis_stat_keys: Sequence[str]) -> str:
    """Stable key identifying one two-axis opponent profile."""
    return "||".join(axis_stat_keys)


def _banding_for(profile_banding, axis_keys: Sequence[str]):
    """Resolve the ProfileBanding fitted for THIS axis pair (None if absent)."""
    if profile_banding is None:
        return None
    if isinstance(profile_banding, dict):
        return profile_banding.get(banding_key(axis_keys))
    return profile_banding          # single banding (single-profile specs / tests)


def parse_stat_key(sk: str) -> Tuple[str, str, str, Optional[int]]:
    metric, perspective, period, window = sk.split(".")
    return metric, perspective, period, (W5 if window == FS.WINDOW_W5 else None)


def compute_required_stats(hist: Dict, home: str, away: str, before: float,
                           required_stat_keys: Sequence[str], *, season_key_fn
                           ) -> Dict[str, Dict[str, Optional[float]]]:
    """{stat_key: {'h': value, 'a': value}} for the fixture, PIT-safe."""
    seasons = {"h": season_key_fn.current_season_key(hist, home, before),
               "a": season_key_fn.current_season_key(hist, away, before)}
    teams = {"h": home, "a": away}
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for sk in required_stat_keys:
        metric, perspective, period, window = parse_stat_key(sk)
        out[sk] = {
            slot: rolling_stat(hist, teams[slot], metric, perspective, period, window, before,
                               season=seasons[slot], season_key_fn=season_key_fn._season_key)
            for slot in ("h", "a")
        }
    return out


def generate_features(*, hist: Dict, home: str, away: str, before: float,
                      spec: Dict, fitted_thresholds, profile_banding=None,
                      season_key_fn) -> Dict[str, object]:
    """Feature values + support metadata for ONE fixture.

    `fitted_thresholds` / `profile_banding` MUST have been fit on the training fold only. A
    column whose inputs are unavailable is emitted as None (abstain) and counted as missing;
    imputation, if any, is the model arm's responsibility and is identical across M0 and M1.
    """
    stats = compute_required_stats(hist, home, away, before,
                                   spec["required_rolling_statistics"],
                                   season_key_fn=season_key_fn)
    seasons = {"h": season_key_fn.current_season_key(hist, home, before),
               "a": season_key_fn.current_season_key(hist, away, before)}
    teams = {"h": home, "a": away}
    values: Dict[str, Optional[float]] = {}

    for c in spec["columns"]:
        slot = str(c["team_slot"])
        kind = c["kind"]
        val: Optional[float] = None

        if kind == FS.KIND_BAND_DUMMY:
            raw = stats.get(str(c["stat_key"]), {}).get(slot)
            band = fitted_thresholds.bin_of(str(c["stat_key"]), raw)
            val = None if band is None else (1.0 if band == c["band"] else 0.0)

        elif kind == FS.KIND_STD_PRODUCT:
            za = fitted_thresholds.standardize(str(c["stat_key_a"]),
                                              stats.get(str(c["stat_key_a"]), {}).get(slot))
            zb = fitted_thresholds.standardize(str(c["stat_key_b"]),
                                              stats.get(str(c["stat_key_b"]), {}).get(slot))
            val = None if (za is None or zb is None) else za * zb

        elif kind == FS.KIND_HALF_SHARE:
            share = second_half_share(hist, teams[slot], str(c["metric"]),
                                      str(c["perspective"]), before,
                                      season=seasons[slot],
                                      season_key_fn=season_key_fn._season_key)
            sk = f"{c['metric']}.{c['perspective']}.2H_SHARE.STD"
            val = fitted_thresholds.standardize(sk, share)

        elif kind == FS.KIND_PROFILE_DUMMY:
            # the OPPONENT's profile: the other slot's two axes
            opp = "a" if slot == "h" else "h"
            axis_keys = list(c["axis_stat_keys"])
            bands = [(ak, fitted_thresholds.bin_of(ak, stats.get(ak, {}).get(opp)))
                     for ak in axis_keys]
            # `profile_banding` is keyed by axis pair: one fitted banding per distinct
            # two-axis profile, so support counts are never shared across different axes.
            pb = _banding_for(profile_banding, axis_keys)
            resolved = pb.resolve(bands) if pb is not None else None
            if resolved is None:
                val = None
            else:
                want = f"{axis_keys[0]}={c['band']}"
                val = 1.0 if resolved.startswith(want) else 0.0

        values[str(c["name"])] = val

    n_missing = sum(1 for v in values.values() if v is None)
    return {
        "generator_version": FEATURE_GENERATOR_VERSION,
        "values": values,
        "support": {
            "n_columns": len(values),
            "n_missing": n_missing,
            "coverage_rate": (0.0 if not values else round(1.0 - n_missing / len(values), 6)),
            "home_current_season_matches": len(_eligible_rows(
                hist, home, before, season_key_fn._season_key, seasons["h"])),
            "away_current_season_matches": len(_eligible_rows(
                hist, away, before, season_key_fn._season_key, seasons["a"])),
        },
        "provenance": {
            "information_cutoff_unix": before,
            "pit_rule": "date_unix < kickoff AND current-season-instance only",
            "reads_outcomes": False,
            "made_llm_call": False,
        },
    }


def version_stamp() -> Dict[str, object]:
    return {
        "feature_generator_version": FEATURE_GENERATOR_VERSION,
        "pit_rule": "date_unix < kickoff AND current_season_key restriction",
        "min_current_season_matches": MIN_CURRENT_SEASON_MATCHES,
        "missing_policy": "abstain_never_impute_at_construction",
        "mirrors_champion_roll_discipline": True,
        "made_llm_call": False,
        "reads_outcomes": False,
    }
