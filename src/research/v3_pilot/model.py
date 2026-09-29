"""Frozen V3 probability kernels. No market prices enter this module."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from .freeze import load_freeze

_FREEZE = load_freeze()
_G = _FREEZE["goals"]
_C = _FREEZE["corners"]

GOAL_LINES = (2.5, 3.5)
DC_HALF_LIFE = float(_G["half_life_days"])
DC_L2 = float(_G["ridge_l2"])
DC_RHO_BOUND = float(_G["rho_bound_abs"])
MIN_DC_TRAIN = int(_G["min_train_matches"])
MAX_GOALS = int(_G["score_matrix_max_goals"])
CAL_L2 = float(_G["calibration"]["ridge_l2"])
MIN_CAL_TARGETS = int(_G["calibration"]["min_calibration_targets"])
CORNER_K = float(_C["shrink_k"])

class InsufficientHistory(RuntimeError):
    pass

def canonical_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()

def _score(m: dict) -> tuple[int, int] | None:
    s = m.get("score") or {}
    h, a = s.get("home"), s.get("away")
    if h is None or a is None:
        return None
    try:
        return int(h), int(a)
    except (TypeError, ValueError):
        return None

def _valid_goal_rows(rows: Iterable[dict], before: float | None = None) -> list[dict]:
    out = []
    for m in rows:
        if before is not None and float(m.get("ts", 0)) >= before:
            continue
        if _score(m) is None:
            continue
        if not m.get("home_id") or not m.get("away_id") or not m.get("ts"):
            continue
        out.append(m)
    return sorted(out, key=lambda x: (float(x["ts"]), str(x.get("match_id", ""))))

def _dc_tau(x: np.ndarray, y: np.ndarray, lh: np.ndarray, la: np.ndarray, rho: float) -> np.ndarray:
    tau = np.ones(len(x), dtype=float)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    tau[m00] = 1 - lh[m00] * la[m00] * rho
    tau[m01] = 1 + lh[m01] * rho
    tau[m10] = 1 + la[m10] * rho
    tau[m11] = 1 - rho
    return tau

def fit_dc(rows: Iterable[dict], ref_ts: float) -> dict:
    train = _valid_goal_rows(rows, before=ref_ts)
    if len(train) < MIN_DC_TRAIN:
        raise InsufficientHistory(f"DC needs {MIN_DC_TRAIN} matches; found {len(train)}")
    teams = sorted({str(m["home_id"]) for m in train} | {str(m["away_id"]) for m in train})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([idx[str(m["home_id"])] for m in train], dtype=int)
    ai = np.array([idx[str(m["away_id"])] for m in train], dtype=int)
    sc = [_score(m) for m in train]
    gh = np.array([s[0] for s in sc], dtype=float)
    ga = np.array([s[1] for s in sc], dtype=float)
    ages = np.array([max((ref_ts - float(m["ts"])) / 86400.0, 0.0) for m in train])
    weights = 0.5 ** (ages / DC_HALF_LIFE)
    const = -gammaln(gh + 1) - gammaln(ga + 1)

    x0 = np.zeros(2 + 2 * n + 1)
    x0[0] = math.log(max(float(np.mean(np.r_[gh, ga])), 0.2))
    x0[1] = 0.12

    def objective(par: np.ndarray) -> float:
        mu, home_adv = par[0], par[1]
        att = par[2:2+n].copy()
        deff = par[2+n:2+2*n].copy()
        att -= att.mean()
        deff -= deff.mean()
        rho = DC_RHO_BOUND * np.tanh(par[-1])
        lgh = np.clip(mu + home_adv + att[hi] + deff[ai], math.log(0.05), math.log(6))
        lga = np.clip(mu + att[ai] + deff[hi], math.log(0.05), math.log(6))
        lh, la = np.exp(lgh), np.exp(lga)
        tau = _dc_tau(gh, ga, lh, la, float(rho))
        if np.any(tau <= 1e-8):
            return 1e12
        lp = gh*lgh - lh + ga*lga - la + const + np.log(tau)
        penalty = DC_L2 * (np.sum(att*att) + np.sum(deff*deff))
        return float(-np.sum(weights * lp) + penalty)

    res = minimize(objective, x0, method="L-BFGS-B",
                   options={"maxiter": 160, "ftol": 1e-8, "maxls": 25})
    par = res.x
    mu, home_adv = float(par[0]), float(par[1])
    att = par[2:2+n].copy()
    deff = par[2+n:2+2*n].copy()
    att -= att.mean()
    deff -= deff.mean()
    rho = float(DC_RHO_BOUND * math.tanh(float(par[-1])))
    model = {
        "mu": mu, "home_adv": home_adv, "rho": rho,
        "attack": {t: float(att[idx[t]]) for t in teams},
        "defense": {t: float(deff[idx[t]]) for t in teams},
        "optimizer_success": bool(res.success),
        "n_train": len(train),
        "training_data_hash": canonical_hash([
            [m.get("match_id"), m["ts"], m["home_id"], m["away_id"], *_score(m)]
            for m in train
        ]),
    }
    model["model_artifact_hash"] = canonical_hash(model)
    return model

def _dc_lambdas(model: dict, home_id: str, away_id: str) -> tuple[float, float]:
    ah = model["attack"].get(str(home_id), 0.0)
    aa = model["attack"].get(str(away_id), 0.0)
    dh = model["defense"].get(str(home_id), 0.0)
    da = model["defense"].get(str(away_id), 0.0)
    lh = math.exp(float(np.clip(model["mu"] + model["home_adv"] + ah + da,
                                math.log(0.05), math.log(6))))
    la = math.exp(float(np.clip(model["mu"] + aa + dh,
                                math.log(0.05), math.log(6))))
    return lh, la

def _dc_matrix(lh: float, la: float, rho: float) -> np.ndarray:
    ph = np.array([math.exp(-lh) * lh**i / math.factorial(i) for i in range(MAX_GOALS + 1)])
    pa = np.array([math.exp(-la) * la**j / math.factorial(j) for j in range(MAX_GOALS + 1)])
    P = np.outer(ph, pa)
    for i, j in ((0,0), (0,1), (1,0), (1,1)):
        if i <= MAX_GOALS and j <= MAX_GOALS:
            if i == 0 and j == 0:
                tau = 1 - lh*la*rho
            elif i == 0 and j == 1:
                tau = 1 + lh*rho
            elif i == 1 and j == 0:
                tau = 1 + la*rho
            else:
                tau = 1 - rho
            P[i, j] *= tau
    total = float(P.sum())
    if total <= 0:
        raise RuntimeError("invalid Dixon-Coles probability matrix")
    return P / total

def _p_total_over(P: np.ndarray, line: float) -> float:
    return float(sum(P[i, j] for i in range(P.shape[0]) for j in range(P.shape[1])
                     if i + j > line))

def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))

def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(min(float(x), 35), -35)))

def _fit_platt(raw_probs: list[float], outcomes: list[int]) -> dict:
    if len(raw_probs) < MIN_CAL_TARGETS:
        raise InsufficientHistory(
            f"calibration needs {MIN_CAL_TARGETS} targets; found {len(raw_probs)}"
        )
    X = np.array([_logit(p) for p in raw_probs], dtype=float)
    y = np.array(outcomes, dtype=float)
    Z = np.column_stack([np.ones(len(X)), X])
    def obj(b: np.ndarray) -> float:
        z = np.clip(Z @ b, -35, 35)
        p = 1 / (1 + np.exp(-z))
        ll = -np.sum(y*np.log(p + 1e-12) + (1-y)*np.log(1-p + 1e-12))
        return float(ll + CAL_L2 * np.sum(b[1:]**2))
    res = minimize(obj, np.zeros(2), method="L-BFGS-B", options={"maxiter": 300})
    art = {"intercept": float(res.x[0]), "slope": float(res.x[1]),
           "n": len(raw_probs), "optimizer_success": bool(res.success)}
    art["calibrator_hash"] = canonical_hash(art)
    return art

def apply_platt(cal: dict, p: float) -> float:
    return _sigmoid(float(cal["intercept"]) + float(cal["slope"]) * _logit(p))

def select_calibration_season(history: Iterable[dict], target_season_id: str) -> str:
    by_season: dict[str, list[float]] = defaultdict(list)
    for m in _valid_goal_rows(history):
        sid = str(m.get("season_id") or "")
        if not sid or sid == str(target_season_id):
            continue
        by_season[sid].append(float(m["ts"]))
    if not by_season:
        raise InsufficientHistory("no prior season available for calibration")
    return max(by_season, key=lambda s: max(by_season[s]))

def fit_goal_calibrators(history: Iterable[dict], target_season_id: str) -> dict:
    rows = _valid_goal_rows(history)
    cal_sid = select_calibration_season(rows, target_season_id)
    cal_rows = [m for m in rows if str(m.get("season_id")) == cal_sid]
    raw: dict[float, list[float]] = {line: [] for line in GOAL_LINES}
    y: dict[float, list[int]] = {line: [] for line in GOAL_LINES}
    by_ts: dict[float, list[dict]] = defaultdict(list)
    for m in cal_rows:
        by_ts[float(m["ts"])].append(m)
    for ts in sorted(by_ts):
        train = [m for m in rows if float(m["ts"]) < ts]
        if len(train) < MIN_DC_TRAIN:
            continue
        model = fit_dc(train, ts)
        for m in by_ts[ts]:
            lh, la = _dc_lambdas(model, str(m["home_id"]), str(m["away_id"]))
            P = _dc_matrix(lh, la, float(model["rho"]))
            total = sum(_score(m))
            for line in GOAL_LINES:
                raw[line].append(_p_total_over(P, line))
                y[line].append(int(total > line))
    calibrators = {str(line): _fit_platt(raw[line], y[line]) for line in GOAL_LINES}
    artifact = {"calibration_season_id": cal_sid, "calibrators": calibrators}
    artifact["artifact_hash"] = canonical_hash(artifact)
    return artifact

def predict_goals(history: Iterable[dict], target: dict, calibrator_artifact: dict) -> dict:
    ts = float(target["ts"])
    model = fit_dc(history, ts)
    lh, la = _dc_lambdas(model, str(target["home_id"]), str(target["away_id"]))
    P = _dc_matrix(lh, la, float(model["rho"]))
    probs = {}
    for line in GOAL_LINES:
        raw = _p_total_over(P, line)
        cal = calibrator_artifact["calibrators"][str(line)]
        probs[str(line)] = {"p_over_raw": raw, "p_over": apply_platt(cal, raw)}
    out = {
        "version": _G["version"], "lambda_home": lh, "lambda_away": la,
        "rho": model["rho"], "probabilities": probs,
        "training_data_hash": model["training_data_hash"],
        "dc_artifact_hash": model["model_artifact_hash"],
        "calibrator_hash": calibrator_artifact["artifact_hash"],
        "n_train": model["n_train"],
    }
    out["distribution_hash"] = canonical_hash(out)
    return out

def _corner_pair(row: dict, role: str) -> tuple[float, float] | None:
    try:
        h, a = float(row["corners_home"]), float(row["corners_away"])
    except (KeyError, TypeError, ValueError):
        return None
    if h < 0 or a < 0:
        return None
    return (h, a) if role == "home" else (a, h)

def _team_corner_rate(rows: Iterable[dict], team_id: str, before: float, n: int,
                      role_filter: str | None, min_n: int) -> dict | None:
    vals = []
    for m in sorted(rows, key=lambda x: float(x["ts"])):
        if float(m["ts"]) >= before:
            break
        if str(m.get("home_id")) == str(team_id):
            role = "home"
        elif str(m.get("away_id")) == str(team_id):
            role = "away"
        else:
            continue
        if role_filter and role != role_filter:
            continue
        z = _corner_pair(m, role)
        if z is not None:
            vals.append(z)
    vals = vals[-n:]
    if len(vals) < min_n:
        return None
    return {"for": float(np.mean([v[0] for v in vals])),
            "against": float(np.mean([v[1] for v in vals])), "n": len(vals)}

def _corner_baseline(rows: Iterable[dict], before: float, role: str | None) -> tuple[float, int] | None:
    vals = []
    for m in rows:
        if float(m.get("ts", 0)) >= before:
            continue
        roles = [role] if role else ["home", "away"]
        for rr in roles:
            z = _corner_pair(m, rr)
            if z is not None:
                vals.append(z[0])
    if not vals:
        return None
    return float(np.mean(vals)), len(vals)

def _shrink(x: float, n: int, baseline: float) -> float:
    return (n*x + CORNER_K*baseline) / (n + CORNER_K)

def _corner_side_lambda(comp_rows: list[dict], global_rows: list[dict], target: dict,
                        team_id: str, opp_id: str, role: str) -> dict:
    before = float(target["ts"])
    opp_role = "away" if role == "home" else "home"
    b_all = _corner_baseline(comp_rows, before, None)
    b_role = _corner_baseline(comp_rows, before, role)
    if b_all is None or b_all[1] < 10:
        b_all = _corner_baseline(global_rows, before, None)
    if b_role is None or b_role[1] < 10:
        b_role = _corner_baseline(global_rows, before, role)
    if b_all is None or b_role is None:
        raise InsufficientHistory("no provider-native corner baseline")
    estimates: dict[str, float] = {}
    details: dict[str, Any] = {}
    specs = [
        ("long5", 5, 5, None, None, b_all[0]),
        ("recent3", 3, 3, None, None, b_all[0]),
        ("venue3", 3, 2, role, opp_role, b_role[0]),
    ]
    for name, n, min_n, rf, of, baseline in specs:
        tr = _team_corner_rate(comp_rows, team_id, before, n, rf, min_n)
        op = _team_corner_rate(comp_rows, opp_id, before, n, of, min_n)
        if tr and op:
            tf = _shrink(tr["for"], tr["n"], baseline)
            oa = _shrink(op["against"], op["n"], baseline)
            estimates[name] = math.sqrt(max(tf, 1e-9) * max(oa, 1e-9))
            details[name] = {"team": tr, "opponent": op, "baseline": baseline,
                             "shrunk_team_for": tf, "shrunk_opp_against": oa}
    if len(estimates) < int(_C["min_valid_estimators_per_side"]):
        raise InsufficientHistory("fewer than two valid corner estimators")
    return {"lambda": float(np.median(list(estimates.values()))),
            "estimators": estimates, "details": details}

def predict_corners(comp_rows: list[dict], global_rows: list[dict], target: dict) -> dict:
    home = _corner_side_lambda(comp_rows, global_rows, target,
                               str(target["home_id"]), str(target["away_id"]), "home")
    away = _corner_side_lambda(comp_rows, global_rows, target,
                               str(target["away_id"]), str(target["home_id"]), "away")
    out = {
        "version": _C["version"], "lambda_home": home["lambda"],
        "lambda_away": away["lambda"], "lambda_total": home["lambda"] + away["lambda"],
        "home": home, "away": away,
        "corner_history_hash": canonical_hash([
            [m.get("match_id"), m.get("ts"), m.get("home_id"), m.get("away_id"),
             m.get("corners_home"), m.get("corners_away")]
            for m in sorted(comp_rows, key=lambda x: (float(x["ts"]), str(x.get("match_id",""))))
            if float(m.get("ts", 0)) < float(target["ts"])
        ]),
    }
    out["distribution_hash"] = canonical_hash(out)
    return out

def poisson_over(line: float, lam: float) -> float:
    k = math.floor(float(line))
    cdf = sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k + 1))
    return float(1 - cdf)
