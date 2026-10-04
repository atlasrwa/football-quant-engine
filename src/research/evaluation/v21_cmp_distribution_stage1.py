"""Development-only CMP distribution tournament for QFE V2.1."""
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

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec
from src.research.evaluation.chronology import (
    CALIBRATION_START_TS,
    DEVELOPMENT_OOF_FOLDS,
)
from src.research.models.cmp_distribution import (
    cmp_pmf_vector,
    convolve_count_pmfs,
    discrete_rps,
    probability_over,
)
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)
from src.research.models.structured_distributions import (
    fit_nb2_dispersion,
    nb2_pmf,
)

RESULT_VERSION = "qfe-v21-cmp-distribution-stage1-v1"
BASE_DIR = Path("/home/ubuntu/data/thestatsapi/championship")
TARGETS = {"goals": GOALS_TARGET, "corners": CORNERS_TARGET}
CORNERS_NB2_WEIGHT = 0.75


@dataclass(frozen=True, slots=True)
class DistributionScores:
    joint_log_score: float
    total_log_score: float
    side_mean_rps: float
    total_rps: float
    binary_log_loss: float
    brier: float

    def to_dict(self) -> dict[str, float]:
        return {
            "joint_log_score": self.joint_log_score,
            "total_log_score": self.total_log_score,
            "side_mean_rps": self.side_mean_rps,
            "total_rps": self.total_rps,
            "binary_log_loss": self.binary_log_loss,
            "brier": self.brier,
        }


def _binary_log_loss(p: float, y: bool) -> float:
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    return float(-log(p if y else 1.0 - p))


def _nb2_vector(mean_count: float, alpha: float) -> np.ndarray:
    support = 120
    while True:
        values = np.asarray(
            [nb2_pmf(k, mean_count, alpha) for k in range(support + 1)],
            dtype=float,
        )
        total = float(values.sum())
        tail = max(0.0, 1.0 - total)
        if tail <= 1e-11:
            values /= total
            return values
        if support >= 480:
            raise RuntimeError("NB2 tail exceeds distribution support contract")
        support = min(480, support * 2)


def _mixture(a: np.ndarray, b: np.ndarray, weight_b: float) -> np.ndarray:
    length = max(len(a), len(b))
    out = np.zeros(length, dtype=float)
    out[: len(a)] += (1.0 - weight_b) * np.asarray(a, dtype=float)
    out[: len(b)] += weight_b * np.asarray(b, dtype=float)
    out /= out.sum()
    return out


def _observed_probability(pmf: np.ndarray, observed: int) -> float:
    if observed >= len(pmf):
        raise RuntimeError("observed count outside audited support")
    return max(float(pmf[observed]), 1e-300)


def _score_fixture(
    *,
    home_observed: int,
    away_observed: int,
    line: float,
    home_pmf: np.ndarray,
    away_pmf: np.ndarray,
    joint_observed_probability: float,
) -> DistributionScores:
    total_observed = home_observed + away_observed
    total_pmf = convolve_count_pmfs(home_pmf, away_pmf)
    p_total = _observed_probability(total_pmf, total_observed)
    p_over = probability_over(total_pmf, line)
    outcome_over = total_observed > line
    return DistributionScores(
        joint_log_score=-log(max(joint_observed_probability, 1e-300)),
        total_log_score=-log(p_total),
        side_mean_rps=0.5 * (
            discrete_rps(home_pmf, home_observed)
            + discrete_rps(away_pmf, away_observed)
        ),
        total_rps=discrete_rps(total_pmf, total_observed),
        binary_log_loss=_binary_log_loss(p_over, outcome_over),
        brier=float((p_over - float(outcome_over)) ** 2),
    )


def _fit_cmp_nu(
    training: list[tuple[float, float, int, int]],
    grid: list[float],
    tie_tolerance: float,
) -> tuple[float, list[dict[str, float]]]:
    if not training:
        raise ValueError("CMP fold training is empty")
    results = []
    for nu in grid:
        losses = []
        for lambda_home, lambda_away, home_obs, away_obs in training:
            hp = cmp_pmf_vector(lambda_home, nu)
            ap = cmp_pmf_vector(lambda_away, nu)
            losses.append(
                -log(_observed_probability(hp, home_obs))
                -log(_observed_probability(ap, away_obs))
            )
        results.append(
            {
                "nu": float(nu),
                "mean_joint_side_nll": float(mean(losses)),
            }
        )
    best = min(x["mean_joint_side_nll"] for x in results)
    tied = [
        x for x in results
        if x["mean_joint_side_nll"] <= best + tie_tolerance
    ]
    selected = min(
        tied,
        key=lambda x: (abs(x["nu"] - 1.0), x["nu"]),
    )
    return float(selected["nu"]), results


