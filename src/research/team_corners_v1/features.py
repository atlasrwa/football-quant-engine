from __future__ import annotations
import math
from collections import defaultdict
from typing import Any, Iterable

METRICS = {
    "shots": "overview.total_shots.all",
    "sot": "overview.shots_on_target.all",
    "crosses": "passes.accurate_crosses.all",
    "possession": "overview.ball_possession.all",
    "final3": "passes.final_third_entries.all",
}
SCALES = {"shots": 12.0, "sot": 4.0, "crosses": 4.0, "possession": 50.0, "final3": 50.0}
RIDGE_FEATURE_NAMES = (
    "intercept", "log_structural", "log_decay", "structural_minus_decay",
    "own_shots", "own_sot", "own_crosses", "own_possession", "own_final3",
    "opp_shots_against", "opp_sot_against", "opp_crosses_against",
    "opp_possession_against", "opp_final3_against", "is_home",
)

def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None
def _raw_side(raw: dict, base: str, side: str) -> float | None:
    return _num(raw.get(f"{base}.{side}"))

def evidence_matches(rows: Iterable[dict]) -> list[dict]:
    out = []
    for o in rows:
        h = _num((((o.get("targets") or {}).get("corners.home") or {}).get("value")))
        a = _num((((o.get("targets") or {}).get("corners.away") or {}).get("value")))
        ts = _num(o.get("kickoff_ts"))
        if h is None or a is None or ts is None:
            continue
        raw = o.get("raw_stats") or {}
        out.append({
            "match_id": str(o.get("match_id") or ""), "ts": ts,
            "competition_id": str(o.get("competition_id") or ""),
            "home_id": str(o.get("home_id") or ""), "away_id": str(o.get("away_id") or ""),
            "home_count": h, "away_count": a, "raw": raw,
        })
    return sorted(out, key=lambda r: (r["ts"], r["match_id"]))

def _side_obs(match: dict, role: str) -> dict:
    own = "home" if role == "home" else "away"
    opp = "away" if own == "home" else "home"
    own_count = match[f"{own}_count"]
    opp_count = match[f"{opp}_count"]
    raw = match["raw"]
    obs = {
        "ts": match["ts"], "role": role,
        "count_for": own_count, "count_against": opp_count,
    }
    for name, base in METRICS.items():
        obs[f"{name}_for"] = _raw_side(raw, base, own)
        obs[f"{name}_against"] = _raw_side(raw, base, opp)
    return obs

def _vals(hist: list[dict], key: str, n: int, role: str | None = None) -> list[float]:
    rows = [r for r in hist if role is None or r["role"] == role]
    vals = [_num(r.get(key)) for r in rows[-n:]]
    return [v for v in vals if v is not None]

def _mean(hist: list[dict], key: str, n: int, role: str | None = None) -> float | None:
    v = _vals(hist, key, n, role)
    return sum(v) / len(v) if v else None

def _ewm(hist: list[dict], key: str, n: int = 12, half_life: float = 4.0) -> tuple[float, int] | None:
    vals = _vals(hist, key, n)
    if not vals:
        return None
    weights = [0.5 ** ((len(vals) - 1 - i) / half_life) for i in range(len(vals))]
    return sum(v*w for v, w in zip(vals, weights)) / sum(weights), len(vals)

def _shrink(value: float, n: int, baseline: float, k: float) -> float:
    return (n * value + k * baseline) / (n + k)
def _baseline(comp_counts: dict, global_counts: dict, comp: str, role: str) -> float | None:
    local = comp_counts.get((comp, role), [])
    if len(local) >= 20:
        return sum(local) / len(local)
    glob = global_counts.get(role, [])
    if len(glob) >= 20:
        return sum(glob) / len(glob)
    return None

def _scaled_mean(hist: list[dict], key: str, scale: float, n: int = 8) -> float:
    m = _mean(hist, key, n)
    return 0.0 if m is None else (m / scale - 1.0)

