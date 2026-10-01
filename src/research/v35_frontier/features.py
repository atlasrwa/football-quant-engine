"""Point-in-time V3.5 feature construction for future fixtures.

Reuses the audited V3.2/V3.3 transforms but never consumes target-match stats.
"""
from __future__ import annotations

from collections import defaultdict

from src.research.evidence_v32.modeling import (
    COMPLETION_BUFFER_SECONDS, FEATURE_HORIZON_SECONDS,
    MIN_FEATURE_HISTORY, MIN_TEAM_TARGET_HISTORY,
)
from src.research.evidence_v32.modeling_v322 import (
    GOALS_DEEP, _apply_elo, _comp_prior as goal_comp_prior,
    _profile as goal_profile, _support as goal_support,
    _vector as goal_vector, _venue,
)
from src.research.evidence_v32.modeling_v323 import (
    VENUE_COUNT_KEYS, VENUE_RATE_KEYS, VENUE_XG_KEYS,
    _venue_features, _venue_profile as goal_venue_profile,
    _venue_side as goal_venue_side, _venue_supported,
    row_metrics_with_events,
)
from src.research.evidence_v32.modeling_v33_corners import (
    PRESSURE_KEYS, _comp_prior as corner_comp_prior,
    _profile as corner_profile, _support as corner_support,
    _vector as corner_vector, row_metrics as corner_row_metrics,
)


class FrontierUnsupported(RuntimeError):
    pass


def _fixture_row(fixture: dict) -> dict:
    neutral = fixture.get("is_neutral")
    if neutral is None:
        neutral = (fixture.get("context") or {}).get("is_neutral")
    return {
        "match_id": str(fixture["match_id"]),
        "competition_id": str(fixture["competition_id"]),
        "kickoff_ts": float(fixture.get("kickoff_ts", fixture.get("ts"))),
        "kickoff": str(fixture.get("kickoff") or fixture.get("utc_date") or ""),
        "home_id": str(fixture["home_id"]),
        "away_id": str(fixture["away_id"]),
        "context": {"is_neutral": neutral},
    }


def goal_target_features(rows: list[dict], fixture: dict) -> dict:
    target = _fixture_row(fixture)
    ts = target["kickoff_ts"]
    cutoff = ts - FEATURE_HORIZON_SECONDS
    comp = target["competition_id"]
    hid, aid = target["home_id"], target["away_id"]

    profile_keys = ("goals",) + GOALS_DEEP + VENUE_RATE_KEYS + VENUE_XG_KEYS
    history: dict[str, list[dict]] = defaultdict(list)
    pool: list[dict] = []
    pending: list[dict] = []

    for row in sorted(rows, key=lambda r: (float(r["kickoff_ts"]), str(r["match_id"]))):
        rts = float(row["kickoff_ts"])
        if rts + COMPLETION_BUFFER_SECONDS >= cutoff:
            continue
        metrics = row_metrics_with_events(row)
        rhid, raid = str(row["home_id"]), str(row["away_id"])
        for side, other, tid in (
            ("home", "away", rhid), ("away", "home", raid)
        ):
            entry = {
                "match_id": str(row["match_id"]),
                "ts": rts,
                "own": metrics[side],
                "opp": metrics[other],
                "venue_side": goal_venue_side(row, side),
            }
            history[tid].append(entry)
            if str(row["competition_id"]) == comp:
                pool.append(entry)
        gh, ga = metrics["home"]["goals"], metrics["away"]["goals"]
        if str(row["competition_id"]) == comp and gh is not None and ga is not None:
            pending.append({
                "ts": rts, "home_id": rhid, "away_id": raid,
                "home_goals": gh, "away_goals": ga,
                "is_neutral": (row.get("context") or {}).get("is_neutral"),
            })

    hp = goal_profile(history[hid], pool, cutoff, profile_keys)
    ap = goal_profile(history[aid], pool, cutoff, profile_keys)
    if not (
        goal_support(hp, ("goals",), MIN_TEAM_TARGET_HISTORY)
        and goal_support(ap, ("goals",), MIN_TEAM_TARGET_HISTORY)
        and goal_support(hp, GOALS_DEEP, MIN_FEATURE_HISTORY)
        and goal_support(ap, GOALS_DEEP, MIN_FEATURE_HISTORY)
    ):
        raise FrontierUnsupported("insufficient VENUE_DEEP overall/deep history")

    home_home = [e for e in history[hid] if e.get("venue_side") == "home"]
    away_away = [e for e in history[aid] if e.get("venue_side") == "away"]
    hvp = goal_venue_profile(
        home_home, hp, cutoff, VENUE_COUNT_KEYS + VENUE_RATE_KEYS + VENUE_XG_KEYS)
    avp = goal_venue_profile(
        away_away, ap, cutoff, VENUE_COUNT_KEYS + VENUE_RATE_KEYS + VENUE_XG_KEYS)
    if not (_venue_supported(hvp) and _venue_supported(avp)):
        raise FrontierUnsupported("insufficient home-at-home / away-away history")

    ratings: dict[str, float] = {}
    _apply_elo(ratings, pending, cutoff)
    elo = (ratings.get(hid, 1500.0) - ratings.get(aid, 1500.0)) / 400.0
    prior = goal_comp_prior(pool, "goals", cutoff)
    if prior is None:
        raise FrontierUnsupported("missing competition goal prior")

    home_deep = goal_vector(
        hp, ap, "goals", GOALS_DEEP, elo, _venue(target, "home"), prior)
    away_deep = goal_vector(
        ap, hp, "goals", GOALS_DEEP, -elo, _venue(target, "away"), prior)
    return {
        "home": home_deep + _venue_features(hvp),
        "away": away_deep + _venue_features(avp),
        "cutoff_ts": cutoff,
        "support": {
            "home_venue_matches": hvp.get("own_goals_n", 0),
            "away_venue_matches": avp.get("own_goals_n", 0),
        },
    }
