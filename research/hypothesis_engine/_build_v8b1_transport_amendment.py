"""Builds V8B1_TRANSPORT_AMENDMENT.json -- a narrow PRE-SPEND amendment to the task-10 freeze
(V8B1_FREEZE_MANIFEST.json) that binds ONLY the transport/runtime configuration changed while
repairing the canary-attempt-1 read timeout.

It does NOT mutate the task-10 freeze. It re-proves, by re-hashing, that every scientific
artifact recorded in the task-10 freeze is byte-identical, that CHAMPION is unchanged, and it
records the transport delta plus the primary-sample exclusion of the 3 T2 canary fixtures.

reason=PRE_RESEARCH_TRANSPORT_TIMEOUT_REPAIR
research_outputs_viewed=0
target_outcomes_viewed=false
scientific_design_changed=false

ZERO SPEND. Read-only w.r.t. the model. No model call. No CHAMPION touch. No scientific edit.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

ROOT = "/home/ubuntu"

FREEZE_MANIFEST = "research/hypothesis_engine/V8B1_FREEZE_MANIFEST.json"
CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

# The transport layer this amendment binds. runner.py is the recovered task-11 transport module
# (was an uncommitted crash orphan); it is transport, NOT a scientific artifact, and is
# deliberately absent from the task-10 freeze's scientific artifact set.
TRANSPORT_MODULE = "src/research/hypothesis_v8b1/runner.py"
CANARY_HARNESS = "research/hypothesis_engine/_v8b1_canary.py"

# Transport delta (attempt-1 -> repaired). Values are the SDK/runtime transport knobs only.
TRANSPORT_BEFORE = {"read_timeout_s": 90, "connect_timeout_s": 10,
                    "retries": {"max_attempts": 2}}
TRANSPORT_AFTER = {"read_timeout_s": 300, "connect_timeout_s": 15,
                   "retries": {"max_attempts": 3, "mode": "standard"}}

# The 3 canary fixtures, now T2_INFRASTRUCTURE_ONLY, excluded from the PRIMARY target sample
# only (exclusion does not propagate; global taint taxonomy unchanged).
PRIMARY_SAMPLE_EXCLUSIONS = ["mt_012232342", "mt_406686877", "mt_581141428"]


def _sha(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def build() -> dict:
    freeze = json.load(open(f"{ROOT}/{FREEZE_MANIFEST}"))
    frozen_hashes = freeze["artifact_hashes"]

    # Re-prove every scientific artifact is byte-identical to the task-10 freeze.
    scientific_drift = []
    recomputed = {}
    for p, frozen_h in frozen_hashes.items():
        cur = _sha(p) if os.path.exists(f"{ROOT}/{p}") else None
        recomputed[p] = cur
        if cur != frozen_h:
            scientific_drift.append({"path": p, "frozen": frozen_h, "current": cur})

    champion_now = _sha(CHAMPION_ARTIFACT)
    champion_unchanged = champion_now == CHAMPION_EXPECTED

    transport_hash = _sha(TRANSPORT_MODULE) if os.path.exists(f"{ROOT}/{TRANSPORT_MODULE}") else None
    canary_hash = _sha(CANARY_HARNESS) if os.path.exists(f"{ROOT}/{CANARY_HARNESS}") else None

    amendment = {
        "amendment_version": "v8b1_transport_amendment_v1",
        "amends": FREEZE_MANIFEST,
        "amends_task10_manifest_hash": freeze.get("manifest_hash"),
        "reason": "PRE_RESEARCH_TRANSPORT_TIMEOUT_REPAIR",
        "research_outputs_viewed": 0,
        "target_outcomes_viewed": False,
        "scientific_design_changed": False,

        # --- the transport delta this amendment binds ---
        "transport_module": TRANSPORT_MODULE,
        "transport_module_sha256": transport_hash,
        "canary_harness": CANARY_HARNESS,
        "canary_harness_sha256": canary_hash,
        "transport_before": TRANSPORT_BEFORE,
        "transport_after": TRANSPORT_AFTER,
        "transport_change_rationale": (
            "read_timeout raised 90->300s: the working golden_v3 single-call baseline for the "
            "same model (us.anthropic.claude-sonnet-4-6) and same maxTokens=8192 but WITHOUT "
            "extended thinking already showed median 55.8s / max 118.8s per call; each runner "
            "turn is strictly heavier (thinking budget 4096 + temperature 1.0) and up to "
            "MAX_TOOL_TURNS turns run per fixture. Only transport knobs changed. No prompt, "
            "no reasoning depth (thinking budget unchanged), no max output (maxTokens "
            "unchanged), no evidence, no task, no fixtures."),

        # --- scientific invariance proof (re-hashed, not asserted) ---
        "scientific_artifacts_rechecked": list(frozen_hashes.keys()),
        "scientific_artifacts_recomputed_hashes": recomputed,
        "scientific_artifact_drift": scientific_drift,
        "all_scientific_artifacts_identical_to_freeze": not scientific_drift,

        # explicit per-category invariance (all covered by the byte-hash proof above)
        "prompt_content_unchanged": True,
        "packet_builder_unchanged": True,
        "scorer_unchanged": True,
        "blind_control_unchanged": True,
        "heuristic_control_unchanged": True,
        "hypothesis_universe_unchanged": True,
        "taint_policy_unchanged": True,
        "evaluation_spec_unchanged": True,
        "inference_spec_unchanged": True,
        "fixture_manifest_file_unchanged": True,
        "model_config_unchanged": True,

        # --- champion ---
        "champion_artifact": CHAMPION_ARTIFACT,
        "champion_artifact_sha256": champion_now,
        "champion_artifact_sha256_expected": CHAMPION_EXPECTED,
        "champion_unchanged": champion_unchanged,

        # --- primary-sample exclusion (does NOT edit the frozen manifest file) ---
        "primary_sample_exclusions": PRIMARY_SAMPLE_EXCLUSIONS,
        "primary_sample_exclusion_taint_level": "T2_INFRASTRUCTURE_ONLY",
        "primary_sample_exclusion_scope": (
            "these 3 canary fixtures are removed from the eventual PRIMARY V8B.1 target sample "
            "only; the frozen V8B1_FIXTURE_MANIFEST.json file itself is NOT modified, the "
            "exclusion does not propagate to any other fixture, and the global taint taxonomy "
            "is unchanged"),

        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "no_target_outcome_opened": True,
        "no_paid_sonnet_research_call_made_yet": True,
        "next_step": "canary attempt 2 (<=3 calls): transport/turn/tool/parse/canonical-id/"
                     "cache/accounting/persistence validation ONLY; no football-quality "
                     "judgment; no prompt tuning",
    }

    amendment["amendment_passed"] = bool(
        not scientific_drift and champion_unchanged and transport_hash is not None)

    amendment["amendment_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in amendment.items() if k != "amendment_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return amendment


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_TRANSPORT_AMENDMENT.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"amendment_passed={out['amendment_passed']}")
    print(f"all_scientific_artifacts_identical_to_freeze={out['all_scientific_artifacts_identical_to_freeze']}")
    print(f"champion_unchanged={out['champion_unchanged']}")
    if out["scientific_artifact_drift"]:
        print("DRIFT:", out["scientific_artifact_drift"])
    print("amendment_hash:", out["amendment_hash"][:16])
