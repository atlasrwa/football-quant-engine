"""Portable V3.5 selected-frontier probability models.

No market prices enter this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import poisson

from src.research.v3_pilot.model import (
    canonical_hash, poisson_over, predict_corners as predict_v3_corners,
)

from .features import (
    FrontierUnsupported, corner_target_features, goal_target_features,
    v3_corner_rows,
)

GOAL_LINES = (2.5, 3.5)
CORNER_LINES = (8.5, 9.5, 10.5)


class ArtifactIntegrityError(RuntimeError):
    pass


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_without_hash(obj: dict[str, Any]) -> str:
    payload = {k: v for k, v in obj.items() if k != "artifact_sha256"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def load_artifact(path: str | Path) -> dict:
    p = Path(path)
    obj = json.loads(p.read_text(encoding="utf-8"))
    observed = _canonical_without_hash(obj)
    declared = str(obj.get("artifact_sha256") or "")
    if observed != declared:
        raise ArtifactIntegrityError(
            f"V35 artifact mismatch: declared={declared}, observed={observed}"
        )
    return obj


class FrozenLinearCount:
    """Portable form of the audited LinearCount / PoissonRegressor arm."""

    def __init__(self, artifact: dict) -> None:
        self.median = np.asarray(artifact["median"], dtype=float)
        self.mean = np.asarray(artifact["mean"], dtype=float)
        self.std = np.asarray(artifact["std"], dtype=float)
        self.coef = np.asarray(artifact["coef"], dtype=float)
        self.intercept = float(artifact["intercept"])
        if not (
            self.mean.shape == self.std.shape == self.coef.shape
            and self.mean.size == self.median.size * 2
        ):
            raise ArtifactIntegrityError("invalid FrozenLinearCount dimensions")

    def _impute(self, x) -> np.ndarray:
        arr = np.asarray(x, dtype=float)
        if arr.ndim == 1:
            arr = arr[None, :]
        if arr.shape[1] != self.median.size:
            raise FrontierUnsupported(
                f"feature dimension mismatch {arr.shape[1]} != {self.median.size}"
            )
        missing = ~np.isfinite(arr)
        return np.column_stack((np.where(missing, self.median, arr), missing.astype(float)))

    def predict(self, x) -> np.ndarray:
        z = self._impute(x)
        scaled = (z - self.mean) / self.std
        eta = self.intercept + scaled @ self.coef
        return np.maximum(np.exp(np.clip(eta, -30, 30)), 1e-8)


def export_linear_count(model) -> dict:
    return {
        "median": [float(x) for x in model.median],
        "mean": [float(x) for x in model.mean],
        "std": [float(x) for x in model.std],
        "coef": [float(x) for x in model.model.coef_],
        "intercept": float(model.model.intercept_),
        "feature_dimension": int(len(model.median)),
        "expanded_dimension": int(len(model.mean)),
    }


def _clip(p: float) -> float:
    return float(np.clip(float(p), 1e-8, 1 - 1e-8))


def _logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(float(x), 35.0), -35.0)))


def blend_probability(p_reference: float, p_challenger: float, weight: float) -> float:
    w = min(max(float(weight), 0.0), 1.0)
    return _clip(_sigmoid((1.0 - w) * _logit(p_reference) + w * _logit(p_challenger)))


def predict_goals(rows: list[dict], fixture: dict, artifact: dict) -> dict:
    cfg = artifact["goals"]
    feat = goal_target_features(rows, fixture)
    model = FrozenLinearCount(cfg["linear_count"])
    means = model.predict([feat["home"], feat["away"]])
    scales = np.asarray(cfg["calibration_scales"], dtype=float)
    if scales.shape != (2,):
        raise ArtifactIntegrityError("goal calibration scales must have length 2")
    home, away = (means * scales).tolist()
    total = float(home + away)
    probabilities = {}
    for line in GOAL_LINES:
        p = _clip(poisson.sf(math.floor(line), total))
        probabilities[str(line)] = {"p_over": p}
    out = {
        "version": "V35_GOALS_VENUE_DEEP_POISSON",
        "lambda_home": float(home),
        "lambda_away": float(away),
        "lambda_total": total,
        "probabilities": probabilities,
        "feature_cutoff_ts": feat["cutoff_ts"],
        "feature_support": feat["support"],
        "model_artifact_hash": artifact["artifact_sha256"],
        "training_evidence_sha256": artifact["training_evidence_sha256"],
    }
    out["distribution_hash"] = canonical_hash(out)
    return out


def predict_corners(rows: list[dict], fixture: dict, artifact: dict) -> dict:
    cfg = artifact["corners"]
    feat = corner_target_features(rows, fixture)
    pressure_model = FrozenLinearCount(cfg["pressure_linear_count"])
    means = pressure_model.predict([feat["home"], feat["away"]])
    scales = np.asarray(cfg["pressure_calibration_scales"], dtype=float)
    if scales.shape != (2,):
        raise ArtifactIntegrityError("corner calibration scales must have length 2")
    phome, paway = (means * scales).tolist()
    pressure_total = float(phome + paway)

    comp_rows = v3_corner_rows(rows, str(fixture["competition_id"]))
    target = {
        "match_id": str(fixture["match_id"]),
        "competition_id": str(fixture["competition_id"]),
        "season_id": str(fixture.get("season_id") or ""),
        "ts": float(fixture.get("kickoff_ts", fixture.get("ts"))),
        "home_id": str(fixture["home_id"]),
        "away_id": str(fixture["away_id"]),
    }
    v3 = predict_v3_corners(comp_rows, comp_rows, target)
    v3_total = float(v3["lambda_total"])

    probabilities = {}
    for line in CORNER_LINES:
        p_v3 = _clip(poisson_over(line, v3_total))
        p_pressure = _clip(poisson.sf(math.floor(line), pressure_total))
        weight = float(cfg["stack_weights"][str(line)])
        probabilities[str(line)] = {
            "p_over": blend_probability(p_v3, p_pressure, weight),
            "p_over_v3": p_v3,
            "p_over_pressure": p_pressure,
            "pressure_weight": weight,
        }

    out = {
        "version": "V35_CORNERS_V3_PRESSURE_STACK",
        "probabilities": probabilities,
        "v3_lambda_total": v3_total,
        "pressure_lambda_home": float(phome),
        "pressure_lambda_away": float(paway),
        "pressure_lambda_total": pressure_total,
        "feature_cutoff_ts": feat["cutoff_ts"],
        "v3_distribution_hash": v3["distribution_hash"],
        "model_artifact_hash": artifact["artifact_sha256"],
        "training_evidence_sha256": artifact["training_evidence_sha256"],
    }
    out["distribution_hash"] = canonical_hash(out)
    return out
