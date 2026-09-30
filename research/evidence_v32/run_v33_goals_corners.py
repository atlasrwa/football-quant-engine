"""Run frozen V3.3 goals/corners model-upgrade comparisons. Offline only."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import poisson

from src.research.evidence_v32.modeling import binary_metrics, paired_gain
from src.research.evidence_v32.modeling_v322 import (
    COMPLETION_BUFFER_SECONDS, GOALS_DEEP, GOALS_PRIMARY, LinearCount,
    UnsupportedFeatures, count_scales, side_design,
)
from src.research.evidence_v32.modeling_v323 import build_venue_panel
from src.research.evidence_v32.modeling_v33_corners import build_corner_panel
from src.research.v3_pilot.model import (
    InsufficientHistory as V3InsufficientHistory,
    predict_corners as predict_v3_corners,
)

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "SPEC_V33_GOALS_CORNERS.json"
PARENT_SPEC = ROOT / "SPEC_V32_2.json"
EVIDENCE = ROOT / "out/evidence_v2/evidence.jsonl"
OUTPUT = ROOT / "out/model_comparison_v33"
GOAL_LINES = (2.5, 3.5)
CORNER_LINES = (8.5, 9.5, 10.5)
GOAL_COMPACT_KEYS = tuple(GOALS_PRIMARY) + (
    "touches_box", "big_missed", "shots_off", "shots_outside",
)


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

    a, b, c = (boundary(fold[k]) for k in ("train_end", "cal_end", "test_end"))
    train = [r for r in rows if r["kickoff_ts"] <= a]
    cal = [r for r in rows if a < r["kickoff_ts"] <= b]
    test = [r for r in rows if b < r["kickoff_ts"] <= c]
    if cal:
        first = min(r["cutoff_ts"] for r in cal)
        train = [r for r in train
                 if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first]
    if test:
        first = min(r["cutoff_ts"] for r in test)
        cal = [r for r in cal
               if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first]
    return train, cal, test
def _slice_goal_vector(vector: list[float | None],
                       keys: tuple[str, ...],
                       keep_venue_append: bool = False) -> list[float | None]:
    base_len = 7 + 4 * len(GOALS_DEEP)
    out = list(vector[:7])
    for i, key in enumerate(GOALS_DEEP):
        if key in keys:
            start = 7 + 4 * i
            out.extend(vector[start:start + 4])
    if keep_venue_append:
        out.extend(vector[base_len:])
    return out


def prepare_goal_panel(rows: list[dict]) -> list[dict]:
    panel = build_venue_panel(rows)
    for row in panel:
        for side in ("home", "away"):
            deep = row[side]["deep"]
            venue = row[side]["venue"]
            row[side]["rich_v33"] = _slice_goal_vector(deep, tuple(GOALS_PRIMARY))
            row[side]["compact_v33"] = _slice_goal_vector(deep, GOAL_COMPACT_KEYS)
            row[side]["venue_compact_v33"] = _slice_goal_vector(
                venue, GOAL_COMPACT_KEYS, keep_venue_append=True)
    return panel


def fit_count_arm(key: str, train: list[dict], cal: list[dict], test: list[dict],
                  lines: tuple[float, ...], target_prefix: str):
    ytrain = np.asarray([r["y"] for r in train], float)
    ycal = np.asarray([r["y"] for r in cal], float)
    model = LinearCount(side_design(train, key), ytrain.ravel())
    cal_raw = model.predict(side_design(cal, key)).reshape(-1, 2)
    scales = count_scales(cal_raw, ycal)
    test_means = model.predict(side_design(test, key)).reshape(-1, 2) * scales[None, :]

    predictions = []
    count_losses = []
    for row, means in zip(test, test_means):
        home, away = map(float, means)
        actual_home, actual_away = map(int, row["y"])
        count_losses.append(
            -float(poisson.logpmf(actual_home, home) + poisson.logpmf(actual_away, away))
        )
        total_mean = home + away
        actual_total = actual_home + actual_away
        for line in lines:
            p = float(np.clip(poisson.sf(math.floor(line), total_mean), 1e-8, 1 - 1e-8))
            event = int(actual_total > line)
            predictions.append({
                "match_id": row["match_id"],
                "competition_id": row["competition_id"],
                "date": row["date"],
                "kickoff_ts": row["kickoff_ts"],
                "target": f"{target_prefix}>{line}",
                "event": event,
                "p": p,
                "loss": float(-event * math.log(p) - (1 - event) * math.log1p(-p)),
            })
    return {
        "calibration_scales": [float(x) for x in scales],
        "joint_count_log_loss": float(np.mean(count_losses)),
    }, predictions
def compare(base: list[dict], candidate: list[dict]) -> dict:
    lookup = {(r["match_id"], r["target"], r.get("fold")): r for r in candidate}
    a, b = [], []
    for row in base:
        other = lookup.get((row["match_id"], row["target"], row.get("fold")))
        if other is not None:
            a.append(row)
            b.append(other)
    out = paired_gain(a, b, seed=3300)
    bm, cm = binary_metrics(a), binary_metrics(b)
    out["baseline_metrics"] = bm
    out["candidate_metrics"] = cm
    out["brier_delta_candidate_minus_base"] = (
        cm.get("brier") - bm.get("brier") if cm.get("brier") is not None else None
    )
    return out


def summarize(pooled: dict[str, list[dict]], baseline: str) -> dict:
    targets = sorted({r["target"] for rows in pooled.values() for r in rows})
    out = {}
    for target in targets:
        by_arm = {arm: [r for r in rows if r["target"] == target]
                  for arm, rows in pooled.items()}
        base = by_arm.get(baseline, [])
        out[target] = {
            "metrics": {arm: binary_metrics(rows) for arm, rows in by_arm.items()},
            "vs_baseline": {
                arm: compare(base, rows)
                for arm, rows in by_arm.items()
                if arm != baseline and base and rows
            },
            "state": "DEVELOPMENT_ONLY",
        }
    return out


def run_cohort(panel: list[dict], eligible_key: str, arms: dict[str, str],
               folds: list[dict], minimum: dict, lines: tuple[float, ...],
               target_prefix: str):
    eligible = [r for r in panel if r[eligible_key]]
    pooled = {arm: [] for arm in arms}
    fits, states = [], []
    for fold_id, fold in enumerate(folds, 1):
        train, cal, test = split_fold(eligible, fold)
        counts = {"train": len(train), "calibration": len(cal), "test": len(test)}
        if (len(train) < minimum["minimum_train"]
                or len(cal) < minimum["minimum_calibration"]
                or len(test) < minimum["minimum_test"]):
            states.append({"fold": fold_id, "state": "INSUFFICIENT_SUPPORT",
                           "counts": counts})
            continue
        failures = []
        for arm, key in arms.items():
            try:
                fit, pred = fit_count_arm(key, train, cal, test, lines, target_prefix)
            except (UnsupportedFeatures, ValueError) as exc:
                failures.append({"arm": arm, "reason": str(exc)})
                continue
            fit.update({"arm": arm, "fold": fold_id, **counts})
            fits.append(fit)
            pooled[arm].extend(dict(r, fold=fold_id) for r in pred)
        states.append({"fold": fold_id, "state": "FITTED_DEVELOPMENT",
                       "counts": counts, "failures": failures})
    return eligible, pooled, fits, states
def v3_corner_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        h = r["targets"]["corners.home"]["value"]
        a = r["targets"]["corners.away"]["value"]
        if h is None or a is None:
            continue
        out.append({
            "match_id": r["match_id"],
            "ts": float(r["kickoff_ts"]),
            "home_id": str(r["home_id"]),
            "away_id": str(r["away_id"]),
            "corners_home": h,
            "corners_away": a,
            "competition_id": str(r["competition_id"]),
        })
    return sorted(out, key=lambda x: (x["ts"], x["match_id"]))


def replay_v3_corners(test_predictions: list[dict], rows: list[dict]) -> list[dict]:
    simple = v3_corner_rows(rows)
    by_comp = defaultdict(list)
    for row in simple:
        by_comp[row["competition_id"]].append(row)
    match_meta = {r["match_id"]: r for r in simple}
    # one reference probability row per arm prediction key; deduplicate fixtures/targets
    keys = sorted({(r["match_id"], r["target"], r.get("fold"), r["date"],
                   r["event"]) for r in test_predictions})
    out = []
    cache = {}
    for match_id, target, fold, date, event in keys:
        target_row = match_meta.get(match_id)
        if target_row is None:
            continue
        if match_id not in cache:
            try:
                cache[match_id] = predict_v3_corners(
                    by_comp[target_row["competition_id"]], simple, target_row)
            except V3InsufficientHistory:
                cache[match_id] = None
        art = cache[match_id]
        if art is None:
            continue
        line = float(target.split(">")[1])
        p = float(np.clip(
            poisson.sf(math.floor(line), float(art["lambda_total"])),
            1e-8, 1 - 1e-8))
        out.append({
            "match_id": match_id, "competition_id": target_row["competition_id"],
            "date": date, "target": target, "event": event, "p": p, "fold": fold,
            "loss": float(-event * math.log(p) - (1 - event) * math.log1p(-p)),
        })
    return out
def main():
    spec = json.loads(SPEC.read_text())
    parent = json.loads(PARENT_SPEC.read_text())
    if spec["version"] != "QFE_V33_GOALS_CORNERS_DEVELOPMENT_1":
        raise RuntimeError("unexpected V33 spec")
    if OUTPUT.exists():
        raise RuntimeError("immutable V33 output already exists")

    rows = read_rows()
    folds = parent["folds"]
    minimum = parent["walk_forward"]
    results = {"version": spec["version"], "state": "DEVELOPMENT_ONLY"}

    # Goals: all arms are compared on the same full-deep support cohort.
    goal_panel = prepare_goal_panel(rows)
    g_eligible, g_pooled, g_fits, g_states = run_cohort(
        goal_panel, "eligible_deep",
        {
            "RICH_POISSON": "rich_v33",
            "CHANCE_COMPACT_POISSON": "compact_v33",
            "DEEP_POISSON": "deep",
        },
        folds, minimum, GOAL_LINES, "total",
    )
    gv_eligible, gv_pooled, gv_fits, gv_states = run_cohort(
        goal_panel, "eligible_venue",
        {
            "VENUE_CHANCE_COMPACT_POISSON": "venue_compact_v33",
            "VENUE_DEEP_POISSON": "venue",
        },
        folds, minimum, GOAL_LINES, "total",
    )
    results["goals"] = {
        "deep_support": len(g_eligible),
        "venue_support": len(gv_eligible),
        "full_deep_comparison": {
            "targets": summarize(g_pooled, "RICH_POISSON"),
            "fits": g_fits, "folds": g_states,
        },
        "venue_complexity_ablation": {
            "targets": summarize(gv_pooled, "VENUE_CHANCE_COMPACT_POISSON"),
            "fits": gv_fits, "folds": gv_states,
        },
    }

    # Corners: separate support-matched comparisons prevent coverage confounding.
    corner_panel = build_corner_panel(rows)
    cp_eligible, cp_pooled, cp_fits, cp_states = run_cohort(
        corner_panel, "eligible_pressure",
        {"CORNERS_BASE_POISSON": "base",
         "CORNERS_PRESSURE_POISSON": "pressure"},
        folds, minimum, CORNER_LINES, "total",
    )
    cv_eligible, cv_pooled, cv_fits, cv_states = run_cohort(
        corner_panel, "eligible_venue",
        {"CORNERS_PRESSURE_POISSON": "pressure",
         "CORNERS_VENUE_PRESSURE_POISSON": "venue"},
        folds, minimum, CORNER_LINES, "total",
    )
    ce_eligible, ce_pooled, ce_fits, ce_states = run_cohort(
        corner_panel, "eligible_extended",
        {"CORNERS_PRESSURE_POISSON": "pressure",
         "CORNERS_EXTENDED_POISSON": "extended"},
        folds, minimum, CORNER_LINES, "total",
    )
    v3_replay = replay_v3_corners(
        cv_pooled["CORNERS_VENUE_PRESSURE_POISSON"], rows)
    v3_vs_venue = {}
    for target in sorted({r["target"] for r in v3_replay}):
        base = [r for r in v3_replay if r["target"] == target]
        cand = [r for r in cv_pooled["CORNERS_VENUE_PRESSURE_POISSON"]
                if r["target"] == target]
        v3_vs_venue[target] = compare(base, cand)

    results["corners"] = {
        "panel_n": len(corner_panel),
        "pressure_support": len(cp_eligible),
        "venue_support": len(cv_eligible),
        "extended_support": len(ce_eligible),
        "base_vs_pressure": {
            "targets": summarize(cp_pooled, "CORNERS_BASE_POISSON"),
            "fits": cp_fits, "folds": cp_states,
        },
        "pressure_vs_venue": {
            "targets": summarize(cv_pooled, "CORNERS_PRESSURE_POISSON"),
            "fits": cv_fits, "folds": cv_states,
        },
        "pressure_vs_extended": {
            "targets": summarize(ce_pooled, "CORNERS_PRESSURE_POISSON"),
            "fits": ce_fits, "folds": ce_states,
        },
        "frozen_v3_vs_venue_pressure": v3_vs_venue,
        "v3_replay_n": len({r["match_id"] for r in v3_replay}),
    }
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n")
    support = {
        "goals_deep": len(g_eligible),
        "goals_venue": len(gv_eligible),
        "corners_panel": len(corner_panel),
        "corners_pressure": len(cp_eligible),
        "corners_venue": len(cv_eligible),
        "corners_extended": len(ce_eligible),
    }
    (OUTPUT / "support.json").write_text(
        json.dumps(support, indent=2, sort_keys=True) + "\n")
    manifest = {
        "version": spec["version"], "state": "DEVELOPMENT_ONLY",
        "live_calls": 0, "market_used_for_fit": False, "promotion_count": 0,
        "evidence_sha256": sha(EVIDENCE), "spec_sha256": sha(SPEC),
        "runner_sha256": sha(Path(__file__)),
        "corner_model_sha256": sha(
            ROOT.parents[1] / "src/research/evidence_v32/modeling_v33_corners.py"),
    }
    manifest["files"] = {p.name: sha(p) for p in sorted(OUTPUT.iterdir())}
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(json.dumps({
        "support": support,
        "goals_full": {
            t: d["vs_baseline"] for t, d in
            results["goals"]["full_deep_comparison"]["targets"].items()
        },
        "goals_venue_ablation": {
            t: d["vs_baseline"] for t, d in
            results["goals"]["venue_complexity_ablation"]["targets"].items()
        },
        "corners_pressure": {
            t: d["vs_baseline"] for t, d in
            results["corners"]["base_vs_pressure"]["targets"].items()
        },
        "corners_venue": {
            t: d["vs_baseline"] for t, d in
            results["corners"]["pressure_vs_venue"]["targets"].items()
        },
        "corners_extended": {
            t: d["vs_baseline"] for t, d in
            results["corners"]["pressure_vs_extended"]["targets"].items()
        },
        "frozen_v3_vs_venue": results["corners"]["frozen_v3_vs_venue_pressure"],
    }, indent=2))


if __name__ == "__main__":
    main()
