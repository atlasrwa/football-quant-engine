"""QFE V2.1 chronological regularized linear-pool ensemble research.

The ensemble operates on immutable DEVELOPMENT OOF component probabilities.
Weights are non-negative, sum to one, and are regularized toward the frozen
V2 anchor. Ridge strength is selected through expanding chronological
validation: D1->D2, D1-D2->D3, D1-D3->D4.

CALIBRATION and PROTECTED outcomes are not read.
"""
from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
from math import log
from pathlib import Path
from statistics import mean
from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.evaluation.paired_uncertainty import paired_block_bootstrap

RESULT_VERSION = "qfe-v21-regularized-linear-pool-stage1-v1"
FOLD_ORDER = {"D1": 1, "D2": 2, "D3": 3, "D4": 4}
STRUCTURED_PATH = Path("evidence/layer3/STRUCTURED_DEVELOPMENT_OOF.json")
SIMILAR_PATH = Path("evidence/layer3/SIMILAR_CONTEXT_DEVELOPMENT_OOF.json")
L31_PATH = Path(
    "evidence/layer31/QFE_LAYER31_CORNERS_MULTILINE_OOF_ROWS.jsonl.gz"
)
V3_PATH = Path("research/qfe_v21_state_space/ROWS_V3.jsonl.gz")


@dataclass(frozen=True, slots=True)
class EventCell:
    fixture_key: str
    kickoff_ts: int
    fold_id: str
    outcome: bool
    probabilities: tuple[float, ...]
    cell_weight: float


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_gzip_rows(path: Path) -> list[dict[str, Any]]:
    raw = gzip.decompress(path.read_bytes()).decode()
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _clip_probability(p: float) -> float:
    return min(max(float(p), 1e-12), 1.0 - 1e-12)


def _cell_loss(p: float, outcome: bool) -> float:
    p = _clip_probability(p)
    return float(-log(p if outcome else 1.0 - p))


