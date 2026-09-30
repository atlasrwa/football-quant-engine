"""Bounded V3.2 offline feature and count-model comparison core."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln, expit, logit
from scipy.stats import nbinom, poisson
from sklearn.linear_model import PoissonRegressor

HALF_LIFE_DAYS = 365.0
SHRINK_MATCHES = 5.0
FEATURE_HORIZON_SECONDS = 24 * 3600
COMPLETION_BUFFER_SECONDS = 4 * 3600
MIN_TEAM_TARGET_HISTORY = 5
MIN_FEATURE_HISTORY = 3
RIDGE_ALPHA = 1.0
STAT_PATHS = {
    "shots": "overview.total_shots",
    "sot": "overview.shots_on_target",
    "box": "shots.shots_inside_box",
    "big": "overview.big_chances",
    "blocked": "shots.blocked_shots",
    "crosses": "passes.accurate_crosses",
    "entries": "passes.final_third_entries",
    "possession": "overview.ball_possession",
    "saves": "goalkeeping.saves",
    "clearances": "defending.clearances",
    "corners": "overview.corner_kicks",
    "fouls": "overview.fouls",
    "tackles": "defending.tackles",
    "interceptions": "defending.interceptions",
    "duels_won_percentage": "duels.duels_won_percentage",
}
GOALS_RICH = ("shots","sot","box","big","blocked","crosses","entries",
              "possession","saves","clearances","corners")
CARDS_RICH = ("fouls","tackles","interceptions","possession","duels_won_percentage")

class UnsupportedFeatures(RuntimeError):
    pass
def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out >= 0 else None

def _period_safe(row: dict, side: str) -> bool:
    target = (row.get("targets") or {}).get(f"corners.{side}") or {}
    return target.get("period_status") == "NO_EXTRA_TIME_RECORDED"

def _metric(row: dict, key: str, side: str) -> float | None:
    if not _period_safe(row, side):
        return None
    path = STAT_PATHS[key]
    bad = {(x.get("path"), x.get("side")) for x in row.get("period_checks", [])}
    if (path, side) in bad:
        return None
    return number((row.get("raw_stats") or {}).get(f"{path}.all.{side}"))

def row_metrics(row: dict) -> dict[str, dict[str, float | None]]:
    out = {"home": {}, "away": {}}
    for side in out:
        out[side]["goals"] = number(row["targets"][f"goals.{side}"]["value"])
        out[side]["yellow"] = number(row["targets"][f"bookings.{side}"]["value"])
        for key in STAT_PATHS:
            out[side][key] = _metric(row, key, side)
    return out
def _weighted(entries: list[dict], key: str, kind: str, cutoff: float):
    values = []
    for entry in entries:
        value = entry[kind].get(key)
        if value is None:
            continue
        weight = 2 ** (-(cutoff - entry["ts"]) / 86400.0 / HALF_LIFE_DAYS)
        values.append((value, weight))
    return (sum(v*w for v,w in values), sum(w for _,w in values), len(values))

def _profile(entries: list[dict], pool: list[dict], cutoff: float, keys: tuple[str,...]):
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

def _venue(row: dict, side: str) -> float | None:
    neutral = (row.get("context") or {}).get("is_neutral")
    if neutral is None:
        return None
    if bool(neutral):
        return 0.0
    return 1.0 if side == "home" else -1.0
def _vector(p: dict, q: dict, side: str, target: str,
            rich_keys: tuple[str,...], elo_delta: float, rich: bool):
    base = [p[f"own_{target}"], p[f"opp_{target}"],
            q[f"own_{target}"], q[f"opp_{target}"], elo_delta,]
    if not rich:
        return base
    values = list(base)
    for key in rich_keys:
        values.extend([p[f"own_{key}"], p[f"opp_{key}"],
                       q[f"own_{key}"], q[f"opp_{key}"]])
    return values

def _support(profile: dict, keys: tuple[str,...], minimum: int) -> bool:
    return all(profile.get(f"{kind}_{key}_n", 0) >= minimum
               for key in keys for kind in ("own", "opp"))

def _elo_expected(home: float, away: float, home_bonus: float) -> float:
    return 1.0 / (1.0 + 10 ** (-(home + home_bonus - away) / 400.0))

def build_panel(rows: list[dict], family: str) -> list[dict]:
    if family not in {"goals", "cards"}:
        raise ValueError(f"unknown family {family}")
    target = "goals" if family == "goals" else "yellow"
    rich_keys = GOALS_RICH if family == "goals" else CARDS_RICH
    keys = (target,) + rich_keys
    history: dict[str,list[dict]] = defaultdict(list)
    pools: dict[str,list[dict]] = defaultdict(list)
    ratings: dict[str,dict[str,float]] = defaultdict(dict)
    panel = []
    for row in sorted(rows, key=lambda r: (r["kickoff_ts"], r["match_id"])):
        ts = float(row["kickoff_ts"])
        cutoff = ts - FEATURE_HORIZON_SECONDS
        comp = str(row["competition_id"])
        home_id, away_id = str(row["home_id"]), str(row["away_id"])
        pool = [e for e in pools[comp] if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        home_hist = [e for e in history[home_id] if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        away_hist = [e for e in history[away_id] if e["ts"] + COMPLETION_BUFFER_SECONDS < cutoff]
        hp = _profile(home_hist, pool, cutoff, keys)
        ap = _profile(away_hist, pool, cutoff, keys)
        hr = ratings[comp].get(home_id, 1500.0)
        ar = ratings[comp].get(away_id, 1500.0)
        elo_delta = (hr - ar) / 400.0
        metrics = row_metrics(row)
        y = [metrics["home"][target], metrics["away"][target]]
        core = _support(hp, (target,), MIN_TEAM_TARGET_HISTORY) and _support(
            ap, (target,), MIN_TEAM_TARGET_HISTORY)
        rich_support = core and _support(hp, rich_keys, MIN_FEATURE_HISTORY) and _support(
            ap, rich_keys, MIN_FEATURE_HISTORY)
        panel.append({
            "match_id": row["match_id"], "competition_id": comp, "date": row["kickoff"][:10],
            "kickoff_ts": ts, "cutoff_ts": cutoff, "y": y,
            "eligible_core": core and None not in y,
            "eligible_rich": rich_support and None not in y,
            "home": {"base": _vector(hp, ap, "home", target, rich_keys, elo_delta, False),
                     "rich": _vector(hp, ap, "home", target, rich_keys, elo_delta, True)},
            "away": {"base": _vector(ap, hp, "away", target, rich_keys, -elo_delta, False),
                     "rich": _vector(ap, hp, "away", target, rich_keys, -elo_delta, True)},
            "support": {"home_target_n": hp.get(f"own_{target}_n", 0),
                        "away_target_n": ap.get(f"own_{target}_n", 0),
                        "rich_supported": rich_support},
        })
        for side, other, team_id in (("home","away",home_id),("away","home",away_id)):
            entry = {"match_id": row["match_id"], "ts": ts,
                     "own": metrics[side], "opp": metrics[other]}
            history[team_id].append(entry)
            pools[comp].append(entry)
        gh = metrics["home"]["goals"]; ga = metrics["away"]["goals"]
        if gh is not None and ga is not None:
            bonus = 0.0 if (row.get("context") or {}).get("is_neutral") else 50.0
            exp_home = _elo_expected(hr, ar, bonus)
            actual = 1.0 if gh > ga else 0.0 if gh < ga else 0.5
            delta = 20.0 * (actual - exp_home)
            ratings[comp][home_id] = hr + delta
            ratings[comp][away_id] = ar - delta
    return panel

class CountRegressor:
    def __init__(self, x, y):
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or x.shape[0] == 0:
            raise UnsupportedFeatures("empty design matrix")
        finite = np.isfinite(x)
        if np.any(finite.sum(axis=0) == 0):
            bad = np.where(finite.sum(axis=0) == 0)[0].tolist()
            raise UnsupportedFeatures(f"all-missing feature columns {bad}")
        self.median = np.array([np.median(c[np.isfinite(c)]) for c in x.T])
        z = self._impute(x)
        self.mean = z.mean(axis=0)
        self.std = z.std(axis=0)
        self.std[self.std == 0] = 1.0
        self.model = PoissonRegressor(alpha=RIDGE_ALPHA, max_iter=2500, tol=1e-8)
        self.model.fit((z - self.mean) / self.std, np.asarray(y, dtype=float))

    def _impute(self, x):
        x = np.asarray(x, dtype=float)
        missing = ~np.isfinite(x)
        filled = np.where(missing, self.median, x)
        return np.column_stack((filled, missing.astype(float)))

    def predict(self, x):
        z = self._impute(x)
        return np.maximum(self.model.predict((z - self.mean) / self.std), 1e-8)

def design(rows: list[dict], arm: str):
    key = "base" if arm == "BASE_POISSON" else "rich"
    return [row[side][key] for row in rows for side in ("home","away")]
def calibrate_scales(means: np.ndarray, outcomes: np.ndarray, ridge: float = 0.05):
    means = np.asarray(means, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    def objective(theta):
        mu = means * np.exp(theta)[None, :]
        nll = np.mean(np.sum(mu - outcomes * np.log(mu) + gammaln(outcomes + 1), axis=1))
        return float(nll + ridge * np.sum(theta * theta))
    fit = minimize(objective, np.zeros(2), method="L-BFGS-B", bounds=[(-1.5,1.5)]*2)
    if not fit.success or not np.isfinite(fit.x).all():
        raise UnsupportedFeatures("calibration convergence failure")
    return np.exp(fit.x)

def estimate_nb_dispersion(y: np.ndarray, mu: np.ndarray) -> float:
    y = np.asarray(y, dtype=float); mu = np.asarray(mu, dtype=float)
    numerator = np.sum((y - mu) ** 2 - y)
    denominator = np.sum(mu ** 2)
    return float(np.clip(numerator / denominator if denominator > 0 else 0.0, 1e-6, 5.0))

def fit_dc_rho(means: np.ndarray, outcomes: np.ndarray) -> float:
    means=np.asarray(means,float); outcomes=np.asarray(outcomes,int)
    def objective(rho):
        loss=0.0
        for (mh,ma),(h,a) in zip(means,outcomes):
            tau=1.0
            if h==0 and a==0: tau=1-mh*ma*rho
            elif h==0 and a==1: tau=1+mh*rho
            elif h==1 and a==0: tau=1+ma*rho
            elif h==1 and a==1: tau=1-rho
            if tau <= 1e-10: return 1e12
            loss -= math.log(tau)
        return loss
    fit=minimize_scalar(objective,bounds=(-0.15,0.15),method="bounded")
    return float(np.clip(fit.x,-0.15,0.15))

def _side_pmf(mean: float, kind: str, dispersion: float, max_count: int):
    k=np.arange(max_count+1)
    if kind=="nb":
        r=1.0/max(dispersion,1e-8); p=r/(r+mean)
        return nbinom.pmf(k,r,p)
    return poisson.pmf(k,mean)

def joint_distribution(home: float, away: float, kind: str,
                       dispersion: float = 1e-6, rho: float = 0.0,
                       max_count: int = 40):
    hp=_side_pmf(home,"nb" if kind=="nb" else "poisson",dispersion,max_count)
    ap=_side_pmf(away,"nb" if kind=="nb" else "poisson",dispersion,max_count)
    joint=np.outer(hp,ap)
    if kind=="dc":
        joint[0,0]*=1-home*away*rho
        joint[0,1]*=1+home*rho
        joint[1,0]*=1+away*rho
        joint[1,1]*=1-rho
    total=float(joint.sum())
    if total <= 0 or not math.isfinite(total):
        raise UnsupportedFeatures("invalid joint distribution")
    return joint/total

def event_probabilities(joint: np.ndarray, family: str):
    h=np.arange(joint.shape[0])[:,None]
    a=np.arange(joint.shape[1])[None,:]
    total=h+a
    if family=="goals":
        return {
            "home>1.5": float(joint[h.repeat(joint.shape[1],axis=1)>1].sum()),
            "away>1.5": float(joint[a.repeat(joint.shape[0],axis=0)>1].sum()),
            "total>2.5": float(joint[total>2].sum()),
            "total>3.5": float(joint[total>3].sum()),
            "BTTS": float(joint[(h>0)&(a>0)].sum()),
        }
    return {
        "home_yellow>1.5": float(joint[h.repeat(joint.shape[1],axis=1)>1].sum()),
        "away_yellow>1.5": float(joint[a.repeat(joint.shape[0],axis=0)>1].sum()),
        "total_yellow>3.5": float(joint[total>3].sum()),
    }

def event_outcomes(y: list[float], family: str):
    home,away=map(int,y)
    if family=="goals":
        return {"home>1.5":int(home>1),"away>1.5":int(away>1),
                "total>2.5":int(home+away>2),"total>3.5":int(home+away>3),
                "BTTS":int(home>0 and away>0)}
    return {"home_yellow>1.5":int(home>1),"away_yellow>1.5":int(away>1),
            "total_yellow>3.5":int(home+away>3)}
def binary_metrics(predictions: list[dict]):
    if not predictions:
        return {"n":0}
    p=np.clip(np.array([r["p"] for r in predictions],float),1e-8,1-1e-8)
    y=np.array([r["event"] for r in predictions],float)
    ll=float(np.mean(-(y*np.log(p)+(1-y)*np.log1p(-p))))
    brier=float(np.mean((p-y)**2))
    diagnostic=None
    if len(set(y.tolist()))==2:
        z=logit(p)
        def objective(beta):
            q=expit(beta[0]+beta[1]*z)
            return float(np.mean(-(y*np.log(np.clip(q,1e-10,1))+
                                   (1-y)*np.log(np.clip(1-q,1e-10,1)))))
        fit=minimize(objective,[0.0,1.0],method="BFGS")
        if fit.success and np.isfinite(fit.x).all():
            diagnostic={"intercept":float(fit.x[0]),"slope":float(fit.x[1])}
    return {"n":len(predictions),"log_loss":ll,"brier":brier,
            "calibration_diagnostic":diagnostic}

def paired_gain(base: list[dict], candidate: list[dict]):
    lookup={(r["match_id"],r["target"],r["fold"]):r for r in candidate}
    diffs=[]
    for row in base:
        other=lookup.get((row["match_id"],row["target"],row["fold"]))
        if other is not None:
            diffs.append(row["loss"]-other["loss"])
    return {"n":len(diffs),"mean_log_loss_improvement":float(np.mean(diffs)) if diffs else None}
