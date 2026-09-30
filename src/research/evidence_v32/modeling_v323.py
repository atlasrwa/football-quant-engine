"""V3.2.3 venue-conditioned goal/BTTS feature construction.

Adds only preregistered historical venue splits. No odds or target-match stats
enter the feature path.
"""
from __future__ import annotations

from collections import defaultdict

from .modeling import (
    COMPLETION_BUFFER_SECONDS, FEATURE_HORIZON_SECONDS, MIN_FEATURE_HISTORY,
    SHRINK_MATCHES,
)
from .modeling_v322 import (
    GOALS_DEEP, _apply_elo, _comp_prior, _profile, _support, _vector, _venue,
    _weighted, row_metrics,
)

VENUE_COUNT_KEYS = ("goals", "shots", "sot", "box", "big")
VENUE_RATE_KEYS = ("clean_sheet", "failed_to_score", "btts")
VENUE_XG_KEYS = ("xg",)
MIN_VENUE_HISTORY = 3


def row_metrics_with_events(row: dict) -> dict:
    metrics = row_metrics(row)
    home_goals = metrics["home"]["goals"]
    away_goals = metrics["away"]["goals"]
    if home_goals is None or away_goals is None:
        for side in ("home", "away"):
            for key in VENUE_RATE_KEYS:
                metrics[side][key] = None
        return metrics
    both = float(home_goals > 0 and away_goals > 0)
    metrics["home"]["clean_sheet"] = float(away_goals == 0)
    metrics["away"]["clean_sheet"] = float(home_goals == 0)
    metrics["home"]["failed_to_score"] = float(home_goals == 0)
    metrics["away"]["failed_to_score"] = float(away_goals == 0)
    metrics["home"]["btts"] = both
    metrics["away"]["btts"] = both
    return metrics


def _venue_profile(entries: list[dict], overall: dict, cutoff: float,
                   keys: tuple[str, ...]) -> dict:
    """Shrink venue-only history toward the same team's all-venue profile."""
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
def _venue_supported(profile: dict, *, include_xg: bool = False) -> bool:
    count_keys = VENUE_COUNT_KEYS + (VENUE_XG_KEYS if include_xg else ())
    for key in count_keys:
        for kind in ("own", "opp"):
            if profile.get(f"{kind}_{key}_n", 0) < MIN_VENUE_HISTORY:
                return False
    return all(
        profile.get(f"own_{key}_n", 0) >= MIN_VENUE_HISTORY
        for key in VENUE_RATE_KEYS
    )


def _venue_features(profile: dict, *, include_xg: bool = False) -> list[float | None]:
    values: list[float | None] = []
    for key in VENUE_COUNT_KEYS:
        values.extend([profile.get(f"own_{key}"), profile.get(f"opp_{key}")])
    values.extend(profile.get(f"own_{key}") for key in VENUE_RATE_KEYS)
    if include_xg:
        for key in VENUE_XG_KEYS:
            values.extend([profile.get(f"own_{key}"), profile.get(f"opp_{key}")])
    return values


def _venue_side(row: dict, side: str) -> str:
    neutral = (row.get("context") or {}).get("is_neutral")
    if neutral is False:
        return side
    return "neutral" if neutral is True else "unknown"