def _mean_metrics(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, float | int]:
    if not rows:
        raise ValueError("empty scoring rows")
    names = (
        "joint_log_score",
        "total_log_score",
        "side_mean_rps",
        "total_rps",
        "binary_log_loss",
        "brier",
    )
    return {
        "n_fixtures": len(rows),
        **{
            name: mean(float(row[key][name]) for row in rows)
            for name in names
        },
    }


def _decision(
    reference: dict[str, float | int],
    challenger: dict[str, float | int],
    fold_wins: int,
) -> dict[str, Any]:
    deltas = {
        key: float(challenger[key]) - float(reference[key])
        for key in (
            "joint_log_score",
            "total_log_score",
            "side_mean_rps",
            "total_rps",
            "binary_log_loss",
            "brier",
        )
    }
    passes = (
        deltas["joint_log_score"] < 0.0
        and fold_wins >= 3
        and deltas["total_rps"] <= 0.0
        and deltas["binary_log_loss"] <= 0.001
    )
    return {
        "deltas": deltas,
        "fold_primary_wins": fold_wins,
        "passes_stage1_gate": bool(passes),
        "decision": (
            "CMP_POOLED_DEVELOPMENT_CANDIDATE_NOT_PROMOTED"
            if passes
            else "NO_ADVANCEMENT"
        ),
    }


