"""QFE V2.1 competition-local Gamma-Poisson Stage 1 V3 evaluation.

Single bounded development-only comparison:
frozen V2 DynamicHierarchicalCountBaseline versus the competition-local
variant that removes team-global transfer.

CALIBRATION and PROTECTED outcomes are structurally excluded.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from math import log
from pathlib import Path
from statistics import mean
from typing import Any

from scipy.stats import poisson

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import build_multiseason_pit_corpus
from src.research.dataset.pit import PITDatasetSpec
from src.research.evaluation.chronology import (
    CALIBRATION_START_TS,
    DEVELOPMENT_OOF_FOLDS,
    development_fold_for_kickoff,
)
from src.research.models.competition_local_count_strength import (
    CompetitionLocalDynamicCountBaseline,
)
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)

RESULT_VERSION = "qfe-v21-comp-local-gamma-poisson-stage1-v3"
BASE_DIR = Path("/home/ubuntu/data/thestatsapi/championship")
TARGETS = {
    "goals": GOALS_TARGET,
    "corners": CORNERS_TARGET,
}


def _binary_log_loss(probability: float, outcome: bool) -> float:
    p = min(max(float(probability), 1e-12), 1.0 - 1e-12)
    return float(-log(p if outcome else 1.0 - p))


def _brier(probability: float, outcome: bool) -> float:
    return float((float(probability) - float(bool(outcome))) ** 2)


def _probability_over(mean_total: float, line: float) -> float:
    return float(poisson.sf(int(line), mean_total))


def _metrics(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    if not rows:
        raise ValueError("cannot score empty rows")
    return {
        "n_fixtures": len(rows),
        "side_poisson_nll": mean(float(row[key]["side_poisson_nll"]) for row in rows),
        "side_mae": mean(float(row[key]["side_mae"]) for row in rows),
        "binary_log_loss": mean(float(row[key]["binary_log_loss"]) for row in rows),
        "brier": mean(float(row[key]["brier"]) for row in rows),
    }


def evaluate_gate(
    *,
    reference: dict[str, float | int],
    candidate: dict[str, float | int],
    fold_primary_wins: int,
) -> dict[str, Any]:
    delta_nll = float(candidate["side_poisson_nll"]) - float(reference["side_poisson_nll"])
    delta_ll = float(candidate["binary_log_loss"]) - float(reference["binary_log_loss"])
    passes = delta_nll < 0.0 and fold_primary_wins >= 3 and delta_ll <= 0.001
    return {
        "delta_side_poisson_nll": delta_nll,
        "delta_side_mae": float(candidate["side_mae"]) - float(reference["side_mae"]),
        "delta_binary_log_loss": delta_ll,
        "delta_brier": float(candidate["brier"]) - float(reference["brier"]),
        "fold_primary_wins": int(fold_primary_wins),
        "passes_stage1_gate": bool(passes),
        "decision": (
            "LAYER2_DEVELOPMENT_CANDIDATE_NOT_PROMOTED"
            if passes
            else "NO_ADVANCEMENT"
        ),
    }


def _target_result(
    rows: list[dict[str, Any]],
    target_name: str,
) -> dict[str, Any]:
    target_rows = [row for row in rows if row["target"] == target_name]
    reference = _metrics(target_rows, "REFERENCE")
    candidate = _metrics(target_rows, "CANDIDATE")
    folds = []
    wins = 0
    for fold in DEVELOPMENT_OOF_FOLDS:
        fold_rows = [row for row in target_rows if row["fold_id"] == fold.fold_id]
        ref = _metrics(fold_rows, "REFERENCE")
        cand = _metrics(fold_rows, "CANDIDATE")
        delta = float(cand["side_poisson_nll"]) - float(ref["side_poisson_nll"])
        if delta < 0.0:
            wins += 1
        folds.append(
            {
                "fold_id": fold.fold_id,
                "reference": ref,
                "candidate": cand,
                "delta_side_poisson_nll": delta,
                "delta_side_mae": float(cand["side_mae"]) - float(ref["side_mae"]),
                "delta_binary_log_loss": (
                    float(cand["binary_log_loss"])
                    - float(ref["binary_log_loss"])
                ),
                "delta_brier": float(cand["brier"]) - float(ref["brier"]),
            }
        )
    gate = evaluate_gate(
        reference=reference,
        candidate=candidate,
        fold_primary_wins=wins,
    )
    return {
        "reference": reference,
        "candidate": candidate,
        "folds": folds,
        **gate,
    }


def build_stage1_v3(
    *,
    repo_root: Path,
    base_dir: Path = BASE_DIR,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo_root = Path(repo_root)
    protocol_path = repo_root / "research/qfe_v21_state_space/PROTOCOL_V3.json"
    protocol = json.loads(protocol_path.read_text())
    if protocol["version"] != "QFE_V21_COMP_LOCAL_GAMMA_POISSON_STAGE1_V3":
        raise ValueError("active V3 protocol mismatch")

    corpus = build_multiseason_pit_corpus(
        base_dir=Path(base_dir),
        pit_spec=PITDatasetSpec(decision_horizon_seconds=21600),
    )
    history = tuple(
        match
        for match in corpus.matches
        if int(match.date_unix) < CALIBRATION_START_TS
    )
    if any(int(match.date_unix) >= CALIBRATION_START_TS for match in history):
        raise ValueError("CALIBRATION leakage into V3 state history")

    rows: list[dict[str, Any]] = []
    target_results: dict[str, Any] = {}
    for target_name, target in TARGETS.items():
        config = DynamicCountConfig(
            **protocol["reference"][f"{target_name}_config"]
        )
        reference_map = {
            forecast.fixture_key: forecast
            for forecast in DynamicHierarchicalCountBaseline(
                target,
                config,
            ).walk_forward(history)
        }
        candidate_model = CompetitionLocalDynamicCountBaseline(target, config)
        candidate_map = {
            forecast.fixture_key: forecast
            for forecast in candidate_model.walk_forward(history)
        }
        if candidate_model._team_global:
            raise ValueError("candidate created forbidden team-global state")

        line = float(protocol["evaluation"]["fixed_total_lines"][target_name])
        for match in history:
            fold = development_fold_for_kickoff(int(match.date_unix))
            if fold is None:
                continue
            observed = target.observed_counts(match)
            if observed is None:
                continue
            fixture_key = match.stable_fixture_key
            if fixture_key is None:
                raise ValueError("stable fixture identity required")
            home_obs, away_obs = observed
            total_obs = home_obs + away_obs
            reference = reference_map[fixture_key]
            candidate = candidate_map[fixture_key]
            row: dict[str, Any] = {
                "fixture_key": fixture_key,
                "fold_id": fold.fold_id,
                "kickoff_ts": int(match.date_unix),
                "competition_ref": match.competition_ref,
                "target": target_name,
                "line": line,
                "home_observed": home_obs,
                "away_observed": away_obs,
                "total_observed": total_obs,
            }
            for key, forecast in (
                ("REFERENCE", reference),
                ("CANDIDATE", candidate),
            ):
                probability = _probability_over(forecast.lambda_total, line)
                row[key] = {
                    "lambda_home": forecast.lambda_home,
                    "lambda_away": forecast.lambda_away,
                    "lambda_total": forecast.lambda_total,
                    "side_poisson_nll": 0.5 * (
                        -float(poisson.logpmf(home_obs, forecast.lambda_home))
                        -float(poisson.logpmf(away_obs, forecast.lambda_away))
                    ),
                    "side_mae": 0.5 * (
                        abs(home_obs - forecast.lambda_home)
                        + abs(away_obs - forecast.lambda_away)
                    ),
                    "probability_over": probability,
                    "binary_log_loss": _binary_log_loss(
                        probability,
                        total_obs > line,
                    ),
                    "brier": _brier(probability, total_obs > line),
                    "effective_support": forecast.effective_support,
                    "supported": forecast.supported,
                }
            rows.append(row)

        target_results[target_name] = _target_result(rows, target_name)

    rows.sort(
        key=lambda row: (
            row["kickoff_ts"],
            row["fixture_key"],
            row["target"],
        )
    )
    implementation_paths = (
        "src/research/models/competition_local_count_strength.py",
        "src/research/evaluation/v21_comp_local_stage1.py",
        "research/qfe_v21_state_space/PROTOCOL_V3.json",
    )
    result: dict[str, Any] = {
        "version": RESULT_VERSION,
        "scientific_status": "DEVELOPMENT_ONLY_CALIBRATION_AND_PROTECTED_UNOPENED",
        "protocol_hash": sha256_json(protocol),
        "corpus_manifest_hash": corpus.manifest.manifest_hash,
        "development_rows": len(rows),
        "development_fixtures": len({row["fixture_key"] for row in rows}),
        "boundaries": {
            "network_calls": 0,
            "market_odds_used": False,
            "llm_calls": 0,
            "calibration_outcomes_read": False,
            "protected_outcomes_read": False,
            "state_history_end_exclusive_ts": CALIBRATION_START_TS,
        },
        "targets": target_results,
        "rows_hash": sha256_json(rows),
        "implementation_sha256": {
            relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
            for relative in implementation_paths
        },
    }
    result["result_hash"] = sha256_json(result)
    return result, rows


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# QFE V2.1 — Competition-Local Gamma-Poisson Stage 1 V3",
        "",
        f"Result hash: {result['result_hash']}",
        "",
        "> DEVELOPMENT D1-D4 only. CALIBRATION and PROTECTED outcomes were not read.",
        "",
    ]
    for target_name in ("goals", "corners"):
        target = result["targets"][target_name]
        lines += [
            f"## {target_name.title()}",
            "",
            f"- Delta side NLL: **{target['delta_side_poisson_nll']:+.8f}**",
            f"- Delta binary LL: **{target['delta_binary_log_loss']:+.8f}**",
            f"- Delta Brier: **{target['delta_brier']:+.8f}**",
            f"- Fold primary wins: **{target['fold_primary_wins']}/4**",
            f"- Stage 1 gate: **{target['passes_stage1_gate']}**",
            f"- Decision: **{target['decision']}**",
            "",
            "| Fold | Delta side NLL | Delta binary LL | Delta Brier |",
            "|---|---:|---:|---:|",
        ]
        for fold in target["folds"]:
            lines.append(
                f"| {fold['fold_id']} | "
                f"{fold['delta_side_poisson_nll']:+.8f} | "
                f"{fold['delta_binary_log_loss']:+.8f} | "
                f"{fold['delta_brier']:+.8f} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_stage1_v3(
    *,
    repo_root: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    repo_root = Path(repo_root)
    output_dir = repo_root / "research/qfe_v21_state_space"
    summary_path = output_dir / "RESULT_V3.json"
    markdown_path = output_dir / "RESULT_V3.md"
    rows_path = output_dir / "ROWS_V3.jsonl.gz"

    raw = "".join(canonical_json(row) + "\n" for row in rows).encode()
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    summary = {
        **result,
        "rows_file": rows_path.name,
        "rows_file_sha256": hashlib.sha256(compressed).hexdigest(),
    }
    json_payload = canonical_json(summary) + "\n"
    markdown_payload = render_markdown(summary)

    for path, payload in (
        (summary_path, json_payload),
        (markdown_path, markdown_payload),
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
