"""Run preregistered V3.2.3 venue-conditioned goals/BTTS comparison."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from src.research.evidence_v32.modeling import (
    binary_metrics, event_outcomes, event_probabilities, joint_distribution,
    paired_gain,
)
from src.research.evidence_v32.modeling_v322 import (
    COMPLETION_BUFFER_SECONDS, DirectLogistic, LinearCount, UnsupportedFeatures,
    count_scales, platt_apply, platt_fit, side_design,
)
from src.research.evidence_v32.modeling_v323 import build_venue_panel

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "SPEC_V32_3.json"
PARENT_SPEC = ROOT / "SPEC_V32_2.json"
EVIDENCE = ROOT / "out/evidence_v2/evidence.jsonl"
OUTPUT = ROOT / "out/model_comparison_v4"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows() -> list[dict]:
    return [json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]
def split_fold(rows: list[dict], fold: dict):
    rows = sorted(rows, key=lambda r: (r["kickoff_ts"], r["match_id"]))
    groups = sorted({float(r["kickoff_ts"]) for r in rows})
    if len(groups) < 10:
        return [], [], []

    def boundary(frac: float) -> float:
        idx = min(max(int(math.ceil(len(groups) * frac)) - 1, 0), len(groups) - 1)
        return groups[idx]

    train_end, cal_end, test_end = (
        boundary(fold[k]) for k in ("train_end", "cal_end", "test_end")
    )
    train = [r for r in rows if r["kickoff_ts"] <= train_end]
    cal = [r for r in rows if train_end < r["kickoff_ts"] <= cal_end]
    test = [r for r in rows if cal_end < r["kickoff_ts"] <= test_end]
    if cal:
        first = min(r["cutoff_ts"] for r in cal)
        train = [r for r in train
                 if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first]
    if test:
        first = min(r["cutoff_ts"] for r in test)
        cal = [r for r in cal
               if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first]
    return train, cal, test
def fit_count(key: str, train: list[dict], cal: list[dict], test: list[dict]):
    ytrain = np.asarray([r["y"] for r in train], float)
    ycal = np.asarray([r["y"] for r in cal], float)
    model = LinearCount(side_design(train, key), ytrain.ravel())
    cal_raw = model.predict(side_design(cal, key)).reshape(-1, 2)
    scales = count_scales(cal_raw, ycal)
    means = model.predict(side_design(test, key)).reshape(-1, 2) * scales[None, :]
    predictions = []
    for row, pair in zip(test, means):
        joint = joint_distribution(float(pair[0]), float(pair[1]), "poisson", max_count=20)
        outcomes = event_outcomes([int(x) for x in row["y"]], "goals")
        probabilities = event_probabilities(joint, "goals")
        for target, event in outcomes.items():
            p = float(np.clip(probabilities[target], 1e-8, 1 - 1e-8))
            predictions.append({
                "match_id": row["match_id"],
                "competition_id": row["competition_id"],
                "date": row["date"],
                "target": target,
                "event": event,
                "p": p,
                "loss": float(-event * math.log(p) - (1 - event) * math.log1p(-p)),
            })
    return {"calibration_scales": [float(x) for x in scales]}, predictions
def fit_direct_venue_btts(train: list[dict], cal: list[dict], test: list[dict]):
    ytrain = np.asarray([int(r["y"][0] > 0 and r["y"][1] > 0) for r in train], int)
    ycal = np.asarray([int(r["y"][0] > 0 and r["y"][1] > 0) for r in cal], int)
    model = DirectLogistic([r["match_venue"] for r in train], ytrain)
    beta = platt_fit(model.predict([r["match_venue"] for r in cal]), ycal)
    ptest = platt_apply(model.predict([r["match_venue"] for r in test]), beta)
    predictions = []
    for row, p in zip(test, ptest):
        event = int(row["y"][0] > 0 and row["y"][1] > 0)
        p = float(np.clip(p, 1e-8, 1 - 1e-8))
        predictions.append({
            "match_id": row["match_id"],
            "competition_id": row["competition_id"],
            "date": row["date"],
            "target": "BTTS",
            "event": event,
            "p": p,
            "loss": float(-event * math.log(p) - (1 - event) * math.log1p(-p)),
        })
    return {"platt_intercept": float(beta[0]), "platt_slope": float(beta[1])}, predictions
def compare(base: list[dict], candidate: list[dict]) -> dict:
    gain = paired_gain(base, candidate, seed=3230)
    bm, cm = binary_metrics(base), binary_metrics(candidate)
    gain["brier_delta_candidate_minus_base"] = cm["brier"] - bm["brier"]
    return gain


def pooled_target_results(pooled: dict[str, list[dict]], baseline: str) -> dict:
    targets = sorted({r["target"] for rows in pooled.values() for r in rows})
    out = {}
    for target in targets:
        by_arm = {
            arm: [r for r in rows if r["target"] == target]
            for arm, rows in pooled.items()
        }
        base = by_arm.get(baseline, [])
        out[target] = {
            "metrics": {arm: binary_metrics(rows) for arm, rows in by_arm.items()},
            "vs_baseline": {
                arm: compare(base, rows)
                for arm, rows in by_arm.items()
                if arm != baseline and base and rows
            },
            "state": "DEVELOPMENT_ONLY",
            "market_state": "NOT_USED_IN_V32_3_FIT",
        }
    return out
def run_count_cohort(panel: list[dict], eligible_key: str, keys: dict[str, str],
                     folds: list[dict], minimum: dict):
    eligible = [r for r in panel if r[eligible_key]]
    pooled = {arm: [] for arm in keys}
    fits, states = [], []
    for fold_id, fold in enumerate(folds, 1):
        train, cal, test = split_fold(eligible, fold)
        counts = {"train": len(train), "calibration": len(cal), "test": len(test)}
        if (
            len(train) < minimum["minimum_train"]
            or len(cal) < minimum["minimum_calibration"]
            or len(test) < minimum["minimum_test"]
        ):
            states.append({"fold": fold_id, "state": "INSUFFICIENT_SUPPORT",
                           "counts": counts})
            continue
        failures = []
        for arm, key in keys.items():
            try:
                fit, pred = fit_count(key, train, cal, test)
            except (UnsupportedFeatures, ValueError) as exc:
                failures.append({"arm": arm, "reason": str(exc)})
                continue
            fit.update({"arm": arm, "fold": fold_id, **counts})
            fits.append(fit)
            pooled[arm].extend(dict(r, fold=fold_id) for r in pred)
        states.append({"fold": fold_id, "state": "FITTED_DEVELOPMENT",
                       "counts": counts, "failures": failures})
    return eligible, pooled, fits, states
def main():
    spec = json.loads(SPEC.read_text())
    parent = json.loads(PARENT_SPEC.read_text())
    if spec["version"] != "EVIDENCE_V32_3_VENUE_BTTS_DEVELOPMENT_1":
        raise RuntimeError("unexpected V32.3 spec")
    if OUTPUT.exists():
        raise RuntimeError("immutable V32.3 output already exists")

    rows = read_rows()
    panel = build_venue_panel(rows)
    folds = parent["folds"]
    minimum = parent["walk_forward"]

    eligible, pooled, fits, states = run_count_cohort(
        panel, "eligible_venue",
        {"DEEP_POISSON_CONTROL": "deep", "VENUE_DEEP_POISSON": "venue"},
        folds, minimum,
    )
    results = {
        "venue_primary": {
            "eligible_fixtures": len(eligible),
            "targets": pooled_target_results(pooled, "DEEP_POISSON_CONTROL"),
            "fold_states": states,
            "fits": fits,
        }
    }
    xg_eligible, xg_pooled, xg_fits, xg_states = run_count_cohort(
        panel, "eligible_venue_xg",
        {"VENUE_DEEP_POISSON_CONTROL": "venue",
         "VENUE_DEEP_POISSON_XG": "venue_xg"},
        folds, minimum,
    )
    results["venue_xg"] = {
        "eligible_fixtures": len(xg_eligible),
        "targets": pooled_target_results(xg_pooled, "VENUE_DEEP_POISSON_CONTROL"),
        "fold_states": xg_states,
        "fits": xg_fits,
    }

    direct_pooled = []
    direct_fits = []
    direct_states = []
    for fold_id, fold in enumerate(folds, 1):
        train, cal, test = split_fold(eligible, fold)
        counts = {"train": len(train), "calibration": len(cal), "test": len(test)}
        if (
            len(train) < minimum["minimum_train"]
            or len(cal) < minimum["minimum_calibration"]
            or len(test) < minimum["minimum_test"]
        ):
            direct_states.append({"fold": fold_id, "state": "INSUFFICIENT_SUPPORT",
                                  "counts": counts})
            continue
        fit, pred = fit_direct_venue_btts(train, cal, test)
        fit.update({"fold": fold_id, **counts})
        direct_fits.append(fit)
        direct_pooled.extend(dict(r, fold=fold_id) for r in pred)
        direct_states.append({"fold": fold_id, "state": "FITTED_DEVELOPMENT",
                              "counts": counts})
    joint_venue = [r for r in pooled["VENUE_DEEP_POISSON"] if r["target"] == "BTTS"]
    results["direct_btts_secondary"] = {
        "metrics": {
            "JOINT_VENUE_POISSON": binary_metrics(joint_venue),
            "DIRECT_VENUE_LOGISTIC": binary_metrics(direct_pooled),
        },
        "direct_minus_joint": compare(joint_venue, direct_pooled),
        "fold_states": direct_states,
        "fits": direct_fits,
        "state": "DEVELOPMENT_ONLY",
    }

    support = {
        "panel_fixtures": len(panel),
        "eligible_venue": sum(r["eligible_venue"] for r in panel),
        "eligible_venue_xg": sum(r["eligible_venue_xg"] for r in panel),
        "competitions_venue": dict(Counter(
            r["competition_id"] for r in panel if r["eligible_venue"]
        )),
        "venue_history": {
            "home_matches_min": min(
                (r["venue_support"]["home_matches"] for r in panel if r["eligible_venue"]),
                default=None),
            "away_matches_min": min(
                (r["venue_support"]["away_matches"] for r in panel if r["eligible_venue"]),
                default=None),
        },
    }

    OUTPUT.mkdir(parents=True)
    (OUTPUT / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n")
    (OUTPUT / "support.json").write_text(
        json.dumps(support, indent=2, sort_keys=True, allow_nan=False) + "\n")
    manifest = {
        "version": spec["version"],
        "state": "DEVELOPMENT_ONLY",
        "live_calls": 0,
        "market_used_for_fit": False,
        "promotion_count": 0,
        "evidence_sha256": sha(EVIDENCE),
        "spec_sha256": sha(SPEC),
        "parent_spec_sha256": sha(PARENT_SPEC),
        "modeling_v323_sha256": sha(
            ROOT.parents[1] / "src/research/evidence_v32/modeling_v323.py"),
        "runner_sha256": sha(Path(__file__)),
    }
    manifest["files"] = {
        p.name: sha(p) for p in sorted(OUTPUT.iterdir())
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(json.dumps({
        "support": support,
        "primary_targets": {
            target: data["vs_baseline"].get("VENUE_DEEP_POISSON")
            for target, data in results["venue_primary"]["targets"].items()
        },
        "direct_btts_secondary": results["direct_btts_secondary"]["direct_minus_joint"],
    }, indent=2))


if __name__ == "__main__":
    main()
