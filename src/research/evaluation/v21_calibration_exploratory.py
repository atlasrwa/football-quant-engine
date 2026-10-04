"""Exploratory V2.1 calibration tournament on already-exposed CALIBRATION data."""
from __future__ import annotations

import hashlib
import json
from math import log
from pathlib import Path
from typing import Any

import numpy as np

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.evaluation.chronology import PROTECTED_START_TS
from src.research.layer4.calibration_run import load_raw_rows
from src.research.layer4.calibrators import (
    BetaGlobal,
    IdentityCalibrator,
    PlattGlobal,
    WeightedIsotonic,
    calibrator_from_spec,
    weighted_brier,
    weighted_log_loss,
)
from src.research.models.v21_monotone_calibration import (
    MonotoneLogitSpline,
    PlattIsotonicBlend,
    assert_monotone_transform,
)

VERSION = "qfe-v21-calibration-exploratory-v1"
GROUPS = ("GOALS_TOTAL", "CORNERS_SIDE", "CORNERS_TOTAL")


def _read_json(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _arrays(rows):
    return (
        [float(r["raw_probability"]) for r in rows],
        [bool(r["outcome_over"]) for r in rows],
        [float(r["sample_weight"]) for r in rows],
    )


def _apply(calibrator, rows):
    return [
        float(
            calibrator.transform(
                float(r["raw_probability"]),
                role=r.get("role"),
                competition_ref=r.get("competition_ref"),
            )
        )
        for r in rows
    ]


def _metrics(calibrator, rows):
    probs = _apply(calibrator, rows)
    _, outcomes, weights = _arrays(rows)
    return {
        "log_loss": weighted_log_loss(probs, outcomes, weights),
        "brier": weighted_brier(probs, outcomes, weights),
    }


def _row_losses(calibrator, rows):
    probs = _apply(calibrator, rows)
    out = []
    for r, p in zip(rows, probs, strict=True):
        y = bool(r["outcome_over"])
        w = float(r["sample_weight"])
        q = min(max(float(p), 1e-12), 1.0 - 1e-12)
        ll = -log(q if y else 1.0 - q)
        br = (q - float(y)) ** 2
        out.append(
            {
                "week": int(r["kickoff_ts"]) // 604800,
                "weight": w,
                "log_loss": ll,
                "brier": br,
            }
        )
    return out


def _paired_week_bootstrap(reference, challenger, rows, *, seed, replicates):
    ref = _row_losses(reference, rows)
    chal = _row_losses(challenger, rows)
    blocks = {}
    for a, b in zip(ref, chal, strict=True):
        if a["week"] != b["week"] or a["weight"] != b["weight"]:
            raise ValueError("paired loss rows misaligned")
        block = blocks.setdefault(
            a["week"],
            {"w": 0.0, "ll": 0.0, "br": 0.0},
        )
        w = a["weight"]
        block["w"] += w
        block["ll"] += w * (a["log_loss"] - b["log_loss"])
        block["br"] += w * (a["brier"] - b["brier"])
    values = list(blocks.values())
    if not values:
        raise ValueError("no bootstrap blocks")

    total_w = sum(v["w"] for v in values)
    point_ll = sum(v["ll"] for v in values) / total_w
    point_br = sum(v["br"] for v in values) / total_w
    rng = np.random.default_rng(seed)
    ll_boot = []
    br_boot = []
    n = len(values)
    for _ in range(int(replicates)):
        indices = rng.integers(0, n, size=n)
        den = sum(values[i]["w"] for i in indices)
        ll_boot.append(sum(values[i]["ll"] for i in indices) / den)
        br_boot.append(sum(values[i]["br"] for i in indices) / den)

    def summary(name, point, boot):
        return {
            "metric": name,
            "mean_reference_minus_challenger": float(point),
            "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)),
            "bootstrap_probability_positive": float(
                np.mean(np.asarray(boot) > 0)
            ),
            "replicates": int(replicates),
            "n_week_blocks": n,
            "seed": int(seed),
        }

    return {
        "log_loss": summary("log_loss", point_ll, ll_boot),
        "brier": summary("brier", point_br, br_boot),
    }


def _assert_ladder_coherence(calibrator, rows):
    grouped = {}
    for row, probability in zip(rows, _apply(calibrator, rows), strict=True):
        key = (
            row["fixture_key"],
            row["group"],
            row.get("role"),
        )
        grouped.setdefault(key, []).append(
            (float(row["line"]), float(probability))
        )
    for key, values in grouped.items():
        values.sort()
        probs = [p for _, p in values]
        if any(
            probs[i + 1] > probs[i] + 1e-12
            for i in range(len(probs) - 1)
        ):
            raise ValueError(f"non-monotone calibrated ladder: {key}")


def _fit_comparators(fit_rows, eps):
    p, y, w = _arrays(fit_rows)
    return {
        "IDENTITY": IdentityCalibrator(),
        "PLATT_GLOBAL": PlattGlobal.fit(p, y, w, eps),
        "BETA_GLOBAL": BetaGlobal.fit(p, y, w, eps),
        "ISOTONIC_GLOBAL": WeightedIsotonic.fit(p, y, w),
    }


def _select_family(records, family, reference_brier):
    eligible = [
        r for r in records
        if r["family"] == family
        and r["metrics"]["brier"] <= reference_brier + 0.001
    ]
    if not eligible:
        return None
    best_ll = min(r["metrics"]["log_loss"] for r in eligible)
    tied = [
        r for r in eligible
        if r["metrics"]["log_loss"] <= best_ll + 0.0005
    ]
    if family == "PLATT_ISOTONIC_BLEND":
        return min(tied, key=lambda r: float(r["parameter_value"]))
    if family == "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE":
        return max(tied, key=lambda r: float(r["parameter_value"]))
    raise ValueError(family)


def run_exploratory_calibration(*, repo_root):
    repo_root = Path(repo_root)
    protocol_path = repo_root / "research/qfe_v21_calibration/PROTOCOL_V1.json"
    protocol = _read_json(protocol_path)
    protocol_hash = sha256_json(protocol)
    if protocol["version"] != "QFE_V21_CALIBRATION_EXPLORATORY_V1":
        raise ValueError("protocol mismatch")

    raw_summary, rows = load_raw_rows(repo_root)
    if any(int(r["kickoff_ts"]) >= PROTECTED_START_TS for r in rows):
        raise ValueError("protected outcome leaked into calibration research")

    frozen = _read_json(
        repo_root / "evidence/layer4/QFE_LAYER4_CALIBRATION_V1.json"
    )
    frozen_by_group = {
        r["group"]: r for r in frozen["group_results"]
    }
    eps = 1e-6
    seed = int(protocol["evaluation"]["bootstrap_seed"])
    reps = int(protocol["evaluation"]["bootstrap_replicates"])
    group_results = []

    for group in GROUPS:
        group_rows = [r for r in rows if r["group"] == group]
        fit_rows = [r for r in group_rows if r["phase"] == "CALIBRATION_FIT"]
        select_rows = [
            r for r in group_rows
            if r["phase"] == "CALIBRATION_SELECT"
        ]
        if not fit_rows or not select_rows:
            raise ValueError(f"missing calibration phase for {group}")

        frozen_spec = frozen_by_group[group]["selected_fit_window_spec"]
        reference = calibrator_from_spec(frozen_spec)
        reference_metrics = _metrics(reference, select_rows)
        comparators = _fit_comparators(fit_rows, eps)

        comparator_records = []
        for name, calibrator in comparators.items():
            _assert_ladder_coherence(calibrator, select_rows)
            comparator_records.append(
                {
                    "candidate": name,
                    "spec": calibrator.to_spec(),
                    "metrics": _metrics(calibrator, select_rows),
                }
            )

        p, y, w = _arrays(fit_rows)
        candidates = []
        blend_cfg = protocol["candidate_families"]["PLATT_ISOTONIC_BLEND"]
        for alpha in blend_cfg["alpha_grid"]:
            calibrator = PlattIsotonicBlend.fit(
                p,
                y,
                w,
                alpha=float(alpha),
                eps=eps,
            )
            assert_monotone_transform(calibrator)
            _assert_ladder_coherence(calibrator, select_rows)
            candidates.append(
                {
                    "candidate": f"PLATT_ISOTONIC_BLEND_A{alpha}",
                    "family": "PLATT_ISOTONIC_BLEND",
                    "parameter_name": "alpha",
                    "parameter_value": float(alpha),
                    "spec": calibrator.to_spec(),
                    "metrics": _metrics(calibrator, select_rows),
                    "paired_vs_frozen_reference": _paired_week_bootstrap(
                        reference,
                        calibrator,
                        select_rows,
                        seed=seed,
                        replicates=reps,
                    ),
                }
            )

        spline_cfg = protocol["candidate_families"][
            "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE"
        ]
        for ridge in spline_cfg["ridge_grid"]:
            calibrator = MonotoneLogitSpline.fit(
                p,
                y,
                w,
                eps=eps,
                ridge_lambda=float(ridge),
                curvature_multiplier=float(
                    spline_cfg["curvature_multiplier"]
                ),
                quantiles=(0.0,0.2,0.4,0.6,0.8,1.0),
                minimum_logit_increment=float(
                    spline_cfg["minimum_logit_increment"]
                ),
            )
            assert_monotone_transform(calibrator)
            _assert_ladder_coherence(calibrator, select_rows)
            candidates.append(
                {
                    "candidate": f"MONOTONE_LOGIT_SPLINE_R{ridge}",
                    "family": "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE",
                    "parameter_name": "ridge_lambda",
                    "parameter_value": float(ridge),
                    "spec": calibrator.to_spec(),
                    "metrics": _metrics(calibrator, select_rows),
                    "paired_vs_frozen_reference": _paired_week_bootstrap(
                        reference,
                        calibrator,
                        select_rows,
                        seed=seed,
                        replicates=reps,
                    ),
                }
            )

        selected_blend = _select_family(
            candidates,
            "PLATT_ISOTONIC_BLEND",
            reference_metrics["brier"],
        )
        selected_spline = _select_family(
            candidates,
            "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE",
            reference_metrics["brier"],
        )
        selected = {
            "PLATT_ISOTONIC_BLEND": (
                selected_blend["candidate"] if selected_blend else None
            ),
            "PLATT_CENTERED_MONOTONE_LOGIT_SPLINE": (
                selected_spline["candidate"] if selected_spline else None
            ),
        }
        promising = []
        for record in (selected_blend, selected_spline):
            if (
                record is not None
                and record["metrics"]["log_loss"]
                < reference_metrics["log_loss"]
                and record["metrics"]["brier"]
                <= reference_metrics["brier"]
            ):
                promising.append(record["candidate"])

        group_results.append(
            {
                "group": group,
                "fit_unique_fixtures": len(
                    {r["fixture_key"] for r in fit_rows}
                ),
                "select_unique_fixtures": len(
                    {r["fixture_key"] for r in select_rows}
                ),
                "frozen_v2_reference": {
                    "selected_candidate": frozen_by_group[group][
                        "selected_candidate"
                    ],
                    "fit_window_spec": frozen_spec,
                    "metrics": reference_metrics,
                },
                "comparators": comparator_records,
                "challengers": candidates,
                "family_research_selections": selected,
                "promising_for_fresh_future_holdout": promising,
                "production_promotion_allowed": False,
            }
        )

    result = {
        "version": VERSION,
        "scientific_status": (
            "EXPLORATORY_CALIBRATION_SELECT_PREVIOUSLY_EXPOSED_"
            "PROTECTED_UNOPENED_NO_MARKET"
        ),
        "protocol_hash": protocol_hash,
        "raw_calibration_hash": raw_summary["raw_calibration_hash"],
        "frozen_layer4_calibration_run_hash": frozen[
            "calibration_run_hash"
        ],
        "boundaries": {
            "protected_outcomes_read": False,
            "market_odds_used": False,
            "network_calls": 0,
            "llm_calls": 0,
            "production_p_model_modified": False,
            "calibration_select_confirmatory": False,
        },
        "group_results": group_results,
    }
    implementation = [
        "src/research/models/v21_monotone_calibration.py",
        "src/research/evaluation/v21_calibration_exploratory.py",
        "research/qfe_v21_calibration/PROTOCOL_V1.json",
    ]
    result["implementation_sha256"] = {
        rel: hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()
        for rel in implementation
    }
    result["result_hash"] = sha256_json(result)
    return result


def render_markdown(result):
    lines = [
        "# QFE V2.1 — Exploratory Calibration Result V1",
        "",
        f"Result hash: {result['result_hash']}",
        "",
        "> Exploratory only: CALIBRATION_SELECT was already exposed by Layer 4 V1.",
        "> PROTECTED outcomes remain unopened and no production calibrator is changed.",
        "",
    ]
    for group in result["group_results"]:
        ref = group["frozen_v2_reference"]
        lines += [
            f"## {group['group']}",
            "",
            f"Frozen V2 reference: **{ref['selected_candidate']}**",
            f"Reference LL: **{ref['metrics']['log_loss']:.6f}**",
            f"Reference Brier: **{ref['metrics']['brier']:.6f}**",
            "",
            "| Challenger | SELECT LL | SELECT Brier | ΔLL vs V2 | ΔBrier vs V2 |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in group["challengers"]:
            dm = (
                row["metrics"]["log_loss"]
                - ref["metrics"]["log_loss"]
            )
            db = row["metrics"]["brier"] - ref["metrics"]["brier"]
            lines.append(
                f"| {row['candidate']} | "
                f"{row['metrics']['log_loss']:.6f} | "
                f"{row['metrics']['brier']:.6f} | "
                f"{dm:+.6f} | {db:+.6f} |"
            )
        lines += [
            "",
            "Research selections: "
            + json.dumps(group["family_research_selections"], sort_keys=True),
            "",
            "Promising only for a fresh future holdout: "
            + (
                ", ".join(group["promising_for_fresh_future_holdout"])
                if group["promising_for_fresh_future_holdout"]
                else "**none**"
            ),
            "",
        ]
    return "\n".join(lines) + "\n"


def write_result(*, repo_root, result):
    repo_root = Path(repo_root)
    out_dir = repo_root / "research/qfe_v21_calibration"
    json_path = out_dir / "RESULT_V1.json"
    md_path = out_dir / "RESULT_V1.md"
    payloads = (
        (json_path, canonical_json(result) + "\n"),
        (md_path, render_markdown(result)),
    )
    for path, payload in payloads:
        if path.exists() and path.read_text() != payload:
            raise FileExistsError(path)
        if not path.exists():
            path.write_text(payload)
