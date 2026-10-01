"""Fit the frozen forward V3.5 artifact from pre-freeze development evidence.

This is model construction, not validation. No market prices or future outcomes
enter the resulting probability path.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import poisson

from src.research.evidence_v32.modeling import COMPLETION_BUFFER_SECONDS
from src.research.evidence_v32.modeling_v322 import (
    LinearCount, count_scales, side_design,
)
from src.research.evidence_v32.modeling_v323 import build_venue_panel
from src.research.evidence_v32.modeling_v33_corners import build_corner_panel
from src.research.v3_pilot.model import (
    InsufficientHistory as V3InsufficientHistory,
    poisson_over, predict_corners as predict_v3_corners,
)
from src.research.v35_frontier.features import v3_corner_rows
from src.research.v35_frontier.model import (
    CORNER_LINES, _canonical_without_hash, _clip, _logit, _sigmoid,
    export_linear_count,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "research/v35_frontier/V35_TRAINING_SPEC_V1.json"
EVIDENCE = ROOT / "research/evidence_v32/out/evidence_v2/evidence.jsonl"
OUTPUT = ROOT / "research/v35_frontier/V35_MODEL_ARTIFACT_V1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows() -> list[dict]:
    return [json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]


def _boundary(groups: list[float], frac: float) -> float:
    idx = min(max(int(math.ceil(len(groups) * frac)) - 1, 0), len(groups) - 1)
    return groups[idx]


def split_two(panel: list[dict], train_fraction: float):
    ordered = sorted(panel, key=lambda r: (r["kickoff_ts"], r["match_id"]))
    groups = sorted({float(r["kickoff_ts"]) for r in ordered})
    cut = _boundary(groups, train_fraction)
    train = [r for r in ordered if r["kickoff_ts"] <= cut]
    cal = [r for r in ordered if r["kickoff_ts"] > cut]
    if cal:
        first = min(r["cutoff_ts"] for r in cal)
        train = [
            r for r in train
            if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first
        ]
    return train, cal


def split_three(panel: list[dict], train_fraction: float, count_cal_fraction: float):
    ordered = sorted(panel, key=lambda r: (r["kickoff_ts"], r["match_id"]))
    groups = sorted({float(r["kickoff_ts"]) for r in ordered})
    a = _boundary(groups, train_fraction)
    b = _boundary(groups, train_fraction + count_cal_fraction)
    train = [r for r in ordered if r["kickoff_ts"] <= a]
    count_cal = [r for r in ordered if a < r["kickoff_ts"] <= b]
    stack_cal = [r for r in ordered if r["kickoff_ts"] > b]
    if count_cal:
        first = min(r["cutoff_ts"] for r in count_cal)
        train = [
            r for r in train
            if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first
        ]
    if stack_cal:
        first = min(r["cutoff_ts"] for r in stack_cal)
        count_cal = [
            r for r in count_cal
            if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first
        ]
    return train, count_cal, stack_cal


def fit_count(train: list[dict], cal: list[dict], key: str):
    ytrain = np.asarray([r["y"] for r in train], float)
    ycal = np.asarray([r["y"] for r in cal], float)
    model = LinearCount(side_design(train, key), ytrain.ravel())
    raw = model.predict(side_design(cal, key)).reshape(-1, 2)
    scales = count_scales(raw, ycal)
    return model, scales


def fit_weight(reference: list[float], challenger: list[float], outcomes: list[int]) -> float:
    if not reference or len(reference) != len(challenger) or len(reference) != len(outcomes):
        raise RuntimeError("invalid stack calibration vectors")

    def loss(w: float) -> float:
        total = 0.0
        for pr, pc, y in zip(reference, challenger, outcomes):
            p = _clip(_sigmoid((1.0-w)*_logit(pr) + w*_logit(pc)))
            total += -y*math.log(p) - (1-y)*math.log1p(-p)
        return total / len(outcomes)

    res = minimize_scalar(
        loss, bounds=(0.0, 1.0), method="bounded",
        options={"xatol": 1e-8, "maxiter": 300},
    )
    if not res.success:
        raise RuntimeError("stack weight optimization failed")
    return float(np.clip(res.x, 0.0, 1.0))


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError(f"immutable artifact already exists: {OUTPUT}")
    spec = json.loads(SPEC.read_text())
    if spec["version"] != "QFE_V35_FRONTIER_TRAINING_1":
        raise RuntimeError("unexpected V35 spec")

    evidence_rows = rows()

    # Goals: selected VENUE_DEEP model, no ensemble.
    gp = [r for r in build_venue_panel(evidence_rows) if r["eligible_venue"]]
    gtrain, gcal = split_two(gp, float(spec["goals_over_under"]["train_fraction"]))
    if min(len(gtrain), len(gcal)) < 100:
        raise RuntimeError("insufficient final goals train/calibration support")
    gmodel, gscales = fit_count(gtrain, gcal, "venue")

    # Corners: pressure parent then independent trailing stack calibration.
    cp = [r for r in build_corner_panel(evidence_rows) if r["eligible_pressure"]]
    ctrain, ccount, cstack = split_three(
        cp,
        float(spec["corners_over_under"]["pressure_train_fraction"]),
        float(spec["corners_over_under"]["pressure_count_calibration_fraction"]),
    )
    if min(len(ctrain), len(ccount), len(cstack)) < 100:
        raise RuntimeError("insufficient final corners train/calibration support")
    cmodel, cscales = fit_count(ctrain, ccount, "pressure")

    stack_pressure = cmodel.predict(side_design(cstack, "pressure")).reshape(-1, 2)
    stack_pressure = stack_pressure * np.asarray(cscales, float)[None, :]

    by_comp = {}
    for comp in {str(r["competition_id"]) for r in cstack}:
        by_comp[comp] = v3_corner_rows(evidence_rows, comp)

    reference = {str(line): [] for line in CORNER_LINES}
    challenger = {str(line): [] for line in CORNER_LINES}
    outcomes = {str(line): [] for line in CORNER_LINES}
    common_fixture_ids = []

    for row, means in zip(cstack, stack_pressure):
        comp = str(row["competition_id"])
        target = {
            "match_id": str(row["match_id"]),
            "competition_id": comp,
            "ts": float(row["kickoff_ts"]),
            "home_id": str(row["home_id"]),
            "away_id": str(row["away_id"]),
        }
        try:
            v3 = predict_v3_corners(by_comp[comp], by_comp[comp], target)
        except V3InsufficientHistory:
            continue
        common_fixture_ids.append(str(row["match_id"]))
        actual_total = int(row["y"][0] + row["y"][1])
        pressure_total = float(means[0] + means[1])
        for line in CORNER_LINES:
            key = str(line)
            reference[key].append(_clip(poisson_over(line, float(v3["lambda_total"]))))
            challenger[key].append(_clip(poisson.sf(math.floor(line), pressure_total)))
            outcomes[key].append(int(actual_total > line))

    weights = {
        str(line): fit_weight(
            reference[str(line)], challenger[str(line)], outcomes[str(line)]
        )
        for line in CORNER_LINES
    }

    artifact = {
        "version": "QFE_V35_MODEL_ARTIFACT_1",
        "created_from_spec_version": spec["version"],
        "training_spec_sha256": sha256(SPEC),
        "training_evidence_sha256": sha256(EVIDENCE),
        "market_used_for_fit": false,
        "production_activation": false,
        "goals": {
            "version": "V35_GOALS_VENUE_DEEP_POISSON",
            "lines": list(spec["goals_over_under"]["markets"]),
            "linear_count": export_linear_count(gmodel),
            "calibration_scales": [float(x) for x in gscales],
            "support": {
                "eligible": len(gp), "train": len(gtrain), "calibration": len(gcal),
                "train_max_kickoff_ts": max(r["kickoff_ts"] for r in gtrain),
                "calibration_min_kickoff_ts": min(r["kickoff_ts"] for r in gcal),
                "calibration_max_kickoff_ts": max(r["kickoff_ts"] for r in gcal),
            },
        },
        "corners": {
            "version": "V35_CORNERS_V3_PRESSURE_STACK",
            "lines": list(spec["corners_over_under"]["markets"]),
            "pressure_linear_count": export_linear_count(cmodel),
            "pressure_calibration_scales": [float(x) for x in cscales],
            "stack_weights": weights,
            "support": {
                "eligible": len(cp), "train": len(ctrain),
                "count_calibration": len(ccount), "stack_calibration": len(cstack),
                "stack_common_v3": len(common_fixture_ids),
                "train_max_kickoff_ts": max(r["kickoff_ts"] for r in ctrain),
                "count_calibration_min_kickoff_ts": min(r["kickoff_ts"] for r in ccount),
                "count_calibration_max_kickoff_ts": max(r["kickoff_ts"] for r in ccount),
                "stack_calibration_min_kickoff_ts": min(r["kickoff_ts"] for r in cstack),
                "stack_calibration_max_kickoff_ts": max(r["kickoff_ts"] for r in cstack),
            },
        },
    }
    artifact["artifact_sha256"] = _canonical_without_hash(artifact)
    OUTPUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "artifact": str(OUTPUT),
        "artifact_sha256": artifact["artifact_sha256"],
        "goals_support": artifact["goals"]["support"],
        "corners_support": artifact["corners"]["support"],
        "corner_stack_weights": weights,
    }, indent=2))


if __name__ == "__main__":
    main()
