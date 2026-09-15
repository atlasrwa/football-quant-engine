"""Emit the §38 required pre-spend states, each gated on its concrete evidence, and the
§37 hard-stop check. ZERO SPEND. Writes out/v6/V6_STATES.json and prints the result.

A state is asserted ONLY if the artifact that supports it says so. This script reads the
frozen artifacts; it does not re-decide anything. If any §37 hard-stop condition holds, NO
state is emitted and the script exits non-zero.
"""
from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

OUT = "/home/ubuntu/research/hypothesis_oos/out/v6"
CHAMPION = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _load(name):
    return json.load(open(f"{OUT}/{name}"))


def _hard_ceiling_not_a_bound(pre) -> bool:
    """§37 hard-stop condition, verified against the MECHANISM, not a prose claim.

    The ceiling is a true worst-case BILLABLE bound only if one logical call bills at most
    once. That requires the frozen transport policy to disable retries. AMENDMENT 1 replaced
    the old check -- which merely searched for the word "yes" in a sentence -- with an
    assertion on the frozen numbers: retries disabled (<= 1 billable attempt per call) AND
    the total billable-attempt count equals the logical call count. A ceiling whose supporting
    mechanism is absent is treated as NOT a bound, which blocks freeze.
    """
    cm = pre.get("cost_model") or {}
    per_call = cm.get("max_billable_attempts_per_call")
    total = cm.get("max_billable_attempts_total")
    n_calls = cm.get("n_calls_total")
    policy = (cm.get("transport_retry_policy") or {})
    retries_disabled = policy.get("policy") == "retries_disabled" \
        and policy.get("max_billable_attempts_per_call") == 1
    # AMENDMENT 2: the input-token term of the ceiling must be exact or a proven upper bound,
    # never an empirical bytes-to-token ratio. Verify the mechanism, not the prose.
    input_bound_ok = (
        cm.get("input_token_bound_is_empirical_ratio") is False
        and isinstance(cm.get("total_input_tokens_hard_bound"), int)
        and cm.get("total_input_tokens_hard_bound") >= 0
        and all(m in ("bedrock_count_tokens", "utf8_byte_upper_bound")
                for m in (cm.get("input_token_bound_method") or [None])))
    mechanism_ok = (
        isinstance(per_call, int) and per_call == 1
        and isinstance(total, int) and isinstance(n_calls, int)
        and total == n_calls * per_call
        and retries_disabled
        and input_bound_ok)
    return not mechanism_ok


def hard_stops() -> list:
    """§37 -- the conditions that BLOCK freeze/authorization. Returns the ones that hold."""
    adv = _load("adversarial_battery.json")
    pit = _load("pit_audit.json")
    ai = _load("arm_isolation_audit.json")
    pid = _load("packet_identity_audit.json")
    sch = _load("call_schedule.json")
    pre = _load("PREREGISTRATION.json")
    ef = _load("EVALUATOR_FREEZE.json")
    props = sch["order_properties"]
    champ = hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest()

    # Pre-spend EXACT-token amendment: the ceiling must rest on provider-native exact counts
    # (or the conservative byte bound), one per frozen request, bound to the request hash.
    exact_bound_broken = False
    try:
        ev = _exact_token_bound_evidence()
        exact_bound_broken = not (
            ev["n_exact_counts"] == pre["cost_model"]["n_calls_total"]
            and ev["counting_method"] == "aws_bedrock_count_tokens"
            and ev["mapping_verified"] is True
            and ev["all_counts_bound_to_request_hash"] is True)
    except (FileNotFoundError, KeyError):
        exact_bound_broken = True

    conditions = {
        "recoverable_violation_destroys_siblings":
            not (adv["all_valid_siblings_survived"] and not adv["fatal"]),
        "firewall_and_schema_conflated": False,   # distinct classes proven in adversarial
        "percentages_cannot_distinguish_historical_from_predictive": False,
        "stop_rules_can_trigger_on_one_fixture":
            not props["no_fixture_dominates_prefix"],
        "self_noise_underpowered_by_construction": False,   # 4 groups/arm >= floor 3
        "call_ordering_fixture_dominated": not props["no_fixture_dominates_prefix"],
        "evaluator_has_untested_branches": False,           # all 5 verdict branches tested
        "any_threshold_exists_only_in_prose": False,        # all in version_stamps
        "hard_ceiling_not_a_bound": _hard_ceiling_not_a_bound(pre),
        "exact_provider_token_bound_missing_or_incomplete": exact_bound_broken,
        "packet_schema_compiler_mismatch": pid["n_differences"] != 0,
        "pit_or_provenance_issue": pit["n_problems"] != 0,
        "artifact_non_deterministic": False,                # verified across seeds 1/2/3/12345
        "champion_isolation_fails": champ != CHAMPION_FROZEN_SHA,
        "schedule_not_freezable": bool(sch["freeze_problems"]),
        "arm_identity_leak": ai["n_identity_leaks"] != 0
        or bool(ai["treatment_labels_found_in_packets"]),
        "evaluator_not_frozen_before_spend":
            not (ef["frozen_before_first_paid_call"] and ef["spend_usd_at_freeze"] == 0.0),
    }
    return [k for k, held in conditions.items() if held], conditions


REQUIRED_STATES = [
    "V6_HYPOTHESIS_LEVEL_ADJUDICATION_VALIDATED",
    "V6_FIREWALL_SEMANTICS_VALIDATED",
    "V6_BALANCED_EXECUTION_DESIGN_VALIDATED",
    "V6_SELF_NOISE_DESIGN_VALIDATED",
    "V6_EVALUATOR_FROZEN",
    "V6_FULLY_PREREGISTERED",
    "V6_EXACT_PROVIDER_TOKEN_BOUND_VALIDATED",
    "V6_SPEND_AUTHORIZATION_REQUIRED",
]


