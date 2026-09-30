"""V3.4 exact-reference stacking experiment. Offline, development-only."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import poisson

from src.research.evidence_v32.modeling import binary_metrics, paired_gain
from src.research.evidence_v32.modeling_v322 import (
    COMPLETION_BUFFER_SECONDS, LinearCount, count_scales, side_design,
)
from src.research.evidence_v32.modeling_v323 import build_venue_panel
from src.research.evidence_v32.modeling_v33_corners import build_corner_panel
from src.research.v3_pilot.model import (
    InsufficientHistory as V3InsufficientHistory,
    _dc_lambdas, _dc_matrix, _p_total_over, apply_platt, fit_dc,
    fit_goal_calibrators, predict_corners as predict_v3_corners,
)

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "SPEC_V34_STACKING.json"
PARENT_SPEC = ROOT / "SPEC_V32_2.json"
EVIDENCE = ROOT / "out/evidence_v2/evidence.jsonl"
OUTPUT = ROOT / "out/model_stacking_v34"

GOAL_LINES = (2.5, 3.5)
CORNER_LINES = (8.5, 9.5, 10.5)


def read_rows():
    return [json.loads(x) for x in EVIDENCE.read_text().splitlines() if x.strip()]


def split_fold(rows: list[dict], fold: dict):
    rows = sorted(rows, key=lambda r: (r["kickoff_ts"], r["match_id"]))
    groups = sorted({float(r["kickoff_ts"]) for r in rows})
    if len(groups) < 10:
        return [], [], []

    def boundary(frac):
        idx = min(max(int(math.ceil(len(groups) * frac)) - 1, 0), len(groups) - 1)
        return groups[idx]

    a, b, c = (boundary(fold[k]) for k in ("train_end", "cal_end", "test_end"))
    train = [r for r in rows if r["kickoff_ts"] <= a]
    cal = [r for r in rows if a < r["kickoff_ts"] <= b]
    test = [r for r in rows if b < r["kickoff_ts"] <= c]
    if cal:
        first = min(r["cutoff_ts"] for r in cal)
        train = [r for r in train if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first]
    if test:
        first = min(r["cutoff_ts"] for r in test)
        cal = [r for r in cal if r["kickoff_ts"] + COMPLETION_BUFFER_SECONDS < first]
    return train, cal, test


def _clip(p):
    return float(np.clip(p, 1e-8, 1 - 1e-8))


def _logit(p):
    p = _clip(p)
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-max(min(float(x), 35.0), -35.0)))


def fit_stack_weight(reference: list[dict], challenger: list[dict]) -> float:
    cref = {(r["match_id"], r["target"]): r for r in reference}
    pairs = [(cref[(r["match_id"], r["target"])], r)
             for r in challenger if (r["match_id"], r["target"]) in cref]
    if not pairs:
        raise ValueError("no common calibration predictions")

    def loss(w):
        total = 0.0
        for a, b in pairs:
            z = (1 - w) * _logit(a["p"]) + w * _logit(b["p"])
            p = _clip(_sigmoid(z))
            y = int(a["event"])
            total += -y * math.log(p) - (1 - y) * math.log1p(-p)
        return total / len(pairs)

    res = minimize_scalar(loss, bounds=(0.0, 1.0), method="bounded",
                          options={"xatol": 1e-6, "maxiter": 200})
    return float(np.clip(res.x, 0.0, 1.0))


def stack_predictions(reference: list[dict], challenger: list[dict], weight: float,
                      fold: int) -> tuple[list[dict], list[dict], list[dict]]:
    cref = {(r["match_id"], r["target"]): r for r in reference}
    aout, bout, sout = [], [], []
    for b in challenger:
        key = (b["match_id"], b["target"])
        a = cref.get(key)
        if a is None:
            continue
        z = (1 - weight) * _logit(a["p"]) + weight * _logit(b["p"])
        p = _clip(_sigmoid(z))
        y = int(a["event"])
        common = {
            "match_id": a["match_id"], "competition_id": a["competition_id"],
            "date": a["date"], "target": a["target"], "event": y, "fold": fold,
        }
        aa = {**common, "p": _clip(a["p"])}
        bb = {**common, "p": _clip(b["p"])}
        ss = {**common, "p": p}
        for row in (aa, bb, ss):
            row["loss"] = float(-y * math.log(row["p"]) -
                                (1-y) * math.log1p(-row["p"]))
        aout.append(aa); bout.append(bb); sout.append(ss)
    return aout, bout, sout
def fit_count_parent(key: str, train: list[dict], cal: list[dict], test: list[dict],
                     lines: tuple[float, ...], prefix: str):
    ytrain = np.asarray([r["y"] for r in train], float)
    ycal = np.asarray([r["y"] for r in cal], float)
    model = LinearCount(side_design(train, key), ytrain.ravel())
    cal_raw = model.predict(side_design(cal, key)).reshape(-1, 2)
    scales = count_scales(cal_raw, ycal)

    def predict(rows):
        means = model.predict(side_design(rows, key)).reshape(-1, 2) * scales[None, :]
        out = []
        for row, pair in zip(rows, means):
            total_mean = float(pair[0] + pair[1])
            actual_total = int(row["y"][0] + row["y"][1])
            for line in lines:
                p = _clip(poisson.sf(math.floor(line), total_mean))
                y = int(actual_total > line)
                out.append({
                    "match_id": row["match_id"],
                    "competition_id": row["competition_id"],
                    "date": row["date"],
                    "target": f"{prefix}>{line}", "event": y, "p": p,
                })
        return out
    return predict(cal), predict(test), [float(x) for x in scales]


def v3_goal_rows(rows: list[dict]) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        h = r["targets"]["goals.home"]["value"]
        a = r["targets"]["goals.away"]["value"]
        if h is None or a is None:
            continue
        out[str(r["competition_id"])].append({
            "match_id": str(r["match_id"]), "ts": float(r["kickoff_ts"]),
            "home_id": str(r["home_id"]), "away_id": str(r["away_id"]),
            "season_id": str(r.get("season_id") or ""),
            "score": {"home": int(h), "away": int(a)},
        })
    for comp in out:
        out[comp].sort(key=lambda r: (r["ts"], r["match_id"]))
    return out


def replay_v3_goals(target_rows: list[dict], all_rows: list[dict]) -> tuple[dict, dict]:
    histories = v3_goal_rows(all_rows)
    targets = {r["match_id"]: r for r in target_rows}
    needed = defaultdict(list)
    for r in targets.values():
        needed[str(r["competition_id"])].append(r)

    predictions = {}
    diagnostics = {"supported": 0, "unsupported": 0, "unsupported_reasons": defaultdict(int),
                   "calibrators": {}, "dc_fits": 0}

    for comp, rows_needed in needed.items():
        history = histories.get(comp, [])
        by_season = defaultdict(list)
        for r in rows_needed:
            by_season[str(r.get("season_id") or "")].append(r)

        cal_cache = {}
        for season, season_targets in by_season.items():
            first_ts = min(float(r["kickoff_ts"]) for r in season_targets)
            hist_before = [h for h in history if h["ts"] < first_ts]
            try:
                cal_cache[season] = fit_goal_calibrators(hist_before, season)
                diagnostics["calibrators"][f"{comp}:{season}"] = (
                    cal_cache[season]["calibration_season_id"])
            except Exception as exc:
                cal_cache[season] = exc
                diagnostics["unsupported_reasons"][f"calibrator:{type(exc).__name__}"] += len(season_targets)

        by_ts = defaultdict(list)
        for r in rows_needed:
            by_ts[float(r["kickoff_ts"])].append(r)
        for ts, group in sorted(by_ts.items()):
            supported_group = [r for r in group if not isinstance(
                cal_cache.get(str(r.get("season_id") or "")), Exception)]
            if not supported_group:
                diagnostics["unsupported"] += len(group)
                continue
            try:
                model = fit_dc(history, ts)
                diagnostics["dc_fits"] += 1
            except Exception as exc:
                diagnostics["unsupported"] += len(group)
                diagnostics["unsupported_reasons"][f"dc:{type(exc).__name__}"] += len(group)
                continue

            for r in group:
                season = str(r.get("season_id") or "")
                cal = cal_cache.get(season)
                if isinstance(cal, Exception) or cal is None:
                    diagnostics["unsupported"] += 1
                    continue
                lh, la = _dc_lambdas(model, str(r["home_id"]), str(r["away_id"]))
                P = _dc_matrix(lh, la, float(model["rho"]))
                actual = int(r["y"][0] + r["y"][1])
                for line in GOAL_LINES:
                    raw = _p_total_over(P, line)
                    p = _clip(apply_platt(cal["calibrators"][str(line)], raw))
                    predictions[(r["match_id"], f"total>{line}")] = {
                        "match_id": r["match_id"], "competition_id": comp,
                        "date": r["date"], "target": f"total>{line}",
                        "event": int(actual > line), "p": p,
                    }
                diagnostics["supported"] += 1
    diagnostics["unsupported_reasons"] = dict(diagnostics["unsupported_reasons"])
    return predictions, diagnostics
def corner_history_rows(rows: list[dict]) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        h = r["targets"]["corners.home"]["value"]
        a = r["targets"]["corners.away"]["value"]
        if h is None or a is None:
            continue
        comp = str(r["competition_id"])
        out[comp].append({
            "match_id": r["match_id"], "ts": float(r["kickoff_ts"]),
            "home_id": str(r["home_id"]), "away_id": str(r["away_id"]),
            "competition_id": comp, "corners_home": h, "corners_away": a,
        })
    for comp in out:
        out[comp].sort(key=lambda r: (r["ts"], r["match_id"]))
    return out


def replay_v3_corners(target_rows: list[dict], all_rows: list[dict]) -> tuple[dict, dict]:
    histories = corner_history_rows(all_rows)
    cache = {}
    diagnostics = {"supported": 0, "unsupported": 0}
    for r in target_rows:
        mid = r["match_id"]
        if mid in cache:
            continue
        comp = str(r["competition_id"])
        target = {
            "match_id": mid, "ts": float(r["kickoff_ts"]),
            "home_id": str(r["home_id"]), "away_id": str(r["away_id"]),
            "competition_id": comp,
        }
        try:
            # Exact production semantics: both comp_rows and fallback rows are the
            # same competition-specific history supplied by V3Provider.
            art = predict_v3_corners(histories[comp], histories[comp], target)
        except V3InsufficientHistory:
            diagnostics["unsupported"] += 1
            continue
        actual = int(r["y"][0] + r["y"][1])
        for line in CORNER_LINES:
            p = _clip(poisson.sf(math.floor(line), float(art["lambda_total"])))
            cache[(mid, f"total>{line}")] = {
                "match_id": mid, "competition_id": comp, "date": r["date"],
                "target": f"total>{line}", "event": int(actual > line), "p": p,
            }
        diagnostics["supported"] += 1
    return cache, diagnostics


def lookup_predictions(cache: dict, rows: list[dict], lines: tuple[float, ...]) -> list[dict]:
    out = []
    mids = {r["match_id"] for r in rows}
    for mid in mids:
        for line in lines:
            row = cache.get((mid, f"total>{line}"))
            if row is not None:
                out.append(row)
    return out
def summarize_parent_stack(reference, challenger, stack):
    return {
        "reference": binary_metrics(reference),
        "challenger": binary_metrics(challenger),
        "stack": binary_metrics(stack),
        "stack_vs_reference": paired_gain(reference, stack, seed=3400),
        "stack_vs_challenger": paired_gain(challenger, stack, seed=3400),
    }


def run_family(panel, eligibility, key, lines, all_rows, replay_fn, folds, minimum):
    eligible = [r for r in panel if r[eligibility]]
    all_needed = []
    fold_splits = []
    for fold_id, fold in enumerate(folds, 1):
        train, cal, test = split_fold(eligible, fold)
        fold_splits.append((fold_id, train, cal, test))
        all_needed.extend(cal); all_needed.extend(test)
    unique_needed = list({r["match_id"]: r for r in all_needed}.values())
    reference_cache, replay_diag = replay_fn(unique_needed, all_rows)

    pooled = defaultdict(lambda: defaultdict(list))
    fold_results = []
    for fold_id, train, cal, test in fold_splits:
        counts = {"train": len(train), "calibration": len(cal), "test": len(test)}
        if (len(train) < minimum["minimum_train"]
                or len(cal) < minimum["minimum_calibration"]
                or len(test) < minimum["minimum_test"]):
            fold_results.append({"fold": fold_id, "state": "INSUFFICIENT_SUPPORT",
                                 "counts": counts})
            continue

        chal_cal, chal_test, scales = fit_count_parent(
            key, train, cal, test, lines, "total")
        ref_cal = lookup_predictions(reference_cache, cal, lines)
        ref_test = lookup_predictions(reference_cache, test, lines)

        line_results = {}
        for line in lines:
            target = f"total>{line}"
            rc = [r for r in ref_cal if r["target"] == target]
            cc = [r for r in chal_cal if r["target"] == target]
            rt = [r for r in ref_test if r["target"] == target]
            ct = [r for r in chal_test if r["target"] == target]
            if not rc or not cc or not rt or not ct:
                line_results[target] = {"state": "UNSUPPORTED_COMMON"}
                continue
            w = fit_stack_weight(rc, cc)
            ra, cb, ss = stack_predictions(rt, ct, w, fold_id)
            pooled[target]["reference"].extend(ra)
            pooled[target]["challenger"].extend(cb)
            pooled[target]["stack"].extend(ss)
            line_results[target] = {
                "state": "FITTED_DEVELOPMENT", "weight_challenger": w,
                "calibration_common_n": len(stack_predictions(rc, cc, w, fold_id)[2]),
                "test_common_n": len(ss),
            }
        fold_results.append({
            "fold": fold_id, "state": "FITTED_DEVELOPMENT", "counts": counts,
            "parent_count_scales": scales, "lines": line_results,
        })

    results = {}
    for target, arms in pooled.items():
        results[target] = summarize_parent_stack(
            arms["reference"], arms["challenger"], arms["stack"])
        results[target]["fold_weights"] = [
            fr["lines"][target]["weight_challenger"]
            for fr in fold_results
            if fr.get("lines", {}).get(target, {}).get("state") == "FITTED_DEVELOPMENT"
        ]
        results[target]["state"] = "DEVELOPMENT_ONLY"
    return {
        "eligible_n": len(eligible), "reference_replay": replay_diag,
        "folds": fold_results, "targets": results,
    }
def main():
    spec = json.loads(SPEC.read_text())
    parent = json.loads(PARENT_SPEC.read_text())
    if spec["version"] != "QFE_V34_STACKING_DEVELOPMENT_1":
        raise RuntimeError("unexpected V34 spec")
    if OUTPUT.exists():
        raise RuntimeError("immutable V34 output already exists")

    rows = read_rows()
    folds = parent["folds"]
    minimum = parent["walk_forward"]

    meta = {r["match_id"]: r for r in rows}
    goals_panel = build_venue_panel(rows)
    for row in goals_panel:
        source = meta[row["match_id"]]
        row["home_id"] = str(source["home_id"])
        row["away_id"] = str(source["away_id"])
        row["season_id"] = str(source.get("season_id") or "")
    goals = run_family(
        goals_panel, "eligible_venue", "venue", GOAL_LINES,
        rows, replay_v3_goals, folds, minimum)

    corner_panel = build_corner_panel(rows)
    corners = run_family(
        corner_panel, "eligible_pressure", "pressure", CORNER_LINES,
        rows, replay_v3_corners, folds, minimum)

    results = {
        "version": spec["version"], "state": "DEVELOPMENT_ONLY",
        "goals": goals, "corners": corners,
    }
    OUTPUT.mkdir(parents=True)
    (OUTPUT / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n")
    (OUTPUT / "summary.json").write_text(json.dumps({
        "goals": {
            t: {
                "reference_ll": d["reference"]["log_loss"],
                "challenger_ll": d["challenger"]["log_loss"],
                "stack_ll": d["stack"]["log_loss"],
                "weights": d["fold_weights"],
                "stack_vs_reference": d["stack_vs_reference"],
                "stack_vs_challenger": d["stack_vs_challenger"],
            } for t, d in goals["targets"].items()
        },
        "corners": {
            t: {
                "reference_ll": d["reference"]["log_loss"],
                "challenger_ll": d["challenger"]["log_loss"],
                "stack_ll": d["stack"]["log_loss"],
                "weights": d["fold_weights"],
                "stack_vs_reference": d["stack_vs_reference"],
                "stack_vs_challenger": d["stack_vs_challenger"],
            } for t, d in corners["targets"].items()
        }
    }, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print((OUTPUT / "summary.json").read_text())


if __name__ == "__main__":
    main()
