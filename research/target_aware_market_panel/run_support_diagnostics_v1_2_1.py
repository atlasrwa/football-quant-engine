"""Outcome-blind V1.2.1 support rerun on the exact frozen V1 scoring panel.

Only the frozen V1.2 prehistory corpus is added to feature construction. Scored rows, folds,
templates, the 60% screen, similarity semantics, and CHAMPION remain unchanged.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.target_aware_market_panel import run_support_diagnostics as V1D  # noqa: E402
from research.target_aware_market_panel import v1_2_freeze_prehistory as RF  # noqa: E402
from src.research.dual_provider_llm import packet as P  # noqa: E402
from src.research.target_aware_market_panel import cohort_packets as CP  # noqa: E402
from src.research.target_aware_market_panel import panel as PN  # noqa: E402
from src.research.target_aware_market_panel import support as SP  # noqa: E402
from src.research.target_aware_market_panel import support_v12 as S12  # noqa: E402

OUT = ROOT / "research/target_aware_market_panel"
CACHE = "/home/ubuntu/data/thestatsapi/championship"
SUPPORT_PLAN = OUT / "V1_2_1_SUPPORT_EXECUTION_PLAN_V1.json"
RAW_MANIFEST = OUT / "V1_2_PREHISTORY_RAW_MANIFEST_V1.json"
REGISTRY = OUT / "SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json"
FOLDS = OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
PLAN_SHA256 = "c87ec9a1413f5ba8b8126d2dd4db2b00fdd7cf24688fe7ae4b5474749e859dbb"
EXPECTED_CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
EXPECTED_PANEL_ROWS = 5620
V12_ABORT = OUT / "V1_2_EXECUTION_ABORT_V1.json"
EXPECTED_V12_ABORT_SHA256 = "ea97968682054f1b507efe8335e065bf7390881c66e51047351e09d123e2c90f"
EXPECTED_FOLD_ROWS_SHA256 = "9fca0ec2860ed13cda0368502978445b9444419eece690cba685449c26bf3270"
PANEL_END_UTC = "2026-09-14T23:59:59Z"
OUTPUTS = (
    "SOL_PANEL_SUPPORT_DIAGNOSTICS_V1_2_1.json",
    "SOL_PANEL_SUPPORT_AUDIT_V1_2_1.md",
    "V1_2_1_EVALUABILITY_GATE_DECISION_V1.json",
    "SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1_2_1.json",
)


def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_self_template_sha256() -> str:
    text = Path(__file__).read_text()
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if line.startswith("PLAN_SHA256 = ")]
    if len(hits) != 1:
        raise RuntimeError("SUPPORT_RUNNER_PLAN_BINDING_NOT_UNIQUE")
    newline = "\n" if lines[hits[0]].endswith("\n") else ""
    lines[hits[0]] = 'PLAN_SHA256 = "__PIN_AFTER_PLAN_FREEZE__"' + newline
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def dump(path: Path, obj) -> str:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return fsha(path)


def load_prehistory(plan: dict) -> tuple[dict, dict]:
    if fsha(RAW_MANIFEST) != plan["prehistory_raw_manifest_sha256"]:
        raise RuntimeError("RAW_PREHISTORY_MANIFEST_HASH_MISMATCH")
    raw_manifest = json.loads(RAW_MANIFEST.read_text())
    discovery = json.loads(RF.DISCOVERY.read_text())
    exact = RF.exact_fixture_index(discovery)
    fixtures = RF.load_fixtures(discovery, exact)
    if set(raw_manifest["raw_files"]) != set(exact):
        raise RuntimeError("RAW_MANIFEST_EXACT_SET_MISMATCH")
    payloads = []
    n200 = n404 = 0
    for mid in sorted(exact):
        wrapper = RF.load_terminal(mid)
        rec = raw_manifest["raw_files"][mid]
        actual_sha = fsha(RF.RAW_ROOT / f"{mid}.json")
        status = int(wrapper["http_status"])
        if actual_sha != rec["sha256"] or status != int(rec["http_status"]):
            raise RuntimeError(f"RAW_FILE_BINDING_MISMATCH:{mid}")
        if status == 200:
            payloads.append((f"{mid}.json", wrapper["payload"]))
            n200 += 1
        else:
            n404 += 1
    stats_ok, conflicts = P.build_stats_map(payloads)
    if conflicts or len(stats_ok) != n200:
        raise RuntimeError("PREHISTORY_STATS_NORMALIZATION_CONFLICT")
    history = P.normalize_history(fixtures, stats_ok, conflicts)
    if len(history) != len(exact):
        raise RuntimeError(f"PREHISTORY_NORMALIZED_COUNT_MISMATCH:{len(history)}")
    return history, {
        "n_prehistory": len(history), "n_http_200": n200, "n_http_404": n404,
        "n_prehistory_stats_conflicts": len(conflicts),
    }


def memoize_history(h: PN.PanelHistory) -> None:
    orig_prior = h.prior
    prior_cache = {}
    def cached_prior(team, before, venue=None):
        key = (str(team), int(before), venue)
        if key not in prior_cache:
            prior_cache[key] = orig_prior(team, before, venue)
        return prior_cache[key]
    h.prior = cached_prior

    orig_strength = h.strength
    strength_cache = {}
    def cached_strength(team, comp, before):
        key = (str(team), str(comp), int(before))
        if key not in strength_cache:
            strength_cache[key] = orig_strength(team, comp, before)
        return strength_cache[key]
    h.strength = cached_strength

    orig_style = PN.style_profile
    profile_cache = {}
    def cached_style(hh, team, venue, dims, before, comp):
        key = (str(team), venue, V1D._profile_key(dims), int(before), str(comp))
        if key not in profile_cache:
            profile_cache[key] = orig_style(hh, team, venue, dims, before, comp)
        return profile_cache[key]
    PN.style_profile = cached_style


def audit_md(gate: dict, history_meta: dict, threshold: float) -> str:
    lines = [
        "# Sol V1.2.1 Outcome-Blind Evaluability Audit", "",
        f"**Decision:** `{gate['decision']}`", "",
        "No cohort target outcomes, market results, prices, model fits, calibration, "
        "or predictive OOS scores were read.", "",
        f"- Original scored rows: **{EXPECTED_PANEL_ROWS}**",
        f"- Frozen V1.2 prehistory fixtures: **{history_meta['n_prehistory']}**",
        f"- Training-fold coverage threshold: **{threshold:.0%}** (unchanged)", "",
        "| Family | Fold | class-C passing | similarity passing |",
        "|---|---:|---:|---:|",
    ]
    for family, fold_map in sorted(gate["details"].items()):
        for fold_id, rec in sorted(fold_map.items(), key=lambda kv: int(kv[0])):
            lines.append(
                f"| {family} | {fold_id} | {rec['n_class_c_pass']} | "
                f"{rec['n_similarity_pass']} |"
            )
    lines += [
        "",
        "PASS requires both counts to be greater than zero for every family in every fold. "
        "A FAIL aborts V1.2.1 before target construction; no threshold, fold, template, "
        "or extra-season rescue is permitted.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    args = ap.parse_args()

    if PLAN_SHA256.startswith("__"):
        raise SystemExit("SUPPORT_PLAN_SHA_NOT_PINNED")
    head = git("rev-parse", "HEAD")
    if head != args.authorized_head:
        raise SystemExit(f"HEAD_MISMATCH expected={args.authorized_head} actual={head}")
    if git("status", "--porcelain"):
        raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(SUPPORT_PLAN) != PLAN_SHA256:
        raise SystemExit("SUPPORT_PLAN_HASH_MISMATCH")
    if fsha(CHAMPION) != EXPECTED_CHAMPION_SHA256:
        raise SystemExit("CHAMPION_HASH_MISMATCH")
    if fsha(V12_ABORT) != EXPECTED_V12_ABORT_SHA256:
        raise SystemExit("V1_2_ABORT_ARTIFACT_HASH_MISMATCH")
    for name in OUTPUTS:
        if (OUT / name).exists():
            raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{name}")

    plan = json.loads(SUPPORT_PLAN.read_text())
    if normalized_self_template_sha256() != plan["support_runner_template_sha256"]:
        raise SystemExit("SUPPORT_RUNNER_TEMPLATE_HASH_MISMATCH")
    for relpath, expected in sorted(plan["semantic_module_sha256"].items()):
        path = ROOT / relpath
        if not path.exists() or fsha(path) != expected:
            raise SystemExit(f"SEMANTIC_MODULE_HASH_MISMATCH:{relpath}")
    threshold = float(plan["training_coverage_threshold"])
    if threshold != S12.COVERAGE_THRESHOLD:
        raise SystemExit("SUPPORT_PLAN_THRESHOLD_MISMATCH")
    if int(plan["n_scored_rows"]) != EXPECTED_PANEL_ROWS:
        raise SystemExit("SUPPORT_PLAN_ROW_COUNT_MISMATCH")

    folds = json.loads(FOLDS.read_text())
    if folds["n_panel_rows"] != EXPECTED_PANEL_ROWS or \
            folds["rows_sha256"] != EXPECTED_FOLD_ROWS_SHA256:
        raise SystemExit("FOLD_MANIFEST_MISMATCH")

    base_history, base_meta = CP.load_history(CACHE, include_gap_fetches=False)
    prehistory, pre_meta = load_prehistory(plan)
    overlap = sorted(set(base_history) & set(prehistory))
    if overlap:
        raise SystemExit(f"PREHISTORY_BASE_ID_OVERLAP:{overlap[:5]}")

    history = dict(prehistory)
    history.update(base_history)
    panel_end = calendar.timegm(time.strptime(PANEL_END_UTC, "%Y-%m-%dT%H:%M:%SZ"))
    h = PN.PanelHistory(PN.rows_from_history(history), panel_end)

    fold_rows = {r["match_id"]: r for r in folds["rows"]}
    fixtures = []
    for fr in folds["rows"]:
        hm = base_history.get(fr["match_id"])
        if hm is None or hm.kickoff_unix > panel_end or not hm.stats:
            raise SystemExit(f"ORIGINAL_PANEL_FIXTURE_MISSING:{fr['match_id']}")
        home = hm.fixture.get("home_team") or {}
        away = hm.fixture.get("away_team") or {}
        fixtures.append({
            "match_id": fr["match_id"],
            "kickoff": int(hm.kickoff_unix),
            "competition_id": str(hm.fixture.get("competition_id")),
            "home_team_id": str(home.get("id")),
            "away_team_id": str(away.get("id")),
        })
    if len(fixtures) != EXPECTED_PANEL_ROWS:
        raise SystemExit("PANEL_ROW_COUNT_MISMATCH")

    memoize_history(h)
    registry = json.loads(REGISTRY.read_text())
    templates = registry.get("templates") or []
    if len(templates) != int(plan["n_templates"]):
        raise SystemExit("TEMPLATE_COUNT_MISMATCH")

    match_ids = [f["match_id"] for f in fixtures]
    columns = {}
    metadata = {}
    per_template = []
    for item in templates:
        tpl = item["feature_template"]
        vals = []
        details = []
        for fx in fixtures:
            if tpl["template_type"] == S12.SIMILARITY_TYPE:
                detail = PN.similarity_detail(tpl, h, fx)
                details.append(detail)
                vals.append(None if detail is None else detail["value"])
            else:
                vals.append(PN.instantiate(tpl, h, fx))

        sig = item["canonical_signature_sha256"]
        rec = {k: item[k] for k in (
            "fixture_id", "family", "hypothesis_id", "market_id",
            "canonical_signature_sha256", "template_type"
        )}
        rec["coverage"] = SP.summarize_column(
            match_ids, fixtures, vals, fold_rows
        )
        rec["training_fold_coverage"] = {
            fold_id: S12.training_coverage(vals, fixtures, fold_def)
            for fold_id, fold_def in sorted(
                folds["folds"].items(), key=lambda kv: int(kv[0])
            )
        }
        if tpl["template_type"] == S12.SIMILARITY_TYPE:
            rec["similarity_support"] = SP.summarize_similarity_details(details)
            rec["style_strength_correlation"] = V1D._style_strength(
                tpl, h, fixtures
            )
        else:
            rec["similarity_support"] = None
            rec["style_strength_correlation"] = None
        per_template.append(rec)
        columns[sig] = vals
        metadata[sig] = {
            "family": item["family"],
            "market_id": item["market_id"],
            "hypothesis_id": item["hypothesis_id"],
        }

    near = SP.pairwise_near_duplicates(columns, metadata)
    gate_details, gate_pass = S12.evaluability_gate(
        per_template, folds, threshold
    )
    history_meta = {
        "n_original_history": len(base_history),
        "n_combined_history": len(history),
        "original_stats_conflicts": base_meta["n_stats_conflicts"],
        **pre_meta,
    }

    summary = {
        "n_templates": len(per_template),
        "n_with_any_support": sum(
            x["coverage"]["n_nonnull"] > 0 for x in per_template
        ),
        "n_zero_support": sum(
            x["coverage"]["n_nonnull"] == 0 for x in per_template
        ),
        "n_near_duplicate_pairs": len(near),
        "n_very_near_duplicate_pairs": sum(
            x["abs_r_ge_0_99"] for x in near
        ),
    }
    diagnostics = {
        "artifact_version": "target_aware_panel_support_v1_2_1",
        "authorized_execution_head": head,
        "support_execution_plan_sha256": PLAN_SHA256,
        "prehistory_raw_manifest_sha256":
            plan["prehistory_raw_manifest_sha256"],
        "n_panel_rows": len(fixtures),
        "history_meta": history_meta,
        "training_coverage_threshold": threshold,
        "summary": summary,
        "templates": per_template,
        "near_duplicate_pairs": near,
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
    }

    decision = (
        "PASS_V1_2_1_EVALUABILITY_GATE"
        if gate_pass else "ABORT_V1_2_1_BEFORE_OUTCOME_ACCESS"
    )
    gate = {
        "artifact_version": "target_aware_v1_2_1_evaluability_gate_decision_v1",
        "decision": decision,
        "gate_pass": gate_pass,
        "rule": (
            "for every family and every frozen fold: >=1 class-C feature and "
            ">=1 OPPONENT_SIMILARITY_CONDITIONAL feature must pass the "
            "unchanged 60% training-row coverage screen"
        ),
        "training_coverage_threshold": threshold,
        "details": gate_details,

        "failure_action": (
            "ABORT; do not lower threshold, move folds, remove early rows, "
            "add a third season, rewrite hypotheses, or run OOS"
        ),
        "pass_action": (
            "freeze and review this gate before any predictive OOS execution"
        ),
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "champion_changed": False,
    }

    diag_sha = dump(OUT / OUTPUTS[0], diagnostics)
    (OUT / OUTPUTS[1]).write_text(
        audit_md(gate, history_meta, threshold)
    )
    audit_sha = fsha(OUT / OUTPUTS[1])
    gate_sha = dump(OUT / OUTPUTS[2], gate)
    manifest = {
        "artifact_version": "sol_panel_support_freeze_manifest_v1_2_1",
        "authorized_execution_head": head,
        "support_execution_plan_sha256": PLAN_SHA256,
        "prehistory_raw_manifest_sha256":
            plan["prehistory_raw_manifest_sha256"],
        "diagnostics_sha256": diag_sha,
        "audit_sha256": audit_sha,
        "gate_decision_sha256": gate_sha,
        "decision": decision,
        "champion_sha256": fsha(CHAMPION),
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "champion_changed": False,
        "next_gate": (
            "REVIEW_FROZEN_V1_2_1_EVALUABILITY_PASS_BEFORE_PREDICTIVE_OOS"
            if gate_pass else "V1_2_1_ABORTED"
        ),
    }

    manifest_sha = dump(OUT / OUTPUTS[3], manifest)
    print(json.dumps({
        "status": "V1_2_1_SUPPORT_AND_EVALUABILITY_COMPLETE",
        "decision": decision,
        "gate_pass": gate_pass,
        "diagnostics_sha256": diag_sha,
        "audit_sha256": audit_sha,
        "gate_decision_sha256": gate_sha,
        "manifest_sha256": manifest_sha,
        "history_meta": history_meta,
        "target_outcomes_read": False,
        "model_fit": False,
        "oos_executed": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
