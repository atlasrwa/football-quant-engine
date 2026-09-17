"""Builds V8B1_ORCHESTRATION_AMENDMENT.json -- a narrow PRE-SPEND amendment to the task-10
freeze that binds ONLY the deterministic termination/resource contract added to the runner
(BOUNDED_SEARCH_THEN_FORCED_SUBMIT) after canary attempt 2 demonstrated non-terminating tool
search with unbounded token growth.

It supersedes V8B1_TRANSPORT_AMENDMENT.json (which bound the pre-orchestration runner hash):
the transport repair is CARRIED FORWARD (read/connect timeout + retry unchanged) and now lives
in the same runner module this amendment binds.

It does NOT mutate the task-10 freeze. It re-proves, by re-hashing, that every scientific
artifact recorded in the task-10 freeze is byte-identical, that CHAMPION is unchanged, and it
records the orchestration delta.

reason=CANARY_DEMONSTRATED_NONTERMINATING_TOOL_SEARCH_AND_UNBOUNDED_TOKEN_GROWTH
target_outcomes_viewed=false
research_experiment_started=false
termination_contract_changed=true
(football_prompt/evidence_packet/reasoning_budget/hypothesis_universe/scorer/controls/inference
 all changed=false)

ZERO SPEND. Read-only w.r.t. the model. No model call. No CHAMPION touch. No scientific edit.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

ROOT = "/home/ubuntu"

FREEZE_MANIFEST = "research/hypothesis_engine/V8B1_FREEZE_MANIFEST.json"
TRANSPORT_AMENDMENT = "research/hypothesis_engine/V8B1_TRANSPORT_AMENDMENT.json"
CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

# The orchestration layer this amendment binds. runner.py is the termination/transport module;
# it is NOT a scientific artifact and is deliberately absent from the task-10 scientific set.
ORCHESTRATION_MODULE = "src/research/hypothesis_v8b1/runner.py"
ORCHESTRATION_TEST = "tests/research/hypothesis_v8b1/test_runner_termination.py"
CANARY_HARNESS = "research/hypothesis_engine/_v8b1_canary.py"

# The frozen termination contract parameters (mirror runner.py constants; re-derived here so a
# drift between the doc and the code is caught).
TERMINATION_CONTRACT = {
    "contract": "BOUNDED_SEARCH_THEN_FORCED_SUBMIT",
    "max_search_calls": 6,
    "final_forced_submit_calls": 1,
    "max_tool_turns_derived": 7,
    "max_tool_turns_formula": "max_search_calls + final_forced_submit_calls",
    "forced_submit_disables_thinking": True,
    "forced_submit_disables_thinking_reason": (
        "this model rejects forced tool_choice while extended thinking is enabled "
        "('Thinking may not be enabled when tool_choice forces tool use'); the forced final "
        "turn therefore disables thinking. It requests only the terminal action, not new "
        "reasoning, so reasoning depth for the research (search) phase is unchanged."),
    "early_submit_accepted": True,
    "abstain_valid_zero_to_eight_selections": True,
    "never_fabricates": True,
}

# Transport config carried forward unchanged from the transport amendment.
TRANSPORT_CARRIED_FORWARD = {"read_timeout_s": 300, "connect_timeout_s": 15,
                             "retries": {"max_attempts": 3, "mode": "standard"}}

PRIMARY_SAMPLE_EXCLUSIONS = ["mt_012232342", "mt_406686877", "mt_581141428"]


def _sha(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _verify_runner_constants():
    """Import the live runner and confirm its constants match this document, so the frozen
    contract can never silently diverge from the code it claims to bind."""
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from src.research.hypothesis_v8b1 import runner as mod
    return {
        "max_search_calls_match": mod.MAX_SEARCH_CALLS == TERMINATION_CONTRACT["max_search_calls"],
        "final_forced_submit_match": mod.FINAL_FORCED_SUBMIT_CALLS
            == TERMINATION_CONTRACT["final_forced_submit_calls"],
        "max_tool_turns_match": mod.MAX_TOOL_TURNS == TERMINATION_CONTRACT["max_tool_turns_derived"],
        "transport_match": (mod.READ_TIMEOUT_S == TRANSPORT_CARRIED_FORWARD["read_timeout_s"]
                            and mod.CONNECT_TIMEOUT_S == TRANSPORT_CARRIED_FORWARD["connect_timeout_s"]
                            and mod.RETRY_MAX_ATTEMPTS
                                == TRANSPORT_CARRIED_FORWARD["retries"]["max_attempts"]
                            and mod.RETRY_MODE == TRANSPORT_CARRIED_FORWARD["retries"]["mode"]),
        "version_stamp": mod.version_stamp(),
    }


def build() -> dict:
    freeze = json.load(open(f"{ROOT}/{FREEZE_MANIFEST}"))
    frozen_hashes = freeze["artifact_hashes"]

    scientific_drift = []
    recomputed = {}
    for p, frozen_h in frozen_hashes.items():
        cur = _sha(p) if os.path.exists(f"{ROOT}/{p}") else None
        recomputed[p] = cur
        if cur != frozen_h:
            scientific_drift.append({"path": p, "frozen": frozen_h, "current": cur})

    champion_now = _sha(CHAMPION_ARTIFACT)
    champion_unchanged = champion_now == CHAMPION_EXPECTED

    runner_checks = _verify_runner_constants()
    constants_ok = all(v for k, v in runner_checks.items() if k.endswith("_match"))

    prior_transport = None
    if os.path.exists(f"{ROOT}/{TRANSPORT_AMENDMENT}"):
        prior_transport = json.load(open(f"{ROOT}/{TRANSPORT_AMENDMENT}"))

    amendment = {
        "amendment_version": "v8b1_orchestration_amendment_v1",
        "amends": FREEZE_MANIFEST,
        "amends_task10_manifest_hash": freeze.get("manifest_hash"),
        "supersedes": TRANSPORT_AMENDMENT,
        "supersedes_transport_amendment_hash": (prior_transport or {}).get("amendment_hash"),
        "reason": "CANARY_DEMONSTRATED_NONTERMINATING_TOOL_SEARCH_AND_UNBOUNDED_TOKEN_GROWTH",
        "target_outcomes_viewed": False,
        "research_experiment_started": False,

        # --- the scientific-invariance claims required by the instruction ---
        "football_prompt_changed": False,
        "evidence_packet_changed": False,
        "reasoning_budget_changed": False,
        "hypothesis_universe_changed": False,
        "scorer_changed": False,
        "controls_changed": False,
        "inference_changed": False,
        "termination_contract_changed": True,

        # --- the orchestration delta this amendment binds ---
        "orchestration_module": ORCHESTRATION_MODULE,
        "orchestration_module_sha256": _sha(ORCHESTRATION_MODULE),
        "orchestration_test": ORCHESTRATION_TEST,
        "orchestration_test_sha256": _sha(ORCHESTRATION_TEST),
        "canary_harness": CANARY_HARNESS,
        "canary_harness_sha256": _sha(CANARY_HARNESS),
        "termination_contract": TERMINATION_CONTRACT,
        "transport_carried_forward": TRANSPORT_CARRIED_FORWARD,
        "runner_constants_verified_against_doc": runner_checks,
        "runner_constants_match": constants_ok,

        # --- scientific invariance proof (re-hashed, not asserted) ---
        "scientific_artifacts_rechecked": list(frozen_hashes.keys()),
        "scientific_artifacts_recomputed_hashes": recomputed,
        "scientific_artifact_drift": scientific_drift,
        "all_scientific_artifacts_identical_to_freeze": not scientific_drift,

        # --- champion ---
        "champion_artifact": CHAMPION_ARTIFACT,
        "champion_artifact_sha256": champion_now,
        "champion_artifact_sha256_expected": CHAMPION_EXPECTED,
        "champion_unchanged": champion_unchanged,

        # --- primary-sample exclusion carried forward (frozen manifest file NOT edited) ---
        "primary_sample_exclusions": PRIMARY_SAMPLE_EXCLUSIONS,
        "primary_sample_exclusion_taint_level": "T2_INFRASTRUCTURE_ONLY",
        "primary_sample_exclusion_scope": (
            "carried forward from the transport amendment: these 3 canary fixtures are removed "
            "from the eventual PRIMARY V8B.1 target sample only; the frozen "
            "V8B1_FIXTURE_MANIFEST.json is NOT modified and the exclusion does not propagate"),

        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "no_target_outcome_opened": True,
        "no_paid_sonnet_research_call_made_yet": True,
        "next_step": "canary attempt 3 (<=3 T2 fixtures): verify deterministic termination "
                     "(OK_WITH_SELECTIONS or OK_ABSTAIN), bounded tool calls, canonical output, "
                     "outcome-blind, cache-safe, cost-bounded; then economics projection; STOP.",
    }

    amendment["amendment_passed"] = bool(
        not scientific_drift and champion_unchanged and constants_ok)

    amendment["amendment_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in amendment.items() if k != "amendment_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return amendment


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_ORCHESTRATION_AMENDMENT.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"amendment_passed={out['amendment_passed']}")
    print(f"all_scientific_artifacts_identical_to_freeze={out['all_scientific_artifacts_identical_to_freeze']}")
    print(f"champion_unchanged={out['champion_unchanged']}")
    print(f"runner_constants_match={out['runner_constants_match']}")
    if out["scientific_artifact_drift"]:
        print("DRIFT:", out["scientific_artifact_drift"])
    print("amendment_hash:", out["amendment_hash"][:16])