def build_venue_panel(rows: list[dict]) -> list[dict]:
    target = "goals"
    profile_keys = (target,) + GOALS_DEEP + VENUE_RATE_KEYS + VENUE_XG_KEYS
    history: dict[str, list[dict]] = defaultdict(list)
    pools: dict[str, list[dict]] = defaultdict(list)
    ratings: dict[str, dict[str, float]] = defaultdict(dict)
    pending: dict[str, list[dict]] = defaultdict(list)
    panel: list[dict] = []

    for row in sorted(rows, key=lambda r: (r["kickoff_ts"], r["match_id"])):
        ts = float(row["kickoff_ts"])
        cutoff = ts - FEATURE_HORIZON_SECONDS
        comp = str(row["competition_id"])
        home_id, away_id = str(row["home_id"]), str(row["away_id"])

        pool = [e for e in pools[comp]
                if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        home_hist = [e for e in history[home_id]
                     if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        away_hist = [e for e in history[away_id]
                     if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        home_profile = _profile(home_hist, pool, cutoff, profile_keys)
        away_profile = _profile(away_hist, pool, cutoff, profile_keys)
        home_at_home = [e for e in home_hist if e.get("venue_side") == "home"]
        away_away = [e for e in away_hist if e.get("venue_side") == "away"]
        home_venue_profile = _venue_profile(
            home_at_home, home_profile, cutoff,
            VENUE_COUNT_KEYS + VENUE_RATE_KEYS + VENUE_XG_KEYS,
        )
        away_venue_profile = _venue_profile(
            away_away, away_profile, cutoff,
            VENUE_COUNT_KEYS + VENUE_RATE_KEYS + VENUE_XG_KEYS,
        )

        _apply_elo(ratings[comp], pending[comp], cutoff)
        elo = (
            ratings[comp].get(home_id, 1500.0)
            - ratings[comp].get(away_id, 1500.0)
        ) / 400.0
        prior = _comp_prior(pool, target, cutoff)
        metrics = row_metrics_with_events(row)
        y = [metrics["home"][target], metrics["away"][target]]

        deep_supported = (
            _support(home_profile, (target,), 5)
            and _support(away_profile, (target,), 5)
            and _support(home_profile, GOALS_DEEP, MIN_FEATURE_HISTORY)
            and _support(away_profile, GOALS_DEEP, MIN_FEATURE_HISTORY)
            and None not in y
        )
        current_non_neutral = (row.get("context") or {}).get("is_neutral") is False
        venue_supported = (
            deep_supported and current_non_neutral
            and _venue_supported(home_venue_profile)
            and _venue_supported(away_venue_profile)
        )
        venue_xg_supported = (
            venue_supported
            and _venue_supported(home_venue_profile, include_xg=True)
            and _venue_supported(away_venue_profile, include_xg=True)
        )

        home_deep = _vector(
            home_profile, away_profile, target, GOALS_DEEP, elo,
            _venue(row, "home"), prior,
        )
        away_deep = _vector(
            away_profile, home_profile, target, GOALS_DEEP, -elo,
            _venue(row, "away"), prior,
        )
        home_venue = home_deep + _venue_features(home_venue_profile)
        away_venue = away_deep + _venue_features(away_venue_profile)
        home_venue_xg = home_deep + _venue_features(
            home_venue_profile, include_xg=True)
        away_venue_xg = away_deep + _venue_features(
            away_venue_profile, include_xg=True)
        panel.append({
            "match_id": row["match_id"],
            "competition_id": comp,
            "date": row["kickoff"][:10],
            "kickoff_ts": ts,
            "cutoff_ts": cutoff,
            "y": y,
            "eligible_deep": deep_supported,
            "eligible_venue": venue_supported,
            "eligible_venue_xg": venue_xg_supported,
            "home": {
                "deep": home_deep,
                "venue": home_venue,
                "venue_xg": home_venue_xg,
            },
            "away": {
                "deep": away_deep,
                "venue": away_venue,
                "venue_xg": away_venue_xg,
            },
            "match_venue": home_venue + away_venue,
            "venue_support": {
                "home_matches": home_venue_profile.get("own_goals_n", 0),
                "away_matches": away_venue_profile.get("own_goals_n", 0),
                "home_xg_matches": home_venue_profile.get("own_xg_n", 0),
                "away_xg_matches": away_venue_profile.get("own_xg_n", 0),
            },
        })
        for side, other, team_id in (
            ("home", "away", home_id),
            ("away", "home", away_id),
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

        home_goals = metrics["home"]["goals"]
        away_goals = metrics["away"]["goals"]
        if home_goals is not None and away_goals is not None:
            pending[comp].append({
                "ts": ts,
                "home_id": home_id,
                "away_id": away_id,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "is_neutral": (row.get("context") or {}).get("is_neutral"),
            })
    return panel