def corner_target_features(rows: list[dict], fixture: dict) -> dict:
    target = _fixture_row(fixture)
    ts = target["kickoff_ts"]
    cutoff = ts - FEATURE_HORIZON_SECONDS
    comp = target["competition_id"]
    hid, aid = target["home_id"], target["away_id"]

    profile_keys = ("corners",) + PRESSURE_KEYS
    history: dict[str, list[dict]] = defaultdict(list)
    pool: list[dict] = []
    pending: list[dict] = []

    for row in sorted(rows, key=lambda r: (float(r["kickoff_ts"]), str(r["match_id"]))):
        rts = float(row["kickoff_ts"])
        if rts + COMPLETION_BUFFER_SECONDS >= cutoff:
            continue
        if not row.get("raw_stats"):
            continue
        metrics = corner_row_metrics(row)
        rhid, raid = str(row["home_id"]), str(row["away_id"])
        for side, other, tid in (
            ("home", "away", rhid), ("away", "home", raid)
        ):
            entry = {
                "match_id": str(row["match_id"]), "ts": rts,
                "own": metrics[side], "opp": metrics[other],
            }
            history[tid].append(entry)
            if str(row["competition_id"]) == comp:
                pool.append(entry)
        try:
            gh = float(row["targets"]["goals.home"]["value"])
            ga = float(row["targets"]["goals.away"]["value"])
        except (KeyError, TypeError, ValueError):
            gh = ga = None
        if str(row["competition_id"]) == comp and gh is not None and ga is not None:
            pending.append({
                "ts": rts, "home_id": rhid, "away_id": raid,
                "home_goals": gh, "away_goals": ga,
                "is_neutral": (row.get("context") or {}).get("is_neutral"),
            })

    hp = corner_profile(history[hid], pool, cutoff, profile_keys)
    ap = corner_profile(history[aid], pool, cutoff, profile_keys)
    if not (
        corner_support(hp, ("corners",), MIN_TEAM_TARGET_HISTORY)
        and corner_support(ap, ("corners",), MIN_TEAM_TARGET_HISTORY)
        and corner_support(hp, PRESSURE_KEYS, MIN_FEATURE_HISTORY)
        and corner_support(ap, PRESSURE_KEYS, MIN_FEATURE_HISTORY)
    ):
        raise FrontierUnsupported("insufficient CORNERS_PRESSURE history")

    ratings: dict[str, float] = {}
    _apply_elo(ratings, pending, cutoff)
    elo = (ratings.get(hid, 1500.0) - ratings.get(aid, 1500.0)) / 400.0
    prior = corner_comp_prior(pool, cutoff)
    if prior is None:
        raise FrontierUnsupported("missing competition corner prior")

    return {
        "home": corner_vector(
            hp, ap, PRESSURE_KEYS, elo, _venue(target, "home"), prior),
        "away": corner_vector(
            ap, hp, PRESSURE_KEYS, -elo, _venue(target, "away"), prior),
        "cutoff_ts": cutoff,
    }


def v3_corner_rows(rows: list[dict], competition_id: str) -> list[dict]:
    out = []
    for row in rows:
        if str(row.get("competition_id")) != str(competition_id):
            continue
        try:
            h = row["targets"]["corners.home"]["value"]
            a = row["targets"]["corners.away"]["value"]
            if h is None or a is None:
                continue
            out.append({
                "match_id": str(row["match_id"]),
                "competition_id": str(competition_id),
                "season_id": str(row.get("season_id") or ""),
                "ts": float(row["kickoff_ts"]),
                "home_id": str(row["home_id"]),
                "away_id": str(row["away_id"]),
                "corners_home": float(h), "corners_away": float(a),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out, key=lambda r: (r["ts"], r["match_id"]))
