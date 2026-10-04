"""Execute the preregistered QFE V2.1 state-space Stage 1 tournament.

Development-only. CALIBRATION and PROTECTED outcomes are structurally excluded.
No network, market, or LLM inputs are used.
"""
from __future__ import annotations

from dataclasses import asdict
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
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
)
from src.research.models.hierarchical_state_space import (
    HierarchicalLogStateSpaceModel,
    HierarchicalStateSpaceConfig,
    StateDynamics,
)

STAGE1_VERSION = "qfe-v21-state-space-stage1-result-v1"
PROFILE_ORDER = ("CONSERVATIVE", "BALANCED", "RESPONSIVE")
TARGETS = {
    "goals": GOALS_TARGET,
    "corners": CORNERS_TARGET,
}
BASE_DIR = Path("/home/ubuntu/data/thestatsapi/championship")


def _binary_log_loss(probability: float, outcome: bool) -> float:
    p = min(max(float(probability), 1e-12), 1.0 - 1e-12)
    return float(-log(p if outcome else 1.0 - p))


def _brier(probability: float, outcome: bool) -> float:
    return float((float(probability) - float(bool(outcome))) ** 2)


def _poisson_over(mean_total: float, line: float) -> float:
    return float(1.0 - poisson.cdf(int(line), mean_total))


def _profile_config(
    protocol: dict[str, Any],
    target_name: str,
    profile_name: str,
) -> HierarchicalStateSpaceConfig:
    profile = protocol["candidate_profiles"][profile_name]
    half_key = f"{target_name}_half_life_days"
    half = profile[half_key]
    sd = profile["stationary_sd"]
    return HierarchicalStateSpaceConfig(
        global_state=StateDynamics(float(half["global"]), float(sd["global"])),
        competition_state=StateDynamics(
            float(half["competition"]),
            float(sd["competition"]),
        ),
        team_global_state=StateDynamics(
            float(half["team_global"]),
            float(sd["team_global"]),
        ),
        team_comp_state=StateDynamics(
            float(half["team_comp"]),
            float(sd["team_comp"]),
        ),
        team_influence=float(profile["team_influence"]),
        min_effective_team_support=3.0,
    )


def _reference_config(
    protocol: dict[str, Any],
    target_name: str,
) -> DynamicCountConfig:
    return DynamicCountConfig(
        **protocol["reference"][f"{target_name}_config"]
    )


