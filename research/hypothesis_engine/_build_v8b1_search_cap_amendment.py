"""Builds V8B1_SEARCH_CAP_AMENDMENT.json -- a narrow PRE-SPEND amendment that makes
MAX_SEARCH_CALLS=6 a TRUE EXECUTION CAP rather than a between-turn threshold.

Background: under the orchestration amendment the budget was checked between turns, so a single
Sonnet response containing several search_hypotheses calls could push the executed search count
to 8 (observed in attempt 3). This amendment binds the runner change that executes only the
remaining allowed searches within a turn and returns a deterministic SEARCH_BUDGET_EXHAUSTED
tool result for every excess call (keeping the conversation structurally valid), then forces
submit_selections on the next turn.

It supersedes V8B1_ORCHESTRATION_AMENDMENT.json. Transport repair + the bounded-search-then-
forced-submit contract are carried forward; only the cap-enforcement mechanics change.

reason=SEARCH_BUDGET_MADE_TRUE_EXECUTION_CAP
target_outcomes_viewed=false
research_experiment_started=false
termination_contract_changed=true
(football_prompt/evidence_packet/reasoning_budget/hypothesis_universe/search_ranking/scorer/
 controls/inference all changed=false)

ZERO SPEND. No model call. No CHAMPION touch. No scientific edit.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

ROOT = "/home/ubuntu"

FREEZE_MANIFEST = "research/hypothesis_engine/V8B1_FREEZE_MANIFEST.json"
ORCHESTRATION_AMENDMENT = "research/hypothesis_engine/V8B1_ORCHESTRATION_AMENDMENT.json"
CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

ORCHESTRATION_MODULE = "src/research/hypothesis_v8b1/runner.py"
ORCHESTRATION_TEST = "tests/research/hypothesis_v8b1/test_runner_termination.py"
CANARY_HARNESS = "research/hypothesis_engine/_v8b1_canary.py"

CAP_DELTA = {
    "before": "MAX_SEARCH_CALLS enforced as a between-turn threshold; a single response with "
              "multiple search calls could execute more than the budget (attempt 3 reached 8).",
    "after": "MAX_SEARCH_CALLS is a TRUE EXECUTION CAP: within any turn only "
             "(MAX_SEARCH_CALLS - search_calls) searches execute; each excess search call gets "
             "a deterministic SEARCH_BUDGET_EXHAUSTED tool result so every toolUseId is answered "
             "and the conversation stays valid; the next turn forces submit_selections.",
    "excess_tool_result_status": "SEARCH_BUDGET_EXHAUSTED",
    "max_search_calls": 6,
    "expected_runner_version": "v8b1_runner_v3_true_search_cap",
}

TERMINATION_CONTRACT_CARRIED_FORWARD = {
    "contract": "BOUNDED_SEARCH_THEN_FORCED_SUBMIT",
    "max_search_calls": 6, "final_forced_submit_calls": 1, "max_tool_turns_derived": 7,
    "forced_submit_disables_thinking": True, "early_submit_accepted": True,
    "abstain_valid_zero_to_eight_selections": True, "never_fabricates": True,
}
TRANSPORT_CARRIED_FORWARD = {"read_timeout_s": 300, "connect_timeout_s": 15,
                             "retries": {"max_attempts": 3, "mode": "standard"}}
PRIMARY_SAMPLE_EXCLUSIONS = ["mt_012232342", "mt_406686877", "mt_581141428"]


def _sha(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _verify_runner():
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from src.research.hypothesis_v8b1 import runner as mod
    vs = mod.version_stamp()
    return {
        "max_search_calls_match": mod.MAX_SEARCH_CALLS == CAP_DELTA["max_search_calls"],
        "max_tool_turns_match": mod.MAX_TOOL_TURNS == TERMINATION_CONTRACT_CARRIED_FORWARD[
            "max_tool_turns_derived"],
        "transport_match": (mod.READ_TIMEOUT_S == TRANSPORT_CARRIED_FORWARD["read_timeout_s"]
                            and mod.CONNECT_TIMEOUT_S == TRANSPORT_CARRIED_FORWARD["connect_timeout_s"]
                            and mod.RETRY_MAX_ATTEMPTS
                                == TRANSPORT_CARRIED_FORWARD["retries"]["max_attempts"]
                            and mod.RETRY_MODE == TRANSPORT_CARRIED_FORWARD["retries"]["mode"]),
        "true_cap_flag_match": vs.get("search_budget_is_true_execution_cap") is True,
        "runner_version_match": vs.get("runner_version") == CAP_DELTA["expected_runner_version"],
        "version_stamp": vs,
    }


def build() -> dict:
    freeze = json.load(open(f"{ROOT}/{FREEZE_MANIFEST}"))
    frozen_hashes = freeze["artifact_hashes"]

    scientific_drift, recomputed = [], {}
    for p, frozen_h in frozen_hashes.items():
        cur = _sha(p) if os.path.exists(f"{ROOT}/{p}") else None
        recomputed[p] = cur
        if cur != frozen_h:
            scientific_drift.append({"path": p, "frozen": frozen_h, "current": cur})

    champion_now = _sha(CHAMPION_ARTIFACT)
    champion_unchanged = champion_now == CHAMPION_EXPECTED

    checks = _verify_runner()
    constants_ok = all(v for k, v in checks.items() if k.endswith("_match"))

    prior = json.load(open(f"{ROOT}/{ORCHESTRATION_AMENDMENT}")) if os.path.exists(
        f"{ROOT}/{ORCHESTRATION_AMENDMENT}") else {}

    amendment = {
        "amendment_version": "v8b1_search_cap_amendment_v1",
        "amends": FREEZE_MANIFEST,
        "amends_task10_manifest_hash": freeze.get("manifest_hash"),
        "supersedes": ORCHESTRATION_AMENDMENT,
        "supersedes_orchestration_amendment_hash": prior.get("amendment_hash"),
        "reason": "SEARCH_BUDGET_MADE_TRUE_EXECUTION_CAP",
        "target_outcomes_viewed": False,
        "research_experiment_started": False,

        "football_prompt_changed": False,
        "evidence_packet_changed": False,
        "reasoning_budget_changed": False,
        "hypothesis_universe_changed": False,
        "search_ranking_changed": False,
        "scorer_changed": False,
        "controls_changed": False,
        "inference_changed": False,
        "termination_contract_changed": True,

        "cap_delta": CAP_DELTA,
        "termination_contract_carried_forward": TERMINATION_CONTRACT_CARRIED_FORWARD,
        "transport_carried_forward": TRANSPORT_CARRIED_FORWARD,

        "orchestration_module": ORCHESTRATION_MODULE,
        "orchestration_module_sha256": _sha(ORCHESTRATION_MODULE),
        "orchestration_test": ORCHESTRATION_TEST,
        "orchestration_test_sha256": _sha(ORCHESTRATION_TEST),
        "canary_harness": CANARY_HARNESS,
        "canary_harness_sha256": _sha(CANARY_HARNESS),
        "runner_checks": checks,
        "runner_checks_match": constants_ok,

        "scientific_artifacts_rechecked": list(frozen_hashes.keys()),
        "scientific_artifacts_recomputed_hashes": recomputed,
        "scientific_artifact_drift": scientific_drift,
        "all_scientific_artifacts_identical_to_freeze": not scientific_drift,

        "champion_artifact": CHAMPION_ARTIFACT,
        "champion_artifact_sha256": champion_now,
        "champion_artifact_sha256_expected": CHAMPION_EXPECTED,
        "champion_unchanged": champion_unchanged,

        "primary_sample_exclusions": PRIMARY_SAMPLE_EXCLUSIONS,
        "primary_sample_exclusion_taint_level": "T2_INFRASTRUCTURE_ONLY",

        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("branch", "--show-current"),
        "no_target_outcome_opened": True,
        "no_paid_sonnet_research_call_made_yet": True,
        "next_step": "one live T2 cap-validation canary (over-budget tool-result -> forced "
                     "submit path), then amended pre-spend report; STOP for authorization "
                     "before the 50-fixture tranche.",
    }
    amendment["amendment_passed"] = bool(
        not scientific_drift and champion_unchanged and constants_ok)
    amendment["amendment_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in amendment.items() if k != "amendment_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return amendment


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_SEARCH_CAP_AMENDMENT.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"amendment_passed={out['amendment_passed']}")
    print(f"all_scientific_artifacts_identical_to_freeze={out['all_scientific_artifacts_identical_to_freeze']}")
    print(f"champion_unchanged={out['champion_unchanged']}")
    print(f"runner_checks_match={out['runner_checks_match']}")
    if out["scientific_artifact_drift"]:
        print("DRIFT:", out["scientific_artifact_drift"])
    print("amendment_hash:", out["amendment_hash"][:16])
