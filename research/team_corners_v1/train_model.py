#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.research.team_corners_v1.config import EVIDENCE, MODEL_FREEZE, PRIMARY_LINES, SPEC
from src.research.team_corners_v1.features import (
    RIDGE_FEATURE_NAMES, build_side_dataset, evidence_matches,
)

RIDGE_LAMBDAS = (0.1, 1.0, 5.0, 20.0)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()
def canonical_hash(obj: dict) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()

def fit_ridge(rows: list[dict], lam: float) -> np.ndarray:
    X = np.asarray([r["ridge_x"] for r in rows], dtype=float)
    y = np.log(np.asarray([r["y"] for r in rows], dtype=float) + 0.5)
    penalty = np.eye(X.shape[1]) * float(lam)
    penalty[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + penalty, X.T @ y)

def ridge_mu(row: dict, beta: np.ndarray) -> float:
    z = float(np.dot(np.asarray(row["ridge_x"], dtype=float), beta))
    return max(math.exp(max(min(z, 4.0), -2.0)) - 0.5, 0.15)

def poisson_nll(y: float, mu: float) -> float:
    mu = max(float(mu), 1e-8)
    return mu - float(y) * math.log(mu) + float(gammaln(float(y) + 1.0))

def mean_poisson_nll(rows: list[dict], mus: list[float]) -> float:
    return float(np.mean([poisson_nll(r["y"], m) for r, m in zip(rows, mus)]))
def simplex_weights(rows: list[dict], rich: list[float]) -> tuple[list[float], float]:
    best = None
    for i in range(21):
        for j in range(21 - i):
            k = 20 - i - j
            w = [i / 20.0, j / 20.0, k / 20.0]
            mus = [
                w[0] * r["structural_mu"] + w[1] * r["decay_mu"] + w[2] * rm
                for r, rm in zip(rows, rich)
            ]
            loss = mean_poisson_nll(rows, mus)
            if best is None or loss < best[0] - 1e-12:
                best = (loss, w)
    assert best is not None
    return best[1], best[0]

def ensemble_mu(row: dict, rich_mu: float, weights: list[float]) -> float:
    return max(
        weights[0] * row["structural_mu"]
        + weights[1] * row["decay_mu"]
        + weights[2] * rich_mu,
        0.15,
    )

def fit_alpha(rows: list[dict], mus: list[float]) -> float:
    num = sum((r["y"] - m) ** 2 - m for r, m in zip(rows, mus))
    den = sum(m * m for m in mus)
    return float(min(max(num / max(den, 1e-9), 0.01), 2.0))
def nb_over(mu: float, alpha: float, line: float) -> float:
    n = 1.0 / max(alpha, 1e-9)
    p = n / (n + max(mu, 1e-9))
    return float(1.0 - nbinom.cdf(math.floor(line), n, p))

def logit(p: float) -> float:
    p = min(max(float(p), 1e-8), 1 - 1e-8)
    return math.log(p / (1 - p))

def logistic(z: float) -> float:
    z = max(min(float(z), 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-z))

def binary_samples(rows: list[dict], mus: list[float], alpha: float) -> list[tuple[float, int]]:
    out = []
    for r, mu in zip(rows, mus):
        for line in PRIMARY_LINES:
            p = nb_over(mu, alpha, line)
            out.append((p, int(r["y"] > line)))
    return out

def fit_platt(samples: list[tuple[float, int]]) -> tuple[float, float]:
    zs = np.asarray([logit(p) for p, _ in samples], dtype=float)
    ys = np.asarray([y for _, y in samples], dtype=float)
    def objective(theta):
        a, b = float(theta[0]), float(theta[1])
        logits = np.clip(a + b * zs, -35, 35)
        ps = 1.0 / (1.0 + np.exp(-logits))
        ps = np.clip(ps, 1e-10, 1 - 1e-10)
        return float(-np.mean(ys * np.log(ps) + (1 - ys) * np.log(1 - ps)))
    res = minimize(objective, np.asarray([0.0, 1.0]), method="L-BFGS-B",
                   bounds=[(-3.0, 3.0), (0.2, 3.0)])
    if not res.success:
        return 0.0, 1.0
    return float(res.x[0]), float(res.x[1])

def calibrate(p: float, a: float, b: float) -> float:
    return logistic(a + b * logit(p))

def binary_metrics(samples: list[tuple[float, int]]) -> dict:
    if not samples:
        return {}
    ps = np.asarray([p for p, _ in samples], dtype=float)
    ys = np.asarray([y for _, y in samples], dtype=float)
    ps = np.clip(ps, 1e-10, 1 - 1e-10)
    ll = float(-np.mean(ys * np.log(ps) + (1 - ys) * np.log(1 - ps)))
    br = float(np.mean((ps - ys) ** 2))
    ece = 0.0
    for lo in np.linspace(0, 0.9, 10):
        hi = lo + 0.1
        mask = (ps >= lo) & ((ps < hi) | ((hi >= 1.0) & (ps <= hi)))
        if mask.any():
            ece += float(mask.mean()) * abs(float(ps[mask].mean() - ys[mask].mean()))
    return {"n": int(len(samples)), "log_loss": ll, "brier": br, "ece_10bin": ece}
