from __future__ import annotations
import hashlib
import json
import math

import numpy as np
from scipy.stats import nbinom

from .config import EVIDENCE, MODEL_FREEZE, PRIMARY_LINES, SPEC
from .features import evidence_matches, prospective_features

_FREEZE = None
_MATCHES = None

def _canonical_hash(obj: dict) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()

def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def freeze() -> dict:
    global _FREEZE
    if _FREEZE is None:
        obj = json.loads(MODEL_FREEZE.read_text(encoding="utf-8"))
        saved = obj.get("freeze_sha256")
        raw = {k: v for k, v in obj.items() if k != "freeze_sha256"}
        if _canonical_hash(raw) != saved:
            raise RuntimeError("team-corners model freeze hash mismatch")
        if _sha256_file(EVIDENCE) != obj["source_evidence_sha256"]:
            raise RuntimeError("team-corners historical evidence hash mismatch")
        if _sha256_file(SPEC) != obj["spec_sha256"]:
            raise RuntimeError("team-corners preregistered spec hash mismatch")
        feature_path = SPEC.parents[2] / "src/research/team_corners_v1/features.py"
        if _sha256_file(feature_path) != obj["feature_builder_sha256"]:
            raise RuntimeError("team-corners feature-builder hash mismatch")
        _FREEZE = obj
    return _FREEZE

def _matches() -> list[dict]:
    global _MATCHES
    if _MATCHES is None:
        rows = [json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
        _MATCHES = evidence_matches(rows)
    return _MATCHES

def _ridge_mu(x: list[float], beta: list[float]) -> float:
    z = float(np.dot(np.asarray(x, dtype=float), np.asarray(beta, dtype=float)))
    return max(math.exp(max(min(z, 4.0), -2.0)) - 0.5, 0.15)

def _nb_over(mu: float, alpha: float, line: float) -> float:
    n = 1.0 / max(float(alpha), 1e-9)
    p = n / (n + max(float(mu), 1e-9))
    return float(1.0 - nbinom.cdf(math.floor(float(line)), n, p))

def _logit(p: float) -> float:
    p = min(max(float(p), 1e-8), 1 - 1e-8)
    return math.log(p / (1.0 - p))
def _calibrate(p: float, intercept: float, slope: float) -> float:
    z = max(min(intercept + slope * _logit(p), 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-z))

def predict_side(fixture: dict, role: str) -> dict | None:
    art = freeze()
    feat = prospective_features(_matches(), fixture, role)
    if feat is None:
        return None
    rich = _ridge_mu(feat["ridge_x"], art["ridge"]["coefficients"])
    w = art["ensemble_weights"]
    mu = (
        float(w["hierarchical_attack_defence"]) * feat["structural_mu"]
        + float(w["decay_profile"]) * feat["decay_mu"]
        + float(w["ridge_pressure"]) * rich
    )
    alpha = float(art["negative_binomial_alpha"])
    cal = art["calibration"]
    probs = {}
    for line in PRIMARY_LINES:
        raw = _nb_over(mu, alpha, line)
        probs[str(line)] = {
            "p_over_raw": raw,
            "p_over": _calibrate(raw, float(cal["intercept"]), float(cal["slope"])),
        }
    return {
        "role": role,
        "team_id": str(fixture["home_id"] if role == "home" else fixture["away_id"]),
        "team_name": str(fixture["home_name"] if role == "home" else fixture["away_name"]),
        "mu": float(mu),
        "negative_binomial_alpha": alpha,
        "probabilities": probs,
        "components": {
            "hierarchical_attack_defence_mu": feat["structural_mu"],
            "decay_profile_mu": feat["decay_mu"],
            "ridge_pressure_mu": rich,
        },
        "ensemble_weights": w,
        "history": {
            "team_n": feat["history_n_team"],
            "opponent_n": feat["history_n_opp"],
            "competition_role_baseline": feat["baseline"],
        },
        "model_version": art["model_version"],
        "model_freeze_sha256": art["freeze_sha256"],
    }

def predict_fixture(fixture: dict) -> dict:
    art = freeze()
    sides = {}
    abstentions = []
    for role in ("home", "away"):
        side = predict_side(fixture, role)
        if side is None:
            abstentions.append({"role": role, "reason": "INSUFFICIENT_PIT_HISTORY"})
        else:
            sides[role] = side
    return {
        "experiment": "QFE Team Corners V1",
        "model_freeze_sha256": art["freeze_sha256"],
        "sides": sides,
        "abstentions": abstentions,
    }