def _metrics(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    if not rows:
        raise ValueError("cannot score empty row set")
    return {
        "n_fixtures": len(rows),
        "side_poisson_nll": mean(float(row[key]["side_poisson_nll"]) for row in rows),
        "side_mae": mean(float(row[key]["side_mae"]) for row in rows),
        "binary_log_loss": mean(float(row[key]["binary_log_loss"]) for row in rows),
        "brier": mean(float(row[key]["brier"]) for row in rows),
    }


def _candidate_uncertainty(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, float]:
    values = [row[key] for row in rows]
    return {
        "mean_latent_log_sd": mean(
            0.5 * (
                float(value["latent_log_sd_home"])
                + float(value["latent_log_sd_away"])
            )
            for value in values
        ),
        "mean_90pct_latent_expected_rate_interval_log_width": mean(
            0.5 * (
                log(
                    float(value["home_interval_90"][1])
                    / float(value["home_interval_90"][0])
                )
                + log(
                    float(value["away_interval_90"][1])
                    / float(value["away_interval_90"][0])
                )
            )
            for value in values
        ),
        "supported_fraction": mean(
            1.0 if bool(value["supported"]) else 0.0
            for value in values
        ),
        "mean_effective_support": mean(
            float(value["effective_support"])
            for value in values
        ),
    }


def _selection(
    *,
    protocol: dict[str, Any],
    rows: list[dict[str, Any]],
    target_name: str,
) -> dict[str, Any]:
    target_rows = [row for row in rows if row["target"] == target_name]
    reference = _metrics(target_rows, "REFERENCE")
    records: list[dict[str, Any]] = []
    for profile in PROFILE_ORDER:
        metric = _metrics(target_rows, profile)
        fold_wins = 0
        fold_results = []
        for fold in DEVELOPMENT_OOF_FOLDS:
            fold_rows = [
                row for row in target_rows
                if row["fold_id"] == fold.fold_id
            ]
            ref_fold = _metrics(fold_rows, "REFERENCE")
            cand_fold = _metrics(fold_rows, profile)
            primary_delta = (
                float(cand_fold["side_poisson_nll"])
                - float(ref_fold["side_poisson_nll"])
            )
            if primary_delta < 0:
                fold_wins += 1
            fold_results.append(
                {
                    "fold_id": fold.fold_id,
                    "reference": ref_fold,
                    "candidate": cand_fold,
                    "delta_side_poisson_nll": primary_delta,
                    "delta_binary_log_loss": (
                        float(cand_fold["binary_log_loss"])
                        - float(ref_fold["binary_log_loss"])
                    ),
                    "delta_brier": (
                        float(cand_fold["brier"])
                        - float(ref_fold["brier"])
                    ),
                }
            )
        pooled_delta = (
            float(metric["side_poisson_nll"])
            - float(reference["side_poisson_nll"])
        )
        binary_delta = (
            float(metric["binary_log_loss"])
            - float(reference["binary_log_loss"])
        )
        qualifies = (
            pooled_delta < 0
            and fold_wins >= 3
            and binary_delta <= 0.001
        )
        records.append(
            {
                "profile": profile,
                "pooled": metric,
                "uncertainty": _candidate_uncertainty(target_rows, profile),
                "delta_side_poisson_nll": pooled_delta,
                "delta_side_mae": (
                    float(metric["side_mae"]) - float(reference["side_mae"])
                ),
                "delta_binary_log_loss": binary_delta,
                "delta_brier": (
                    float(metric["brier"]) - float(reference["brier"])
                ),
                "fold_primary_wins": fold_wins,
                "folds": fold_results,
                "qualifies_stage1_gate": qualifies,
            }
        )

    best_primary = min(float(r["pooled"]["side_poisson_nll"]) for r in records)
    tie_tolerance = 0.0005
    tied = [
        r for r in records
        if float(r["pooled"]["side_poisson_nll"]) <= best_primary + tie_tolerance
    ]
    chosen = min(tied, key=lambda r: PROFILE_ORDER.index(str(r["profile"])))
    advances = bool(chosen["qualifies_stage1_gate"])
    return {
        "reference": reference,
        "candidates": records,
        "chosen_profile": chosen["profile"],
        "stage1_advances": advances,
        "stage1_decision": (
            "ADVANCE_TO_SEPARATELY_PREREGISTERED_STAGE2"
            if advances
            else "NO_ADVANCEMENT"
        ),
    }


def build_stage1(
    *,
    repo_root: Path,
    base_dir: Path = BASE_DIR,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo_root = Path(repo_root)
    protocol_path = repo_root / "research/qfe_v21_state_space/PROTOCOL_V1_1.json"
    protocol = json.loads(protocol_path.read_text())
    if protocol["version"] != "QFE_V21_STATE_SPACE_STAGE1_V1_1":
        raise ValueError("active protocol mismatch")
    protocol_hash = sha256_json(protocol)

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
        raise ValueError("CALIBRATION leakage into Stage1 state history")

    rows: list[dict[str, Any]] = []
    target_results: dict[str, Any] = {}
    for target_name, target in TARGETS.items():
        reference_model = DynamicHierarchicalCountBaseline(
            target,
            _reference_config(protocol, target_name),
        )
        reference = {
            f.fixture_key: f
            for f in reference_model.walk_forward(history)
        }
        challenger_maps: dict[str, dict[str, Any]] = {}
        challenger_configs: dict[str, dict[str, Any]] = {}
        for profile in PROFILE_ORDER:
            config = _profile_config(protocol, target_name, profile)
            challenger_configs[profile] = asdict(config)
            model = HierarchicalLogStateSpaceModel(target, config)
            challenger_maps[profile] = {
                f.fixture_key: f
                for f in model.walk_forward(history)
            }

        line = float(protocol["evaluation"]["fixed_total_lines"][target_name])
        for match in history:
            fold = development_fold_for_kickoff(int(match.date_unix))
            if fold is None:
                continue
            outcome = target.observed_counts(match)
            if outcome is None:
                continue
            fixture_key = match.stable_fixture_key
            if fixture_key is None:
                raise ValueError("stable fixture key required")
            ref = reference[fixture_key]
            home_obs, away_obs = outcome
            total_obs = home_obs + away_obs
            ref_p = _poisson_over(ref.lambda_total, line)
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
                "REFERENCE": {
                    "lambda_home": ref.lambda_home,
                    "lambda_away": ref.lambda_away,
                    "lambda_total": ref.lambda_total,
                    "side_poisson_nll": 0.5 * (
                        -float(poisson.logpmf(home_obs, ref.lambda_home))
                        -float(poisson.logpmf(away_obs, ref.lambda_away))
                    ),
                    "side_mae": 0.5 * (
                        abs(home_obs - ref.lambda_home)
                        + abs(away_obs - ref.lambda_away)
                    ),
                    "probability_over": ref_p,
                    "binary_log_loss": _binary_log_loss(ref_p, total_obs > line),
                    "brier": _brier(ref_p, total_obs > line),
                },
            }
            for profile in PROFILE_ORDER:
                forecast = challenger_maps[profile][fixture_key]
                p_over = _poisson_over(forecast.lambda_total, line)
                row[profile] = {
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
                    "probability_over": p_over,
                    "binary_log_loss": _binary_log_loss(
                        p_over,
                        total_obs > line,
                    ),
                    "brier": _brier(p_over, total_obs > line),
                    "latent_log_sd_home": forecast.latent_log_sd_home,
                    "latent_log_sd_away": forecast.latent_log_sd_away,
                    "home_interval_90": list(
                        forecast.home_expected_rate_interval_90
                    ),
                    "away_interval_90": list(
                        forecast.away_expected_rate_interval_90
                    ),
                    "effective_support": forecast.effective_support,
                    "supported": forecast.supported,
                }
            rows.append(row)

        target_rows = [row for row in rows if row["target"] == target_name]
        target_results[target_name] = {
            "configs": challenger_configs,
            "selection": _selection(
                protocol=protocol,
                rows=target_rows,
                target_name=target_name,
            ),
        }

    rows.sort(
        key=lambda row: (
            row["kickoff_ts"],
            row["fixture_key"],
            row["target"],
        )
    )
    result: dict[str, Any] = {
        "version": STAGE1_VERSION,
        "scientific_status": "DEVELOPMENT_ONLY_PROTECTED_AND_CALIBRATION_UNOPENED",
        "protocol_hash": protocol_hash,
        "protocol_version": protocol["version"],
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
    }
    implementation = [
        "src/research/models/hierarchical_state_space.py",
        "src/research/evaluation/v21_state_space_stage1.py",
        "research/qfe_v21_state_space/PROTOCOL_V1_1.json",
    ]
    result["implementation_sha256"] = {
        relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
        for relative in implementation
    }
    result["result_hash"] = sha256_json(result)
    return result, rows


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# QFE V2.1 — State-Space Stage 1 Result",
        "",
        f"Result hash: {result['result_hash']}",
        "",
        "> DEVELOPMENT D1-D4 only. CALIBRATION and PROTECTED outcomes were not read.",
        "",
    ]
    for target_name in ("goals", "corners"):
        section = result["targets"][target_name]["selection"]
        ref = section["reference"]
        lines += [
            f"## {target_name.title()}",
            "",
            f"Reference side NLL: **{ref['side_poisson_nll']:.6f}**",
            f"Reference binary LL: **{ref['binary_log_loss']:.6f}**",
            "",
            "| Profile | Δ side NLL | Δ binary LL | Δ Brier | Fold wins | Gate |",
            "|---|---:|---:|---:|---:|:---:|",
        ]
        for candidate in section["candidates"]:
            lines.append(
                "| {profile} | {dnll:+.6f} | {dll:+.6f} | {db:+.6f} | {wins}/4 | {gate} |".format(
                    profile=candidate["profile"],
                    dnll=candidate["delta_side_poisson_nll"],
                    dll=candidate["delta_binary_log_loss"],
                    db=candidate["delta_brier"],
                    wins=candidate["fold_primary_wins"],
                    gate=candidate["qualifies_stage1_gate"],
                )
            )
        lines += [
            "",
            f"Chosen profile: **{section['chosen_profile']}**",
            f"Stage 1 decision: **{section['stage1_decision']}**",
            "",
        ]
    return "\n".join(lines) + "\n"


def write_stage1(
    *,
    repo_root: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    repo_root = Path(repo_root)
    out_dir = repo_root / "research/qfe_v21_state_space"
    summary = out_dir / "RESULT_V1.json"
    markdown = out_dir / "RESULT_V1.md"
    row_path = out_dir / "ROWS_V1.jsonl.gz"
    raw = "".join(canonical_json(row) + "\n" for row in rows).encode()
    gz = gzip.compress(raw, compresslevel=9, mtime=0)
    enriched = {
        **result,
        "rows_file": row_path.name,
        "rows_file_sha256": hashlib.sha256(gz).hexdigest(),
    }
    json_payload = canonical_json(enriched) + "\n"
    md_payload = render_markdown(enriched)
    for path, payload in (
        (summary, json_payload),
        (markdown, md_payload),
    ):
        if path.exists() and path.read_text() != payload:
            raise FileExistsError(path)
        if not path.exists():
            path.write_text(payload)
    if row_path.exists():
        if row_path.read_bytes() != gz:
            raise FileExistsError(row_path)
    else:
        row_path.write_bytes(gz)
