"""Builds V8B1_FREEZE_MANIFEST.json -- the single artifact recording that every required spec
is frozen (hashed, committed) BEFORE any paid Sonnet call toward the actual experiment. This is
task 10's gate: after this file is written and committed, no listed artifact may change until
V8B1_SELECTION_FREEZE.json exists and target outcomes are opened, per the no-mid-run-tuning
rule carried from the V8B instructions into V8B.1.

ZERO SPEND. Read-only. No model call. No CHAMPION touch.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

ROOT = "/home/ubuntu"

REQUIRED_MD_SPECS = [
    "research/hypothesis_engine/V8B_ABORT_REPORT.md",
    "research/hypothesis_engine/V8B1_SCORER_SPEC.md",
    "research/hypothesis_engine/V8B1_AGGREGATION_INFERENCE_SPEC.md",
    "research/hypothesis_engine/V8B1_HYPOTHESIS_SEARCH_SPEC.md",
    "research/hypothesis_engine/V8B1_EVIDENCE_PACKET_SPEC.md",
    "research/hypothesis_engine/V8B1_RESEARCH_PROTOCOL.md",
    "research/hypothesis_engine/V8B1_BLIND_CONTROL_SPEC.md",
    "research/hypothesis_engine/V8B1_HEURISTIC_SPEC.md",
]
REQUIRED_JSON_ARTIFACTS = [
    "research/hypothesis_engine/V8B_TAINT_REGISTRY.json",
    "research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json",
    "research/hypothesis_engine/V8B1_CHRONOLOGICAL_BLOCKS.json",
    "research/hypothesis_engine/V8B1_MODEL_CONFIG.json",
]
REQUIRED_CODE_MODULES = [
    "src/research/hypothesis_v8b1/scorer.py",
    "src/research/hypothesis_v8b1/search.py",
    "src/research/hypothesis_v8b1/packet.py",
    "src/research/hypothesis_v8b1/prompt.py",
    "src/research/hypothesis_v8b1/controls.py",
]
REQUIRED_TEST_MODULES = [
    "tests/research/hypothesis_v8b1/test_scorer.py",
    "tests/research/hypothesis_v8b1/test_search.py",
    "tests/research/hypothesis_v8b1/test_packet.py",
    "tests/research/hypothesis_v8b1/test_prompt.py",
    "tests/research/hypothesis_v8b1/test_controls.py",
]

CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"


def _sha(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def build() -> dict:
    all_paths = (REQUIRED_MD_SPECS + REQUIRED_JSON_ARTIFACTS + REQUIRED_CODE_MODULES
                + REQUIRED_TEST_MODULES)
    missing = [p for p in all_paths if not os.path.exists(f"{ROOT}/{p}")]

    tracked = set(_git("ls-files").splitlines())
    untracked = [p for p in all_paths if p not in tracked]

    porcelain = _git("status", "--porcelain")
    dirty_listed = [p for p in all_paths
                    if any(line.strip().endswith(p) for line in porcelain.splitlines())]

    hashes = {p: _sha(p) for p in all_paths if p not in missing}

    manifest = {
        "freeze_manifest_version": "v8b1_freeze_manifest_v1",
        "gate": "TASK_10_PRE_SPEND_FREEZE",
        "required_md_specs": REQUIRED_MD_SPECS,
        "required_json_artifacts": REQUIRED_JSON_ARTIFACTS,
        "required_code_modules": REQUIRED_CODE_MODULES,
        "required_test_modules": REQUIRED_TEST_MODULES,
        "artifact_hashes": hashes,
        "missing_artifacts": missing,
        "artifacts_not_git_tracked": untracked,
        "artifacts_with_uncommitted_changes": dirty_listed,
        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "champion_artifact_sha256": _sha(CHAMPION_ARTIFACT),
        "champion_artifact_sha256_expected": (
            "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"),
        "gate_passed": (not missing and not untracked and not dirty_listed
                        and _sha(CHAMPION_ARTIFACT) ==
                        "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"),
        "no_target_outcome_opened": True,
        "no_paid_sonnet_call_toward_experiment_made_yet": True,
        "next_step": "3-call canary (transport/schema/parser/canonical-ID-resolution/caching/"
                     "token-budget validation only; no prompt tuning based on liking the "
                     "generated football content)",
    }
    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return manifest


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_FREEZE_MANIFEST.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"gate_passed={out['gate_passed']}")
    if not out["gate_passed"]:
        print("missing:", out["missing_artifacts"])
        print("untracked:", out["artifacts_not_git_tracked"])
        print("dirty:", out["artifacts_with_uncommitted_changes"])
    print("hash:", out["manifest_hash"][:16])