def sliced_binary_metrics(rows: list[dict], mus: list[float], alpha: float,
                          platt_a: float, platt_b: float) -> dict:
    by_line = {}
    for line in PRIMARY_LINES:
        raw = [(nb_over(mu, alpha, line), int(r["y"] > line)) for r, mu in zip(rows, mus)]
        cal = [(calibrate(p, platt_a, platt_b), y) for p, y in raw]
        by_line[str(line)] = binary_metrics(cal)
    by_role = {}
    for role in ("home", "away"):
        idx = [i for i, r in enumerate(rows) if r["role"] == role]
        sub_rows = [rows[i] for i in idx]
        sub_mus = [mus[i] for i in idx]
        raw = binary_samples(sub_rows, sub_mus, alpha)
        cal = [(calibrate(p, platt_a, platt_b), y) for p, y in raw]
        by_role[role] = binary_metrics(cal)
    return {"by_line_calibrated": by_line, "by_role_calibrated": by_role}

def count_metrics(rows: list[dict], component_mus: dict[str, list[float]]) -> dict:
    out = {}
    ys = np.asarray([r["y"] for r in rows], dtype=float)
    for name, mus in component_mus.items():
        arr = np.asarray(mus, dtype=float)
        out[name] = {
            "mae": float(np.mean(np.abs(arr - ys))),
            "rmse": float(np.sqrt(np.mean((arr - ys) ** 2))),
            "poisson_nll": mean_poisson_nll(rows, list(arr)),
        }
    return out

def main() -> int:
    evidence_rows = [json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
    matches = evidence_matches(evidence_rows)
    side_rows = build_side_dataset(matches)
    unique_ts = sorted({r["ts"] for r in side_rows})
    t60 = unique_ts[int(len(unique_ts) * 0.60)]
    t80 = unique_ts[int(len(unique_ts) * 0.80)]
    train = [r for r in side_rows if r["ts"] < t60]
    tune = [r for r in side_rows if t60 <= r["ts"] < t80]
    hold = [r for r in side_rows if r["ts"] >= t80]
    if min(len(train), len(tune), len(hold)) < 200:
        raise RuntimeError("insufficient chronological side rows")
    ridge_trials = []
    for lam in RIDGE_LAMBDAS:
        beta = fit_ridge(train, lam)
        mus = [ridge_mu(r, beta) for r in tune]
        ridge_trials.append((mean_poisson_nll(tune, mus), lam, beta))
    ridge_trials.sort(key=lambda x: (x[0], x[1]))
    ridge_tune_loss, ridge_lambda, beta = ridge_trials[0]

    tune_rich = [ridge_mu(r, beta) for r in tune]
    weights, tune_ensemble_poisson_nll = simplex_weights(tune, tune_rich)
    tune_mu = [ensemble_mu(r, rm, weights) for r, rm in zip(tune, tune_rich)]
    alpha = fit_alpha(tune, tune_mu)
    tune_raw_samples = binary_samples(tune, tune_mu, alpha)
    platt_a, platt_b = fit_platt(tune_raw_samples)

    hold_rich = [ridge_mu(r, beta) for r in hold]
    hold_mu = [ensemble_mu(r, rm, weights) for r, rm in zip(hold, hold_rich)]
    hold_raw = binary_samples(hold, hold_mu, alpha)
    hold_cal = [(calibrate(p, platt_a, platt_b), y) for p, y in hold_raw]
    component_mus = {
        "structural": [r["structural_mu"] for r in hold],
        "decay": [r["decay_mu"] for r in hold],
        "ridge_pressure": hold_rich,
        "ensemble": hold_mu,
    }
    spec_obj = json.loads(SPEC.read_text())
    artifact = {
        "experiment": "QFE Team Corners V1",
        "version": "QFE_TEAM_CORNERS_V1",
        "model_version": "TCV1_NB_3COMP_ENSEMBLE_PLATT",
        "historical_source": "THESTATSAPI_ONLY",
        "source_evidence_sha256": sha256_file(EVIDENCE),
        "spec_sha256": sha256_file(SPEC),
        "feature_builder_sha256": sha256_file(ROOT / "src/research/team_corners_v1/features.py"),
        "historical_corner_matches": len(matches),
        "pit_side_rows": len(side_rows),
        "split": {
            "train_side_rows": len(train), "tune_side_rows": len(tune), "holdout_side_rows": len(hold),
            "tune_start_ts": t60, "holdout_start_ts": t80,
        },
        "ridge": {
            "feature_names": list(RIDGE_FEATURE_NAMES),
            "lambda": ridge_lambda,
            "coefficients": [float(x) for x in beta],
            "tuning_trials": [{"lambda": x[1], "poisson_nll": x[0]} for x in ridge_trials],
        },
        "ensemble_weights": {
            "hierarchical_attack_defence": weights[0],
            "decay_profile": weights[1],
            "ridge_pressure": weights[2],
        },
        "negative_binomial_alpha": alpha,
        "calibration": {"type": "monotone_platt", "intercept": platt_a, "slope": platt_b},
        "selection": spec_obj["selection"],
        "lines": list(PRIMARY_LINES),
        "tuning": {
            "ensemble_poisson_nll": tune_ensemble_poisson_nll,
            "binary_raw": binary_metrics(tune_raw_samples),
        },
        "untouched_holdout": {
            "count_metrics": count_metrics(hold, component_mus),
            "binary_raw": binary_metrics(hold_raw),
            "binary_calibrated": binary_metrics(hold_cal),
            **sliced_binary_metrics(hold, hold_mu, alpha, platt_a, platt_b),
        },
        "training_max_match_ts": max(m["ts"] for m in matches),
        "notes": [
            "All feature rows are constructed point-in-time from prior completed matches only.",
            "Ridge lambda, ensemble weights, NB dispersion and Platt calibration use no holdout outcomes.",
            "The prospective experiment is the decisive validation; holdout evidence does not authorize CHAMPION promotion."
        ],
    }
    artifact["freeze_sha256"] = canonical_hash(artifact)
    MODEL_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FREEZE.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