def side_features(team_hist: dict[str, list[dict]], comp_counts: dict, global_counts: dict,
                  *, comp: str, team: str, opp: str, role: str) -> dict | None:
    th = team_hist.get(team, [])
    oh = team_hist.get(opp, [])
    if len(th) < 4 or len(oh) < 4:
        return None
    baseline = _baseline(comp_counts, global_counts, comp, role)
    if baseline is None or baseline <= 0:
        return None
    opp_role = "away" if role == "home" else "home"
    tf = _mean(th, "count_for", 12)
    oa = _mean(oh, "count_against", 12)
    if tf is None or oa is None:
        return None
    tf_s = _shrink(tf, min(len(th), 12), baseline, 6.0)
    oa_s = _shrink(oa, min(len(oh), 12), baseline, 6.0)
    structural_long = math.sqrt(max(tf_s, 1e-6) * max(oa_s, 1e-6))
    tv = _mean(th, "count_for", 6, role)
    ov = _mean(oh, "count_against", 6, opp_role)
    tvn = len(_vals(th, "count_for", 6, role))
    ovn = len(_vals(oh, "count_against", 6, opp_role))
    if tv is not None and ov is not None and tvn >= 2 and ovn >= 2:
        tv_s = _shrink(tv, tvn, baseline, 8.0)
        ov_s = _shrink(ov, ovn, baseline, 8.0)
        structural_venue = math.sqrt(max(tv_s, 1e-6) * max(ov_s, 1e-6))
        structural = 0.70 * structural_long + 0.30 * structural_venue
    else:
        structural = structural_long

    te = _ewm(th, "count_for")
    oe = _ewm(oh, "count_against")
    if te is None or oe is None:
        return None
    te_s = _shrink(te[0], te[1], baseline, 3.0)
    oe_s = _shrink(oe[0], oe[1], baseline, 3.0)
    decay = math.sqrt(max(te_s, 1e-6) * max(oe_s, 1e-6))
    rich = [
        1.0,
        math.log(max(structural, 1e-6)),
        math.log(max(decay, 1e-6)),
        structural - decay,
    ]
    for key in ("shots", "sot", "crosses", "possession", "final3"):
        rich.append(_scaled_mean(th, f"{key}_for", SCALES[key]))
    for key in ("shots", "sot", "crosses", "possession", "final3"):
        rich.append(_scaled_mean(oh, f"{key}_against", SCALES[key]))
    rich.append(1.0 if role == "home" else 0.0)
    return {
        "structural_mu": float(structural), "decay_mu": float(decay),
        "ridge_x": rich, "baseline": float(baseline),
        "history_n_team": len(th), "history_n_opp": len(oh),
    }

def _update_state(match: dict, team_hist: dict, comp_counts: dict, global_counts: dict) -> None:
    for role, team in (("home", match["home_id"]), ("away", match["away_id"])):
        obs = _side_obs(match, role)
        team_hist[team].append(obs)
        comp_counts[(match["competition_id"], role)].append(obs["count_for"])
        global_counts[role].append(obs["count_for"])
def build_side_dataset(matches: list[dict]) -> list[dict]:
    team_hist: dict[str, list[dict]] = defaultdict(list)
    comp_counts: dict[tuple[str, str], list[float]] = defaultdict(list)
    global_counts: dict[str, list[float]] = defaultdict(list)
    out: list[dict] = []
    i = 0
    while i < len(matches):
        ts = matches[i]["ts"]
        j = i
        while j < len(matches) and matches[j]["ts"] == ts:
            j += 1
        block = matches[i:j]
        for m in block:
            for role, team, opp, y in (
                ("home", m["home_id"], m["away_id"], m["home_count"]),
                ("away", m["away_id"], m["home_id"], m["away_count"]),
            ):
                f = side_features(team_hist, comp_counts, global_counts,
                                  comp=m["competition_id"], team=team, opp=opp, role=role)
                if f is not None:
                    out.append({
                        "match_id": m["match_id"], "ts": m["ts"], "competition_id": m["competition_id"],
                        "role": role, "team_id": team, "opp_id": opp, "y": float(y), **f,
                    })
        for m in block:
            _update_state(m, team_hist, comp_counts, global_counts)
        i = j
    return out
def prospective_features(matches: list[dict], fixture: dict, role: str) -> dict | None:
    cutoff = float(fixture["ts"])
    team_hist: dict[str, list[dict]] = defaultdict(list)
    comp_counts: dict[tuple[str, str], list[float]] = defaultdict(list)
    global_counts: dict[str, list[float]] = defaultdict(list)
    for m in matches:
        if float(m["ts"]) >= cutoff:
            break
        _update_state(m, team_hist, comp_counts, global_counts)
    if role == "home":
        team, opp = str(fixture["home_id"]), str(fixture["away_id"])
    else:
        team, opp = str(fixture["away_id"]), str(fixture["home_id"])
    return side_features(team_hist, comp_counts, global_counts,
                         comp=str(fixture["competition_id"]), team=team, opp=opp, role=role)
