"""Freeze the outcome-blind V1.2 support execution plan after raw prehistory freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from src.research.target_aware_market_panel import panel as PN

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/target_aware_market_panel"
RAW_MANIFEST = OUT / "V1_2_PREHISTORY_RAW_MANIFEST_V1.json"
PLAN_OUT = OUT / "V1_2_SUPPORT_EXECUTION_PLAN_V1.json"
FOLDS = OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json"
REGISTRY = OUT / "SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json"
RESPONSES = OUT / "SOL_RESPONSE_MANIFEST_V1.json"
SCOPE = OUT / "V1_SCOPE_FREEZE_V1.json"
V1_GATE = OUT / "V1_OOS_GATE_DECISION_V1.json"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
PANEL_MODULE = ROOT / "src/research/target_aware_market_panel/panel.py"
FOLD_SHA256 = "f353068ec40864d56ac2c514a22e1199a9e237f58b1399e9739c71ae4488d3a1"
REGISTRY_SHA256 = "2367b9ea5b3bad10b66c2958599069d574d5bc8c829d6066dc04b75aa069bf1b"
RESPONSES_SHA256 = "79edc665876aca82ba9425eb741d74fa5252722b9b017dd10bf8f37744b46c6a"
SCOPE_SHA256 = "2d156e959b195af5b8847751bf5bd08ea7ce7259c4dcf41d329ac9810936055c"
V1_GATE_SHA256 = "67ba5372e280efa7175f5c58d02e86768f001e874f20ac1e1322b99f26432769"
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
EXPECTED_PANEL_ROWS = 5620
EXPECTED_FOLD_ROWS_SHA256 = "9fca0ec2860ed13cda0368502978445b9444419eece690cba685449c26bf3270"
EXPECTED_TEMPLATES = 124
EXPECTED_SIMILARITY = 116
COVERAGE_THRESHOLD = 0.60


def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def build_plan(authorized_head: str) -> dict:
    if git("rev-parse", "HEAD") != authorized_head:
        raise RuntimeError("HEAD_MISMATCH")
    if git("status", "--porcelain"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    frozen = {FOLDS: FOLD_SHA256, REGISTRY: REGISTRY_SHA256, RESPONSES: RESPONSES_SHA256,
              SCOPE: SCOPE_SHA256, V1_GATE: V1_GATE_SHA256, CHAMPION: CHAMPION_SHA256}
    for path, expected in frozen.items():
        if fsha(path) != expected:
            raise RuntimeError(f"FROZEN_INPUT_HASH_MISMATCH:{path}")
    if not RAW_MANIFEST.exists():
        raise RuntimeError("RAW_PREHISTORY_MANIFEST_MISSING")
    raw = json.loads(RAW_MANIFEST.read_text())
    if raw.get("n_terminal") != 4994 or raw.get("target_outcomes_read") is not False:
        raise RuntimeError("RAW_PREHISTORY_MANIFEST_NOT_COMPLETE")
    folds = json.loads(FOLDS.read_text())
    if folds.get("n_panel_rows") != EXPECTED_PANEL_ROWS or \
            folds.get("rows_sha256") != EXPECTED_FOLD_ROWS_SHA256:
        raise RuntimeError("FOLD_MANIFEST_MISMATCH")
    registry = json.loads(REGISTRY.read_text())
    templates = registry.get("templates") or []
    n_similarity = sum(x.get("template_type") == "OPPONENT_SIMILARITY_CONDITIONAL"
                       for x in templates)
    if len(templates) != EXPECTED_TEMPLATES or n_similarity != EXPECTED_SIMILARITY:
        raise RuntimeError("TEMPLATE_COUNT_MISMATCH")
    return {
        "artifact_version": "target_aware_v1_2_support_execution_plan_v1",
        "authorized_plan_head": authorized_head,
        "prehistory_raw_manifest_sha256": fsha(RAW_MANIFEST),
        "prehistory_raw_files_aggregate_sha256": raw["raw_files_aggregate_sha256"],
        "fold_manifest_sha256": FOLD_SHA256,
        "fold_rows_sha256": EXPECTED_FOLD_ROWS_SHA256,
        "class_c_registry_sha256": REGISTRY_SHA256,
        "sol_response_manifest_sha256": RESPONSES_SHA256,
        "v1_scope_freeze_sha256": SCOPE_SHA256,
        "v1_gate_decision_sha256": V1_GATE_SHA256,
        "champion_sha256": CHAMPION_SHA256,
        "panel_module_sha256": fsha(PANEL_MODULE),
        "n_scored_rows": EXPECTED_PANEL_ROWS,
        "n_templates": EXPECTED_TEMPLATES,
        "n_similarity_templates": EXPECTED_SIMILARITY,
        "training_coverage_threshold": COVERAGE_THRESHOLD,
        "history_rule": "original V1 history plus frozen V1.2 prehistory; backfill is history-only",
        "scored_population_rule": "exact original 5,620 V1 fold-manifest rows only",
        "include_gap_fetches": False,
        "similarity_parameters": {
            "profile_window": PN.PROFILE_WINDOW,
            "min_profile_per_dim": PN.MIN_PROFILE_PER_DIM,
            "min_similarity_history": PN.MIN_SIMILARITY_HISTORY,
            "neighbor_fraction": PN.NEIGHBOR_FRACTION,
            "min_neighbors": PN.MIN_NEIGHBORS,
            "shrinkage_kappa": PN.SHRINKAGE_KAPPA,
        },
        "evaluability_gate": {
            "all_families_have_class_c_in_every_fold": True,
            "all_families_have_similarity_in_every_fold": True,
            "threshold_must_not_change": True,
        },
        "forbidden_before_gate_freeze": [
            "target settlement", "target label construction", "M0 fit", "M1 fit",
            "calibration", "Log Loss", "Brier", "ECE", "market comparison", "prices",
            "prospective promotion", "CHAMPION modification",
        ],
        "target_outcomes_read": False, "market_results_read": False,
        "model_fit": False, "oos_executed": False, "champion_changed": False,
        "next_gate": "RUN_AND_FREEZE_OUTCOME_BLIND_V1_2_SUPPORT_AND_EVALUABILITY_DECISION",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    args = ap.parse_args()
    if PLAN_OUT.exists():
        raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{PLAN_OUT}")
    doc = build_plan(args.authorized_head)
    PLAN_OUT.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "V1_2_SUPPORT_EXECUTION_PLAN_FROZEN",
        "plan_sha256": fsha(PLAN_OUT),
        "prehistory_raw_manifest_sha256": doc["prehistory_raw_manifest_sha256"],
        "n_scored_rows": doc["n_scored_rows"], "n_templates": doc["n_templates"],
        "n_similarity_templates": doc["n_similarity_templates"],
        "training_coverage_threshold": doc["training_coverage_threshold"],
        "target_outcomes_read": False, "model_fit": False, "oos_executed": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