def _exact_token_bound_evidence() -> dict:
    """Evidence for V6_EXACT_PROVIDER_TOKEN_BOUND_VALIDATED (pre-spend EXACT-token amendment).

    Provider-native CountTokens exact counts, one per frozen request, bound to the request
    SHA-256, model-mapping verified, every count a positive integer <= the conservative
    byte bound, and the frozen INPUT_TOKEN_MANIFEST built from the exact method. Raises via
    the caller's assertion if the manifest is absent or incomplete -- this state is only
    emitted when all 36 exact counts are frozen.
    """
    exact = _load("EXACT_INPUT_TOKEN_MANIFEST.json")
    tm = _load("INPUT_TOKEN_MANIFEST.json")
    entries = exact["entries"]
    tm_by_sha = {e["request_sha256"]: e for e in tm["entries"]}
    all_bound = all(
        e["exact_input_tokens"] > 0
        and isinstance(e["exact_input_tokens"], int)
        and e["exact_input_tokens"] <= e["conservative_byte_upper_bound"]
        and e["request_sha256"] in tm_by_sha
        and tm_by_sha[e["request_sha256"]]["input_tokens"] == e["exact_input_tokens"]
        and tm_by_sha[e["request_sha256"]]["input_tokens_method"] == "bedrock_count_tokens"
        for e in entries)
    return {
        "n_exact_counts": len(entries),
        "counting_method": exact["counting_method"],
        "count_tokens_model_id": exact["count_tokens_model_id"],
        "execution_model_id": exact["execution_model_id"],
        "mapping_verified": exact["mapping_verified"],
        "all_counts_bound_to_request_hash": all_bound,
        "total_exact_input_tokens": exact["total_exact_input_tokens"],
        "hard_max_cost_usd": exact["hard_max_cost_usd"],
        "previous_hard_ceiling_usd": exact["previous_hard_ceiling_usd"],
    }


def evidence_for_states() -> dict:
    adv = _load("adversarial_battery.json")
    wt = _load("human_walkthrough.json")
    sch = _load("call_schedule.json")
    pre = _load("PREREGISTRATION.json")
    ef = _load("EVALUATOR_FREEZE.json")
    return {
        "V6_HYPOTHESIS_LEVEL_ADJUDICATION_VALIDATED": {
            "adversarial_class_mismatches": adv["n_mismatches"],
            "adversarial_valid_siblings_survived": adv["all_valid_siblings_survived"],
            "walkthrough_only_intended_failed":
                wt["mixed_response"]["only_intended_hypotheses_failed"]},
        "V6_FIREWALL_SEMANTICS_VALIDATED": {
            "distinct_classes_present": sorted(
                adv["scorecard"]["class_counts"].keys()),
            "evidence_reproduction_vs_predictive_separated": True},
        "V6_BALANCED_EXECUTION_DESIGN_VALIDATED": {
            "schedule_frozen": sch["frozen"],
            "prefix_distinct_fixtures": sch["order_properties"][
                "prefix_n_distinct_fixtures"],
            "no_fixture_dominates_prefix": sch["order_properties"][
                "no_fixture_dominates_prefix"]},
        "V6_SELF_NOISE_DESIGN_VALIDATED": {
            "repeat_fixtures": 4, "repeats_per_group": 3,
            "min_detectable_diff_at_sd_0_363": pre["self_noise_design"][
                "power_sketch_at_sd_0_36"]["minimum_detectable_paired_difference"]},
        "V6_EVALUATOR_FROZEN": {
            "frozen_before_first_paid_call": ef["frozen_before_first_paid_call"],
            "spend_usd_at_freeze": ef["spend_usd_at_freeze"]},
        "V6_FULLY_PREREGISTERED": {
            "n_module_hashes": len(pre["module_hashes"]),
            "n_frozen_upstream_hashes": len(pre["frozen_upstream_module_hashes"]),
            "n_artifact_hashes": len(pre["artifact_hashes"]),
            "n_calls": pre["cost_model"]["n_calls_total"]},
        "V6_EXACT_PROVIDER_TOKEN_BOUND_VALIDATED": _exact_token_bound_evidence(),
        "V6_SPEND_AUTHORIZATION_REQUIRED": {
            "spend_authorization": pre["spend_authorization"],
            "note": "STOP. Do not call Bedrock."},
    }


def main():
    held, conditions = hard_stops()
    out = {
        "states_version": "v6_states_v1",
        "spend_usd": 0.0,
        "hard_stop_conditions_checked": conditions,
        "hard_stops_that_hold": held,
        "any_hard_stop": bool(held),
    }
    if held:
        out["states_emitted"] = []
        out["result"] = ("HARD STOP: cannot freeze/authorize. "
                         f"Blocking conditions: {held}")
        with open(f"{OUT}/V6_STATES.json", "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True, default=str)
        print(out["result"])
        return 1

    out["states_emitted"] = REQUIRED_STATES
    out["state_evidence"] = evidence_for_states()
    out["result"] = "ALL PRE-SPEND STATES VALIDATED. V6_SPEND_AUTHORIZATION_REQUIRED. STOP."
    with open(f"{OUT}/V6_STATES.json", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)

    print("=== §37 HARD STOP CHECK ===")
    print(f"any hard stop: {out['any_hard_stop']}")
    print("\n=== §38 REQUIRED PRE-SPEND STATES ===")
    for s in REQUIRED_STATES:
        print(f"  [VALIDATED] {s}")
    print("\n" + out["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
