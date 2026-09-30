"""V3.3 point-in-time corner-pressure feature construction.

The frozen V3 corner model is not modified. This module builds research-only
regularized count challengers from provider-native historical evidence.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .modeling import (
    COMPLETION_BUFFER_SECONDS, FEATURE_HORIZON_SECONDS, HALF_LIFE_DAYS,
    MIN_FEATURE_HISTORY, MIN_TEAM_TARGET_HISTORY, SHRINK_MATCHES,
)
from .modeling_v322 import _apply_elo, _elo_expected, _venue, number

CORNER_PATHS = {
    "shots": "overview.total_shots",
    "blocked": "shots.blocked_shots",
    "crosses": "passes.accurate_crosses",
    "entries": "passes.final_third_entries",
    "box": "shots.shots_inside_box",
    "touches_box": "attack.touches_in_penalty_area",
    "possession": "overview.ball_possession",
    "clearances": "defending.clearances",
    "shots_off": "shots.shots_off_target",
    "throw_ins": "passes.throw_ins",
    "accurate_long_balls": "passes.accurate_long_balls",
    "offsides": "attack.offsides",
    "goal_kicks": "goalkeeping.goal_kicks",
    "free_kicks": "overview.free_kicks",
}
PRESSURE_KEYS = (
    "shots", "blocked", "crosses", "entries", "box",
    "touches_box", "possession", "clearances", "shots_off",
)
EXTENDED_KEYS = PRESSURE_KEYS + (
    "throw_ins", "accurate_long_balls", "offsides", "goal_kicks", "free_kicks",
)
VENUE_KEYS = ("corners",) + PRESSURE_KEYS
MIN_VENUE_HISTORY = 3


def _metric(row: dict, key: str, side: str) -> float | None:
    target = (row.get("targets") or {}).get(f"corners.{side}") or {}
    if target.get("period_status") != "NO_EXTRA_TIME_RECORDED":
        return None
    path = CORNER_PATHS[key]
    bad = {(x.get("path"), x.get("side")) for x in row.get("period_checks", [])}
    if (path, side) in bad:
        return None
    return number((row.get("raw_stats") or {}).get(f"{path}.all.{side}"))


def row_metrics(row: dict) -> dict:
    out = {"home": {}, "away": {}}
    for side in out:
        out[side]["corners"] = number(row["targets"][f"corners.{side}"]["value"])
        for key in CORNER_PATHS:
            out[side][key] = _metric(row, key, side)
    return out
def _weighted(entries: list[dict], key: str, kind: str, cutoff: float):
    vals = []
    for entry in entries:
        value = entry[kind].get(key)
        if value is None:
            continue
        weight = 2 ** (-(cutoff - entry["ts"]) / 86400.0 / HALF_LIFE_DAYS)
        vals.append((value, weight))
    return sum(v * w for v, w in vals), sum(w for _, w in vals), len(vals)


def _profile(entries: list[dict], pool: list[dict], cutoff: float,
             keys: tuple[str, ...]) -> dict:
    out = {}
    for key in keys:
        for kind in ("own", "opp"):
            num, den, n = _weighted(entries, key, kind, cutoff)
            gnum, gden, _ = _weighted(pool, key, kind, cutoff)
            prior = gnum / gden if gden else None
            out[f"{kind}_{key}"] = (
                (num + SHRINK_MATCHES * prior) / (den + SHRINK_MATCHES)
                if prior is not None else None
            )
            out[f"{kind}_{key}_n"] = n
    return out


def _venue_profile(entries: list[dict], overall: dict, cutoff: float,
                   keys: tuple[str, ...]) -> dict:
    out = {}
    for key in keys:
        for kind in ("own", "opp"):
            num, den, n = _weighted(entries, key, kind, cutoff)
            anchor = overall.get(f"{kind}_{key}")
            out[f"{kind}_{key}"] = (
                (num + SHRINK_MATCHES * anchor) / (den + SHRINK_MATCHES)
                if anchor is not None else None
            )
            out[f"{kind}_{key}_n"] = n
    return out


def _support(profile: dict, keys: tuple[str, ...], minimum: int) -> bool:
    return all(
        profile.get(f"{kind}_{key}_n", 0) >= minimum
        for key in keys for kind in ("own", "opp")
    )


def _vector(p: dict, q: dict, keys: tuple[str, ...], elo_delta: float,
            venue: float | None, comp_prior: float | None) -> list[float | None]:
    values = [
        p["own_corners"], p["opp_corners"],
        q["own_corners"], q["opp_corners"],
        elo_delta, venue, comp_prior,
    ]
    for key in keys:
        values.extend([
            p[f"own_{key}"], p[f"opp_{key}"],
            q[f"own_{key}"], q[f"opp_{key}"],
        ])
    return values


def _venue_append(profile: dict) -> list[float | None]:
    values = []
    for key in VENUE_KEYS:
        values.extend([profile.get(f"own_{key}"), profile.get(f"opp_{key}")])
    return values


def _comp_prior(pool: list[dict], cutoff: float) -> float | None:
    num, den, _ = _weighted(pool, "corners", "own", cutoff)
    return num / den if den else None


def _venue_side(row: dict, side: str) -> str:
    neutral = (row.get("context") or {}).get("is_neutral")
    if neutral is False:
        return side
    return "neutral" if neutral is True else "unknown"
def build_corner_panel(rows: list[dict]) -> list[dict]:
    profile_keys = ("corners",) + EXTENDED_KEYS
    history: dict[str, list[dict]] = defaultdict(list)
    pools: dict[str, list[dict]] = defaultdict(list)
    ratings: dict[str, dict[str, float]] = defaultdict(dict)
    pending: dict[str, list[dict]] = defaultdict(list)
    panel = []

    eligible_rows = [
        row for row in rows
        if row["targets"]["corners.home"]["value"] is not None
        and row["targets"]["corners.away"]["value"] is not None
        and row.get("raw_stats")
    ]
    for row in sorted(eligible_rows, key=lambda r: (r["kickoff_ts"], r["match_id"])):
        ts = float(row["kickoff_ts"])
        cutoff = ts - FEATURE_HORIZON_SECONDS
        comp = str(row["competition_id"])
        hid, aid = str(row["home_id"]), str(row["away_id"])

        pool = [e for e in pools[comp]
                if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        hh = [e for e in history[hid]
              if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        ah = [e for e in history[aid]
              if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        hp = _profile(hh, pool, cutoff, profile_keys)
        ap = _profile(ah, pool, cutoff, profile_keys)

        home_home = [e for e in hh if e.get("venue_side") == "home"]
        away_away = [e for e in ah if e.get("venue_side") == "away"]
        hvp = _venue_profile(home_home, hp, cutoff, VENUE_KEYS)
        avp = _venue_profile(away_away, ap, cutoff, VENUE_KEYS)

        _apply_elo(ratings[comp], pending[comp], cutoff)
        elo = (
            ratings[comp].get(hid, 1500.0)
            - ratings[comp].get(aid, 1500.0)
        ) / 400.0
        prior = _comp_prior(pool, cutoff)
        metrics = row_metrics(row)
        y = [metrics["home"]["corners"], metrics["away"]["corners"]]

        core = (
            _support(hp, ("corners",), MIN_TEAM_TARGET_HISTORY)
            and _support(ap, ("corners",), MIN_TEAM_TARGET_HISTORY)
            and None not in y
        )
        pressure = (
            core
            and _support(hp, PRESSURE_KEYS, MIN_FEATURE_HISTORY)
            and _support(ap, PRESSURE_KEYS, MIN_FEATURE_HISTORY)
        )
        extended = (
            pressure
            and _support(hp, EXTENDED_KEYS, MIN_FEATURE_HISTORY)
            and _support(ap, EXTENDED_KEYS, MIN_FEATURE_HISTORY)
        )
        venue_supported = (
            pressure
            and (row.get("context") or {}).get("is_neutral") is False
            and _support(hvp, VENUE_KEYS, MIN_VENUE_HISTORY)
            and _support(avp, VENUE_KEYS, MIN_VENUE_HISTORY)
        )

        home_base = _vector(hp, ap, (), elo, _venue(row, "home"), prior)
        away_base = _vector(ap, hp, (), -elo, _venue(row, "away"), prior)
        home_pressure = _vector(
            hp, ap, PRESSURE_KEYS, elo, _venue(row, "home"), prior)
        away_pressure = _vector(
            ap, hp, PRESSURE_KEYS, -elo, _venue(row, "away"), prior)
        home_extended = _vector(
            hp, ap, EXTENDED_KEYS, elo, _venue(row, "home"), prior)
        away_extended = _vector(
            ap, hp, EXTENDED_KEYS, -elo, _venue(row, "away"), prior)
        home_venue = home_pressure + _venue_append(hvp)
        away_venue = away_pressure + _venue_append(avp)

        panel.append({
            "match_id": row["match_id"],
            "competition_id": comp,
            "date": row["kickoff"][:10],
            "kickoff_ts": ts,
            "cutoff_ts": cutoff,
            "home_id": hid,
            "away_id": aid,
            "y": y,
            "eligible_core": core,
            "eligible_pressure": pressure,
            "eligible_extended": extended,
            "eligible_venue": venue_supported,
            "home": {
                "base": home_base,
                "pressure": home_pressure,
                "extended": home_extended,
                "venue": home_venue,
            },
            "away": {
                "base": away_base,
                "pressure": away_pressure,
                "extended": away_extended,
                "venue": away_venue,
            },
            "venue_support": {
                "home": hvp.get("own_corners_n", 0),
                "away": avp.get("own_corners_n", 0),
            },
        })
        for side, other, team_id in (
            ("home", "away", hid), ("away", "home", aid)
        ):
            entry = {
                "match_id": row["match_id"],
                "ts": ts,
                "own": metrics[side],
                "opp": metrics[other],
                "venue_side": _venue_side(row, side),
            }
            history[team_id].append(entry)
            pools[comp].append(entry)

        gh = number(row["targets"]["goals.home"]["value"])
        ga = number(row["targets"]["goals.away"]["value"])
        if gh is not None and ga is not None:
            pending[comp].append({
                "ts": ts, "home_id": hid, "away_id": aid,
                "home_goals": gh, "away_goals": ga,
                "is_neutral": (row.get("context") or {}).get("is_neutral"),
            })
    return panel