def _fixture_scores(
    cells: list[EventCell],
    weights: np.ndarray,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for cell in cells:
        if len(cell.probabilities) != len(weights):
            raise ValueError("component/weight dimension mismatch")
        p = float(np.dot(weights, np.asarray(cell.probabilities, dtype=float)))
        p = _clip_probability(p)
        row = grouped.setdefault(
            cell.fixture_key,
            {
                "fixture_key": cell.fixture_key,
                "kickoff_ts": cell.kickoff_ts,
                "fold_id": cell.fold_id,
                "log_loss": 0.0,
                "brier": 0.0,
                "weight_sum": 0.0,
            },
        )
        if row["kickoff_ts"] != cell.kickoff_ts or row["fold_id"] != cell.fold_id:
            raise ValueError("fixture metadata drift")
        row["log_loss"] += cell.cell_weight * _cell_loss(p, cell.outcome)
        row["brier"] += cell.cell_weight * (
            p - float(cell.outcome)
        ) ** 2
        row["weight_sum"] += cell.cell_weight
    rows = []
    for row in grouped.values():
        if abs(float(row["weight_sum"]) - 1.0) > 1e-9:
            raise ValueError(
                f"fixture cell weights do not sum to one: {row['fixture_key']}"
            )
        rows.append(row)
    rows.sort(key=lambda r: (r["kickoff_ts"], r["fixture_key"]))
    return rows


def fit_regularized_simplex(
    cells: list[EventCell],
    *,
    anchor_weights: list[float],
    ridge_lambda: float,
) -> np.ndarray:
    """Fit a convex linear pool under fixture-balanced Log Loss."""
    if not cells:
        raise ValueError("cannot fit ensemble on empty cells")
    anchor = np.asarray(anchor_weights, dtype=float)
    if np.any(anchor < 0) or abs(float(anchor.sum()) - 1.0) > 1e-9:
        raise ValueError("anchor weights must lie on simplex")
    n_components = len(anchor)
    if any(len(cell.probabilities) != n_components for cell in cells):
        raise ValueError("component count mismatch")

    n_fixtures = len({cell.fixture_key for cell in cells})

    def objective(weights: np.ndarray) -> float:
        total = 0.0
        for cell in cells:
            p = float(
                np.dot(
                    weights,
                    np.asarray(cell.probabilities, dtype=float),
                )
            )
            total += cell.cell_weight * _cell_loss(p, cell.outcome)
        data_loss = total / n_fixtures
        penalty = float(ridge_lambda) * float(
            np.dot(weights - anchor, weights - anchor)
        )
        return float(data_loss + penalty)

    result = minimize(
        objective,
        anchor.copy(),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n_components,
        constraints=[
            {
                "type": "eq",
                "fun": lambda weights: float(np.sum(weights) - 1.0),
            }
        ],
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"ensemble optimizer failed: {result.message}")
    weights = np.clip(np.asarray(result.x, dtype=float), 0.0, 1.0)
    weights /= weights.sum()
    return weights


def _mean_scores(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        raise ValueError("empty score rows")
    return {
        "n_fixtures": len(rows),
        "log_loss": float(mean(float(row["log_loss"]) for row in rows)),
        "brier": float(mean(float(row["brier"]) for row in rows)),
    }


def _goals_cells(repo_root: Path) -> list[EventCell]:
    structured = _load_json(repo_root / STRUCTURED_PATH)
    similar = _load_json(repo_root / SIMILAR_PATH)
    v3 = _load_gzip_rows(repo_root / V3_PATH)

    dynamic = {
        row["fixture_key"]: row
        for row in structured["rows"]
        if row["target"] == "goals"
        and row["candidate"] == "dynamic_poisson"
    }
    sim = {
        row["fixture_key"]: row
        for row in similar["rows"]
        if row["target"] == "goals"
    }
    local = {
        row["fixture_key"]: row
        for row in v3
        if row["target"] == "goals"
    }
    keys = sorted(
        set(dynamic) & set(sim) & set(local),
        key=lambda key: (dynamic[key]["kickoff_ts"], key),
    )
    if not keys:
        raise ValueError("no paired goals ensemble rows")
    cells = []
    for key in keys:
        d = dynamic[key]
        s = sim[key]
        c = local[key]
        if d["fold_id"] != s["fold_id"] or d["fold_id"] != c["fold_id"]:
            raise ValueError("goals fold mismatch")
        if int(d["observed_total"]) != int(c["total_observed"]):
            raise ValueError("goals outcome mismatch")
        p_dynamic = float(d["probability_over"])
        p_similar = float(poisson.sf(2, float(s["expected_total"])))
        p_local = float(c["CANDIDATE"]["probability_over"])
        cells.append(
            EventCell(
                fixture_key=key,
                kickoff_ts=int(d["kickoff_ts"]),
                fold_id=str(d["fold_id"]),
                outcome=int(d["observed_total"]) > 2,
                probabilities=(p_dynamic, p_similar, p_local),
                cell_weight=1.0,
            )
        )
    return cells


def _corners_cells(repo_root: Path) -> list[EventCell]:
    layer31 = _load_gzip_rows(repo_root / L31_PATH)
    v3 = _load_gzip_rows(repo_root / V3_PATH)
    local = {
        row["fixture_key"]: row
        for row in v3
        if row["target"] == "corners"
    }

    paired: dict[
        tuple[str, str, str | None, float],
        dict[str, dict[str, Any]],
    ] = {}
    for row in layer31:
        key = (
            row["fixture_key"],
            row["market_scope"],
            row.get("role"),
            float(row["line"]),
        )
        paired.setdefault(key, {})[row["candidate"]] = row

    cells = []
    for (fixture_key, scope, role, line), candidates in sorted(
        paired.items(),
        key=lambda item: (
            item[1][next(iter(item[1]))]["kickoff_ts"],
            item[0],
        ),
    ):
        if set(candidates) != {"dynamic_poisson", "dynamic_side_nb2"}:
            raise ValueError("missing corners component pair")
        if fixture_key not in local:
            raise ValueError("missing competition-local corner fixture")
        p0 = candidates["dynamic_poisson"]
        p1 = candidates["dynamic_side_nb2"]
        if bool(p0["outcome_over"]) != bool(p1["outcome_over"]):
            raise ValueError("corners outcome mismatch")
        local_row = local[fixture_key]
        if p0["fold_id"] != local_row["fold_id"]:
            raise ValueError("corners fold mismatch")
        if scope == "SIDE":
            role_upper = str(role).upper()
            if role_upper == "HOME":
                mu = float(local_row["CANDIDATE"]["lambda_home"])
            elif role_upper == "AWAY":
                mu = float(local_row["CANDIDATE"]["lambda_away"])
            else:
                raise ValueError("invalid corner side role")
            cell_weight = 0.25 / 6.0
        elif scope == "TOTAL":
            mu = float(local_row["CANDIDATE"]["lambda_total"])
            cell_weight = 0.50 / 6.0
        else:
            raise ValueError("invalid corner market scope")
        p_local = float(poisson.sf(int(line), mu))
        cells.append(
            EventCell(
                fixture_key=fixture_key,
                kickoff_ts=int(p0["kickoff_ts"]),
                fold_id=str(p0["fold_id"]),
                outcome=bool(p0["outcome_over"]),
                probabilities=(
                    float(p0["probability_over"]),
                    float(p1["probability_over"]),
                    p_local,
                ),
                cell_weight=cell_weight,
            )
        )
    # Validate exactly one fixture-balanced composite objective.
    _fixture_scores(cells, np.asarray([1.0, 0.0, 0.0]))
    return cells


def _cells_for_family(repo_root: Path, family: str) -> list[EventCell]:
    if family == "goals":
        return _goals_cells(repo_root)
    if family == "corners":
        return _corners_cells(repo_root)
    raise ValueError(family)


def _fixed_scores(
    cells: list[EventCell],
    weights: list[float] | np.ndarray,
    *,
    folds: tuple[str, ...] = ("D2", "D3", "D4"),
) -> list[dict[str, Any]]:
    subset = [cell for cell in cells if cell.fold_id in folds]
    return _fixture_scores(subset, np.asarray(weights, dtype=float))


def _chronological_for_ridge(
    cells: list[EventCell],
    *,
    anchor: list[float],
    ridge_lambda: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validation_rows: list[dict[str, Any]] = []
    fold_records = []
    for validation_fold in ("D2", "D3", "D4"):
        validation_index = FOLD_ORDER[validation_fold]
        train = [
            cell
            for cell in cells
            if FOLD_ORDER[cell.fold_id] < validation_index
        ]
        validation = [
            cell for cell in cells if cell.fold_id == validation_fold
        ]
        weights = fit_regularized_simplex(
            train,
            anchor_weights=anchor,
            ridge_lambda=ridge_lambda,
        )
        scored = _fixture_scores(validation, weights)
        validation_rows.extend(scored)
        fold_records.append(
            {
                "fold_id": validation_fold,
                "training_fixtures": len({cell.fixture_key for cell in train}),
                "validation_fixtures": len(scored),
                "weights": [float(x) for x in weights],
                "scores": _mean_scores(scored),
            }
        )
    validation_rows.sort(key=lambda r: (r["kickoff_ts"], r["fixture_key"]))
    return validation_rows, fold_records


def _family_result(
    *,
    family: str,
    cells: list[EventCell],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    spec = protocol["families"][family]
    anchor = [float(x) for x in spec["anchor_weights"]]
    equal = [float(x) for x in spec["equal_weights"]]
    ridge_grid = [float(x) for x in protocol["optimizer"]["ridge_grid"]]
    tie_tolerance = float(protocol["optimizer"]["ridge_tie_tolerance"])

    ridge_results = []
    chronological_cache: dict[
        float,
        tuple[list[dict[str, Any]], list[dict[str, Any]]],
    ] = {}
    for ridge in ridge_grid:
        rows, folds = _chronological_for_ridge(
            cells,
            anchor=anchor,
            ridge_lambda=ridge,
        )
        chronological_cache[ridge] = (rows, folds)
        ridge_results.append(
            {
                "ridge_lambda": ridge,
                "scores": _mean_scores(rows),
                "folds": folds,
            }
        )
    best_ll = min(float(r["scores"]["log_loss"]) for r in ridge_results)
    tied = [
        r
        for r in ridge_results
        if float(r["scores"]["log_loss"]) <= best_ll + tie_tolerance
    ]
    selected_record = max(tied, key=lambda r: float(r["ridge_lambda"]))
    selected_ridge = float(selected_record["ridge_lambda"])
    selected_rows, selected_folds = chronological_cache[selected_ridge]

    anchor_rows = _fixed_scores(cells, anchor)
    equal_rows = _fixed_scores(cells, equal)
    single_records = []
    for index, name in enumerate(spec["components"]):
        weights = [0.0] * len(anchor)
        weights[index] = 1.0
        rows = _fixed_scores(cells, weights)
        single_records.append(
            {
                "component": name,
                "weights": weights,
                "scores": _mean_scores(rows),
            }
        )
    best_single = min(
        single_records,
        key=lambda r: float(r["scores"]["log_loss"]),
    )

    by_fixture_anchor = {row["fixture_key"]: row for row in anchor_rows}
    if set(by_fixture_anchor) != {
        row["fixture_key"] for row in selected_rows
    }:
        raise ValueError("ensemble anchor/challenger pairing mismatch")
    ll_pairs = []
    br_pairs = []
    for row in selected_rows:
        base = by_fixture_anchor[row["fixture_key"]]
        ll_pairs.append(
            (
                int(row["kickoff_ts"]),
                float(base["log_loss"]),
                float(row["log_loss"]),
            )
        )
        br_pairs.append(
            (
                int(row["kickoff_ts"]),
                float(base["brier"]),
                float(row["brier"]),
            )
        )
    eval_spec = protocol["evaluation"]
    ll_uncertainty = paired_block_bootstrap(
        ll_pairs,
        metric=f"{family}_ensemble_log_loss",
        bootstrap_replicates=int(eval_spec["bootstrap_replicates"]),
        seed=int(eval_spec["bootstrap_seed"]),
    ).to_dict()
    br_uncertainty = paired_block_bootstrap(
        br_pairs,
        metric=f"{family}_ensemble_brier",
        bootstrap_replicates=int(eval_spec["bootstrap_replicates"]),
        seed=int(eval_spec["bootstrap_seed"]),
    ).to_dict()

    anchor_fold_scores = {
        fold: _mean_scores(
            [
                row
                for row in anchor_rows
                if row["fold_id"] == fold
            ]
        )
        for fold in ("D2", "D3", "D4")
    }
    fold_deltas = []
    fold_wins = 0
    max_regression = float("-inf")
    for fold in selected_folds:
        fid = fold["fold_id"]
        delta = (
            float(fold["scores"]["log_loss"])
            - float(anchor_fold_scores[fid]["log_loss"])
        )
        if delta < 0:
            fold_wins += 1
        max_regression = max(max_regression, delta)
        fold_deltas.append(
            {
                "fold_id": fid,
                "challenger": fold["scores"],
                "anchor": anchor_fold_scores[fid],
                "delta_log_loss": delta,
                "weights": fold["weights"],
            }
        )

    passes = (
        ll_uncertainty["ci_low"] > 0.0
        and br_uncertainty["ci_low"] > 0.0
        and fold_wins >= 2
        and max_regression <= 0.002
    )
    final_weights = fit_regularized_simplex(
        cells,
        anchor_weights=anchor,
        ridge_lambda=selected_ridge,
    )
    return {
        "components": spec["components"],
        "selected_ridge_lambda": selected_ridge,
        "ridge_selection": ridge_results,
        "chronological_scores": _mean_scores(selected_rows),
        "frozen_v2_anchor": {
            "weights": anchor,
            "scores": _mean_scores(anchor_rows),
        },
        "equal_weight": {
            "weights": equal,
            "scores": _mean_scores(equal_rows),
        },
        "best_single_component": best_single,
        "paired_improvement_vs_anchor": {
            "log_loss": ll_uncertainty,
            "brier": br_uncertainty,
        },
        "fold_results": fold_deltas,
        "fold_log_loss_wins": fold_wins,
        "max_fold_log_loss_regression": max_regression,
        "passes_stage1_gate": bool(passes),
        "decision": (
            "REGULARIZED_LINEAR_POOL_DEVELOPMENT_CANDIDATE_NOT_PROMOTED"
            if passes
            else "RETAIN_FROZEN_V2_ENSEMBLE"
        ),
        "final_refit_weights_descriptive_only": [
            float(x) for x in final_weights
        ],
    }


def build_ensemble_stage1(
    *,
    repo_root: Path,
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    protocol_path = (
        repo_root / "research/qfe_v21_state_space/PROTOCOL_ENSEMBLE_V1.json"
    )
    protocol = _load_json(protocol_path)
    if protocol["version"] != "QFE_V21_REGULARIZED_LINEAR_POOL_STAGE1_V1":
        raise ValueError("ensemble protocol mismatch")

    families = {}
    for family in ("goals", "corners"):
        cells = _cells_for_family(repo_root, family)
        if any(cell.fold_id not in FOLD_ORDER for cell in cells):
            raise ValueError("non-development fold leaked into ensemble")
        families[family] = _family_result(
            family=family,
            cells=cells,
            protocol=protocol,
        )

    implementation = (
        "src/research/evaluation/v21_regularized_ensemble.py",
        "research/qfe_v21_state_space/PROTOCOL_ENSEMBLE_V1.json",
    )
    result: dict[str, Any] = {
        "version": RESULT_VERSION,
        "scientific_status": "DEVELOPMENT_ONLY_CALIBRATION_AND_PROTECTED_UNOPENED",
        "protocol_hash": sha256_json(protocol),
        "families": families,
        "boundaries": {
            "network_calls": 0,
            "market_odds_used": False,
            "llm_calls": 0,
            "calibration_outcomes_read": False,
            "protected_outcomes_read": False,
        },
        "source_sha256": {
            str(path): hashlib.sha256((repo_root / path).read_bytes()).hexdigest()
            for path in (
                STRUCTURED_PATH,
                SIMILAR_PATH,
                L31_PATH,
                V3_PATH,
            )
        },
        "implementation_sha256": {
            relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
            for relative in implementation
        },
    }
    result["result_hash"] = sha256_json(result)
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# QFE V2.1 — Regularized Linear Pool Stage 1 V1",
        "",
        f"Result hash: {result['result_hash']}",
        "",
        "> DEVELOPMENT chronological D2-D4 validation only. CALIBRATION and PROTECTED outcomes were not read.",
        "",
    ]
    for family in ("goals", "corners"):
        r = result["families"][family]
        lines += [
            f"## {family.title()}",
            "",
            f"- Selected ridge: **{r['selected_ridge_lambda']}**",
            f"- Chronological LL: **{r['chronological_scores']['log_loss']:.6f}**",
            f"- Anchor LL: **{r['frozen_v2_anchor']['scores']['log_loss']:.6f}**",
            f"- LL improvement: **{r['paired_improvement_vs_anchor']['log_loss']['mean_improvement']:+.6f}**",
            f"- LL 95% CI: **[{r['paired_improvement_vs_anchor']['log_loss']['ci_low']:+.6f}, {r['paired_improvement_vs_anchor']['log_loss']['ci_high']:+.6f}]**",
            f"- Brier improvement: **{r['paired_improvement_vs_anchor']['brier']['mean_improvement']:+.6f}**",
            f"- Fold wins: **{r['fold_log_loss_wins']}/3**",
            f"- Gate: **{r['passes_stage1_gate']}**",
            f"- Decision: **{r['decision']}**",
            f"- Final refit weights (descriptive): **{r['final_refit_weights_descriptive_only']}**",
            "",
        ]
    return "\n".join(lines) + "\n"


def write_ensemble_stage1(
    *,
    repo_root: Path,
    result: dict[str, Any],
) -> None:
    output_dir = Path(repo_root) / "research/qfe_v21_state_space"
    json_path = output_dir / "RESULT_ENSEMBLE_V1.json"
    md_path = output_dir / "RESULT_ENSEMBLE_V1.md"
    for path, payload in (
        (json_path, canonical_json(result) + "\n"),
        (md_path, render_markdown(result)),
    ):
        if path.exists():
            if path.read_text() != payload:
                raise FileExistsError(path)
        else:
            path.write_text(payload)