def build_cmp_stage1(
    *,
    repo_root: Path,
    base_dir: Path = BASE_DIR,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo_root = Path(repo_root)
    protocol_path = (
        repo_root
        / "research/qfe_v21_state_space/PROTOCOL_DISTRIBUTION_V1.json"
    )
    protocol = json.loads(protocol_path.read_text())
    if protocol["version"] != "QFE_V21_DISTRIBUTION_STAGE1_CMP_V1":
        raise ValueError("CMP protocol mismatch")

    corpus = build_multiseason_pit_corpus(
        base_dir=Path(base_dir),
        pit_spec=PITDatasetSpec(decision_horizon_seconds=21600),
    )
    history = tuple(
        m for m in corpus.matches if int(m.date_unix) < CALIBRATION_START_TS
    )
    if any(int(m.date_unix) >= CALIBRATION_START_TS for m in history):
        raise ValueError("CALIBRATION leakage into CMP stage")

    grid = [float(x) for x in protocol["challenger"]["nu_grid"]]
    tie_tolerance = float(protocol["challenger"]["tie_tolerance"])
    rows: list[dict[str, Any]] = []
    fits: list[dict[str, Any]] = []

    for target_name, target in TARGETS.items():
        config = DynamicCountConfig(
            **protocol["means"][f"{target_name}_config"]
        )
        forecasts = {
            f.fixture_key: f
            for f in DynamicHierarchicalCountBaseline(
                target,
                config,
            ).walk_forward(history)
        }
        line = float(protocol["evaluation"]["fixed_total_lines"][target_name])

        for fold in DEVELOPMENT_OOF_FOLDS:
            train_matches = [
                m for m in history
                if int(m.date_unix) < fold.validation_start_ts
            ]
            valid_matches = [
                m for m in history
                if fold.contains_validation(int(m.date_unix))
            ]
            training: list[tuple[float, float, int, int]] = []
            nb_training: list[tuple[float, int]] = []
            for match in train_matches:
                observed = target.observed_counts(match)
                forecast = forecasts.get(match.stable_fixture_key)
                if observed is None or forecast is None:
                    continue
                training.append(
                    (
                        forecast.lambda_home,
                        forecast.lambda_away,
                        observed[0],
                        observed[1],
                    )
                )
                if target_name == "corners":
                    nb_training.extend(
                        (
                            (forecast.lambda_home, observed[0]),
                            (forecast.lambda_away, observed[1]),
                        )
                    )

            selected_nu, grid_results = _fit_cmp_nu(
                training,
                grid,
                tie_tolerance,
            )
            alpha = None
            if target_name == "corners":
                alpha = float(fit_nb2_dispersion(nb_training).alpha)
            fits.append(
                {
                    "target": target_name,
                    "fold_id": fold.fold_id,
                    "training_fixtures": len(training),
                    "selected_nu": selected_nu,
                    "nu_grid_results": grid_results,
                    "reference_corner_nb2_alpha": alpha,
                }
            )

            for match in valid_matches:
                observed = target.observed_counts(match)
                if observed is None:
                    continue
                fixture_key = match.stable_fixture_key
                if fixture_key is None:
                    raise ValueError("stable fixture identity required")
                forecast = forecasts[fixture_key]
                home_obs, away_obs = observed

                pois_h = cmp_pmf_vector(forecast.lambda_home, 1.0)
                pois_a = cmp_pmf_vector(forecast.lambda_away, 1.0)
                if target_name == "goals":
                    reference_home = pois_h
                    reference_away = pois_a
                    reference_joint = (
                        _observed_probability(pois_h, home_obs)
                        * _observed_probability(pois_a, away_obs)
                    )
                else:
                    assert alpha is not None
                    nb_h = _nb2_vector(forecast.lambda_home, alpha)
                    nb_a = _nb2_vector(forecast.lambda_away, alpha)
                    reference_home = _mixture(
                        pois_h,
                        nb_h,
                        CORNERS_NB2_WEIGHT,
                    )
                    reference_away = _mixture(
                        pois_a,
                        nb_a,
                        CORNERS_NB2_WEIGHT,
                    )
                    pois_joint = (
                        _observed_probability(pois_h, home_obs)
                        * _observed_probability(pois_a, away_obs)
                    )
                    nb_joint = (
                        _observed_probability(nb_h, home_obs)
                        * _observed_probability(nb_a, away_obs)
                    )
                    reference_joint = (
                        (1.0 - CORNERS_NB2_WEIGHT) * pois_joint
                        + CORNERS_NB2_WEIGHT * nb_joint
                    )

                cmp_h = cmp_pmf_vector(forecast.lambda_home, selected_nu)
                cmp_a = cmp_pmf_vector(forecast.lambda_away, selected_nu)
                cmp_joint = (
                    _observed_probability(cmp_h, home_obs)
                    * _observed_probability(cmp_a, away_obs)
                )
                reference_scores = _score_fixture(
                    home_observed=home_obs,
                    away_observed=away_obs,
                    line=line,
                    home_pmf=reference_home,
                    away_pmf=reference_away,
                    joint_observed_probability=reference_joint,
                )
                cmp_scores = _score_fixture(
                    home_observed=home_obs,
                    away_observed=away_obs,
                    line=line,
                    home_pmf=cmp_h,
                    away_pmf=cmp_a,
                    joint_observed_probability=cmp_joint,
                )
                rows.append(
                    {
                        "fixture_key": fixture_key,
                        "kickoff_ts": int(match.date_unix),
                        "competition_ref": match.competition_ref,
                        "target": target_name,
                        "fold_id": fold.fold_id,
                        "line": line,
                        "selected_nu": selected_nu,
                        "reference_corner_nb2_alpha": alpha,
                        "home_observed": home_obs,
                        "away_observed": away_obs,
                        "REFERENCE": reference_scores.to_dict(),
                        "CMP": cmp_scores.to_dict(),
                    }
                )

    target_results: dict[str, Any] = {}
    for target_name in TARGETS:
        target_rows = [r for r in rows if r["target"] == target_name]
        ref = _mean_metrics(target_rows, "REFERENCE")
        cmp = _mean_metrics(target_rows, "CMP")
        fold_results = []
        wins = 0
        for fold in DEVELOPMENT_OOF_FOLDS:
            fold_rows = [
                r for r in target_rows if r["fold_id"] == fold.fold_id
            ]
            fr = _mean_metrics(fold_rows, "REFERENCE")
            fc = _mean_metrics(fold_rows, "CMP")
            delta_joint = (
                float(fc["joint_log_score"]) - float(fr["joint_log_score"])
            )
            if delta_joint < 0.0:
                wins += 1
            fold_results.append(
                {
                    "fold_id": fold.fold_id,
                    "selected_nu": next(
                        x["selected_nu"]
                        for x in fits
                        if x["target"] == target_name
                        and x["fold_id"] == fold.fold_id
                    ),
                    "reference": fr,
                    "cmp": fc,
                    "delta_joint_log_score": delta_joint,
                    "delta_total_log_score": (
                        float(fc["total_log_score"])
                        - float(fr["total_log_score"])
                    ),
                    "delta_total_rps": (
                        float(fc["total_rps"]) - float(fr["total_rps"])
                    ),
                    "delta_binary_log_loss": (
                        float(fc["binary_log_loss"])
                        - float(fr["binary_log_loss"])
                    ),
                }
            )
        target_results[target_name] = {
            "reference": ref,
            "cmp": cmp,
            "folds": fold_results,
            **_decision(ref, cmp, wins),
        }

    rows.sort(
        key=lambda r: (r["kickoff_ts"], r["fixture_key"], r["target"])
    )
    implementation_paths = (
        "src/research/models/cmp_distribution.py",
        "src/research/evaluation/v21_cmp_distribution_stage1.py",
        "research/qfe_v21_state_space/PROTOCOL_DISTRIBUTION_V1.json",
    )
    result: dict[str, Any] = {
        "version": RESULT_VERSION,
        "scientific_status": "DEVELOPMENT_ONLY_CALIBRATION_AND_PROTECTED_UNOPENED",
        "protocol_hash": sha256_json(protocol),
        "corpus_manifest_hash": corpus.manifest.manifest_hash,
        "development_rows": len(rows),
        "development_fixtures": len({r["fixture_key"] for r in rows}),
        "fits": fits,
        "targets": target_results,
        "rows_hash": sha256_json(rows),
        "boundaries": {
            "network_calls": 0,
            "market_odds_used": False,
            "llm_calls": 0,
            "calibration_outcomes_read": False,
            "protected_outcomes_read": False,
            "state_history_end_exclusive_ts": CALIBRATION_START_TS,
        },
        "implementation_sha256": {
            rel: hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()
            for rel in implementation_paths
        },
    }
    result["result_hash"] = sha256_json(result)
    return result, rows


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# QFE V2.1 — CMP Distribution Stage 1 V1",
        "",
        f"Result hash: {result['result_hash']}",
        "",
        "> DEVELOPMENT D1-D4 only. CALIBRATION and PROTECTED outcomes were not read.",
        "",
    ]
    for target_name in ("goals", "corners"):
        target = result["targets"][target_name]
        d = target["deltas"]
        lines += [
            f"## {target_name.title()}",
            "",
            f"- Delta joint LogS: **{d['joint_log_score']:+.8f}**",
            f"- Delta total LogS: **{d['total_log_score']:+.8f}**",
            f"- Delta total RPS: **{d['total_rps']:+.8f}**",
            f"- Delta binary LL: **{d['binary_log_loss']:+.8f}**",
            f"- Delta Brier: **{d['brier']:+.8f}**",
            f"- Fold primary wins: **{target['fold_primary_wins']}/4**",
            f"- Decision: **{target['decision']}**",
            "",
            "| Fold | nu | Delta joint LogS | Delta total RPS | Delta binary LL |",
            "|---|---:|---:|---:|---:|",
        ]
        for fold in target["folds"]:
            lines.append(
                f"| {fold['fold_id']} | {fold['selected_nu']:.2f} | "
                f"{fold['delta_joint_log_score']:+.8f} | "
                f"{fold['delta_total_rps']:+.8f} | "
                f"{fold['delta_binary_log_loss']:+.8f} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_cmp_stage1(
    *,
    repo_root: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    output_dir = Path(repo_root) / "research/qfe_v21_state_space"
    summary_path = output_dir / "RESULT_DISTRIBUTION_V1.json"
    markdown_path = output_dir / "RESULT_DISTRIBUTION_V1.md"
    rows_path = output_dir / "ROWS_DISTRIBUTION_V1.jsonl.gz"
    raw = "".join(canonical_json(row) + "\n" for row in rows).encode()
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    summary = {
        **result,
        "rows_file": rows_path.name,
        "rows_file_sha256": hashlib.sha256(compressed).hexdigest(),
    }
    for path, payload in (
        (summary_path, canonical_json(summary) + "\n"),
        (markdown_path, render_markdown(summary)),
    ):
        if path.exists():
            if path.read_text() != payload:
                raise FileExistsError(path)
        else:
            path.write_text(payload)
    if rows_path.exists():
        if rows_path.read_bytes() != compressed:
            raise FileExistsError(rows_path)
    else:
        rows_path.write_bytes(compressed)
