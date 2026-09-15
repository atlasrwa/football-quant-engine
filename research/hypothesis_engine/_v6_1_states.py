"""Emit the required V6.1 pre-spend states, each gated on its concrete evidence. ZERO SPEND.

Writes out/v6_1/V6_1_STATES.json. A state is asserted ONLY if the artifact that supports it
says so; this script reads frozen artifacts and re-checks, it does not re-decide anything. If
any required piece of evidence is missing or contradicts a state, that state is NOT emitted
and the script exits non-zero (PRESPEND_BLOCKED).

This script NEVER calls Bedrock. It does not authorize spend; the terminal state is
V6_1_SPEND_AUTHORIZATION_REQUIRED, which is a STOP.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

ROOT = "/home/ubuntu"
V6 = f"{ROOT}/research/hypothesis_oos/out/v6"
V6_EXEC = f"{V6}/execution"
V61 = f"{ROOT}/research/hypothesis_oos/out/v6_1"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

# The V6 artifacts that MUST remain byte-immutable (Task 1). Values verified this session.
V6_IMMUTABLE = {
    f"{ROOT}/src/research/hypothesis_oos/v6_verdict.py":
        "f195cf7f2db48d47d1bedc20cf6a364efc7b7efca46f5089045d3803b4d99854",
    f"{ROOT}/src/research/hypothesis_oos/v6_scorecard.py":
        "0b89e96ec042a762bbaf78b4e3cdb9e65054b9514688d6d0c260663f86a13bcf",
    f"{V6}/EVALUATOR_FREEZE.json":
        "d0c78442df6d63fba5a1fd83d0d5ad80d84691ae2da1c039e8b427032690d71c",
    f"{V6_EXEC}/V6_VERDICT.json":
        "0225963d1ca6e0ca2accaf6f1e9c84ff1a9077816dd99d4675922782ceac86d6",
    f"{V6_EXEC}/scores.json":
        "4ba5f37b98aec2ad2a04cf62f3b40587786a907dd6abe19c6939d2f26cf5ec3c",
}

REQUIRED_STATES = [
    "V6_1_V6_HISTORY_PRESERVED",
    "V6_1_EVALUATOR_DEFECT_REPRODUCED",
    "V6_1_COMPILER_RATE_FIXED",
    "V6_1_ALL_RATE_CONTRACTS_VALIDATED",
    "V6_1_POSTHOC_REPLAY_DIAGNOSTIC_ONLY",
    "V6_1_FRESH_FIXTURE_SELECTION_FROZEN",
    "V6_1_PIT_VALIDATED",
    "V6_1_EVALUATOR_FROZEN",
    "V6_1_EXECUTION_DESIGN_FROZEN",
    "V6_1_EXACT_COST_BOUND_VALIDATED",
    "V6_1_FULLY_PREREGISTERED",
    "V6_1_SPEND_AUTHORIZATION_REQUIRED",
]


def _sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _load(path):
    return json.load(open(path))


def gather_evidence() -> tuple[dict, list]:
    """Return (evidence, blocking_problems). Each state's evidence and its gate."""
    ev, blocked = {}, []

    # 1. V6 history preserved (immutable hashes + audit interpretation).
    v6_hash_ok = {p: (_sha(p) == want) for p, want in V6_IMMUTABLE.items()}
    audit = _load(f"{V6_EXEC}/V6_POSTRUN_AUDIT.json")
    v6_verdict = _load(f"{V6_EXEC}/V6_VERDICT.json")["verdict"]
    hist_ok = (all(v6_hash_ok.values())
               and audit["V6_EXECUTION_STATUS"] == "COMPLETE"
               and audit["V6_FROZEN_EVALUATOR_VERDICT"] == "FAIL"
               and audit["V6_SCIENTIFIC_VERDICT"] is None
               and v6_verdict["scientific_verdict"] == "FAIL"
               and audit["v6_untouched"] is True)
    ev["V6_1_V6_HISTORY_PRESERVED"] = {
        "all_v6_artifacts_immutable": all(v6_hash_ok.values()),
        "V6_EXECUTION_STATUS": audit["V6_EXECUTION_STATUS"],
        "V6_FROZEN_EVALUATOR_VERDICT": audit["V6_FROZEN_EVALUATOR_VERDICT"],
        "V6_SCIENTIFIC_VERDICT": audit["V6_SCIENTIFIC_VERDICT"],
        "V6_POSTRUN_AUDIT": audit["V6_POSTRUN_AUDIT"]}
    if not hist_ok:
        blocked.append("V6 history not preserved / an immutable artifact changed")

    # 2/3. defect reproduced + compiler rate fixed (from the corrected replay + a direct
    # check on the exact counterexample).
    from src.research.hypothesis_oos import v6_1_metrics as MC
    from src.research.hypothesis_oos import v6_1_verdict as V61V
    replay = _load(f"{V61}/V6_POSTHOC_CORRECTED_REPLAY.json")
    old = replay["old_defective_compiler_rate"]["base"]
    defect_reproduced = old["rate"] is not None and old["rate"] > 1.0
    try:
        MC.check_rate("compiler_valid_rate", old["numerator_all_compilable"],
                      old["denominator_nonabstaining"])
        contract_catches_defect = False
    except MC.MetricContractViolation:
        contract_catches_defect = True
    corrected_base = replay["corrected_evaluator"]["discipline"]["axes"][
        "compiler_valid_rate"]["base"]
    rate_fixed = (corrected_base is not None and corrected_base <= 1.0
                  and contract_catches_defect)
    ev["V6_1_EVALUATOR_DEFECT_REPRODUCED"] = {
        "old_base_rate": old["rate"], "old_numerator": old["numerator_all_compilable"],
        "old_denominator": old["denominator_nonabstaining"],
        "rate_exceeds_one": defect_reproduced,
        "contract_now_catches_it": contract_catches_defect}
    ev["V6_1_COMPILER_RATE_FIXED"] = {
        "corrected_base_rate": corrected_base,
        "corrected_research_rate": replay["corrected_evaluator"]["discipline"]["axes"][
            "compiler_valid_rate"]["research"],
        "repaired_numerator": "non-abstaining AND compiler-valid",
        "cannot_exceed_one": True}
    if not defect_reproduced:
        blocked.append("evaluator defect (compiler_valid_rate>1) not reproduced")
    if not rate_fixed:
        blocked.append("compiler_valid_rate repair not demonstrated")

    # 4. all rate contracts validated (run the V6.1 pre-spend test suite).
    test = subprocess.run(
        [sys.executable, "-m", "pytest",
         f"{ROOT}/tests/research/hypothesis_oos/test_v6_1_prespend.py", "-q"],
        capture_output=True, text=True, cwd=ROOT)
    tests_pass = test.returncode == 0
    ev["V6_1_ALL_RATE_CONTRACTS_VALIDATED"] = {
        "test_suite": "tests/research/hypothesis_oos/test_v6_1_prespend.py",
        "returncode": test.returncode, "passed": tests_pass,
        "summary": test.stdout.strip().splitlines()[-1] if test.stdout else "",
        "enforced_in_production_path": MC.version_stamp()["enforced_in_production_path"]}
    if not tests_pass:
        blocked.append("V6.1 metric-contract / path test suite did not pass")

    # 5. posthoc replay diagnostic-only labelled.
    replay_labeled = ("NON_CONFIRMATORY" in replay["status_tags"]
                      and "DIAGNOSTIC_ONLY" in replay["status_tags"]
                      and replay["is_v6_scientific_verdict"] is False
                      and replay["is_v6_1_confirmatory_evidence"] is False
                      and replay["must_not_tune_v6_1"] is True)
    ev["V6_1_POSTHOC_REPLAY_DIAGNOSTIC_ONLY"] = {
        "status_tags": replay["status_tags"],
        "is_v6_scientific_verdict": replay["is_v6_scientific_verdict"],
        "is_v6_1_confirmatory_evidence": replay["is_v6_1_confirmatory_evidence"],
        "second_order_material_defect_found":
            replay["second_order_audit"]["material_second_order_defect_found"]}
    if not replay_labeled:
        blocked.append("corrected replay not labelled NON_CONFIRMATORY/DIAGNOSTIC_ONLY")
    if replay["second_order_audit"]["material_second_order_defect_found"]:
        blocked.append("a second-order evaluator defect remains unfixed")

    # 6. fresh fixture selection frozen + outcome-independent.
    sel = _load(f"{V61}/fixture_selection.json")
    from src.research.hypothesis_oos import v6_1_fixtures as FX
    no_overlap = not (set(sel["selected_fixtures"]) & set(FX.HELD_OUT))
    indep = all(v is False for k, v in sel["independence_assertion"].items()
                if k != "ordering_is_hash_of_identifier_only")
    fresh_ok = (sel["n_selected"] == 10 and not sel["shortfalls"] and no_overlap and indep)
    ev["V6_1_FRESH_FIXTURE_SELECTION_FROZEN"] = {
        "n_selected": sel["n_selected"], "shortfalls": sel["shortfalls"],
        "no_overlap_with_v6_or_v5a": no_overlap,
        "outcome_independent": indep,
        "ordering": "sha256(fixture_id)",
        "selected_fixtures": sel["selected_fixtures"]}
    if not fresh_ok:
        blocked.append("fresh fixture selection not frozen / not outcome-independent")

    # 7. PIT validated on the fresh packets.
    pit = _load(f"{V61}/pit_audit.json")
    ai = _load(f"{V61}/arm_isolation_audit.json")
    pit_ok = (pit["n_problems"] == 0 and ai["n_identity_leaks"] == 0
              and not ai["treatment_labels_found_in_packets"]
              and ai["research_superset_of_base_all"])
    ev["V6_1_PIT_VALIDATED"] = {
        "pit_problems": pit["n_problems"], "arm_identity_leaks": ai["n_identity_leaks"],
        "treatment_labels": ai["treatment_labels_found_in_packets"],
        "research_superset_of_base": ai["research_superset_of_base_all"]}
    if not pit_ok:
        blocked.append("PIT / arm-isolation not validated on the fresh packets")

    # 8. evaluator frozen before spend.
    ef = _load(f"{V61}/EVALUATOR_FREEZE.json")
    ef_ok = (ef["frozen_before_first_paid_call"] and ef["spend_usd_at_freeze"] == 0.0
             and ef["thresholds_unchanged_from_v6"])
    ev["V6_1_EVALUATOR_FROZEN"] = {
        "frozen_before_first_paid_call": ef["frozen_before_first_paid_call"],
        "spend_usd_at_freeze": ef["spend_usd_at_freeze"],
        "thresholds_unchanged_from_v6": ef["thresholds_unchanged_from_v6"],
        "n_evaluator_modules": len(ef["evaluator_modules"])}
    if not ef_ok:
        blocked.append("evaluator not frozen before spend / thresholds changed")

    # 9. execution design frozen (schedule).
    sch = _load(f"{V61}/call_schedule.json")
    design_ok = sch["frozen"] and sch["n_calls"] == 36 and not sch["freeze_problems"]
    ev["V6_1_EXECUTION_DESIGN_FROZEN"] = {
        "n_calls": sch["n_calls"], "frozen": sch["frozen"],
        "freeze_problems": sch["freeze_problems"],
        "no_fixture_dominates_prefix": sch["order_properties"][
            "no_fixture_dominates_prefix"]}
    if not design_ok:
        blocked.append("execution design (schedule) not freezable")

    # 10. exact cost bound validated (provider-native CountTokens).
    exact = _load(f"{V61}/EXACT_INPUT_TOKEN_MANIFEST.json")
    tm = _load(f"{V61}/INPUT_TOKEN_MANIFEST.json")
    exact_by_sha = {e["request_sha256"]: e for e in exact["entries"]}
    all_bound = all(
        e["exact_input_tokens"] > 0
        and e["exact_input_tokens"] <= e["conservative_byte_upper_bound"]
        for e in exact["entries"])
    tm_uses_exact = all(e["input_tokens_method"] == "bedrock_count_tokens"
                        for e in tm["entries"])
    cost_ok = (exact["n_requests"] == 36 and all_bound
               and exact["counting_method"] == "aws_bedrock_count_tokens"
               and exact["mapping_verified"] is True and tm_uses_exact)
    ev["V6_1_EXACT_COST_BOUND_VALIDATED"] = {
        "n_exact_counts": exact["n_requests"],
        "counting_method": exact["counting_method"],
        "count_tokens_model_id": exact["count_tokens_model_id"],
        "total_exact_input_tokens": exact["total_exact_input_tokens"],
        "hard_max_cost_usd": exact["hard_max_cost_usd"],
        "byte_bound_total": exact["previous_utf8_total_input_tokens"],
        "all_exact_le_byte_bound": all_bound,
        "manifest_uses_exact": tm_uses_exact,
        "v6_ceiling_not_assumed": True}
    if not cost_ok:
        blocked.append("exact provider-native token bound missing/incomplete")

    # 11. fully preregistered.
    prereg = _load(f"{V61}/PREREGISTRATION.json")
    champ_ok = _sha(CHAMPION) == CHAMPION_FROZEN_SHA
    prereg_ok = (prereg["spend_usd_so_far"] == 0.0
                 and "REQUIRED" in prereg["spend_authorization"]
                 and prereg["champion_protection"]["current_sha256"]
                 == CHAMPION_FROZEN_SHA
                 and len(prereg["metric_registry"]) >= 10
                 and champ_ok)
    ev["V6_1_FULLY_PREREGISTERED"] = {
        "spend_usd_so_far": prereg["spend_usd_so_far"],
        "n_registered_metrics": len(prereg["metric_registry"]),
        "champion_unchanged": champ_ok,
        "n_call_sequence": len(prereg["call_sequence"]),
        "preregistration_sha256": _sha(f"{V61}/PREREGISTRATION.json")}
    if not prereg_ok:
        blocked.append("preregistration incomplete / champion changed")

    # 12. terminal STOP.
    ev["V6_1_SPEND_AUTHORIZATION_REQUIRED"] = {
        "spend_authorization": prereg["spend_authorization"],
        "note": "STOP. Do not call Converse/InvokeModel. Human authorization required."}

    return ev, blocked


def main() -> int:
    ev, blocked = gather_evidence()
    out = {"states_version": "v6_1_states_v1", "spend_usd": 0.0,
           "blocking_problems": blocked, "any_block": bool(blocked)}
    if blocked:
        out["states_emitted"] = []
        out["executive_verdict"] = "V6_1_PRESPEND_BLOCKED"
        out["result"] = f"BLOCKED: {blocked}"
        with open(f"{V61}/V6_1_STATES.json", "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True, default=str)
        print("=== V6.1 PRE-SPEND STATES ===")
        print("EXECUTIVE VERDICT: V6_1_PRESPEND_BLOCKED")
        for b in blocked:
            print("  BLOCK:", b)
        return 1

    out["states_emitted"] = REQUIRED_STATES
    out["state_evidence"] = ev
    out["executive_verdict"] = "V6_1_PRESPEND_READY"
    out["result"] = ("ALL V6.1 PRE-SPEND STATES VALIDATED. "
                     "V6_1_SPEND_AUTHORIZATION_REQUIRED. STOP.")
    with open(f"{V61}/V6_1_STATES.json", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)

    print("=== V6.1 PRE-SPEND STATES (ZERO SPEND) ===")
    for s in REQUIRED_STATES:
        print(f"  [VALIDATED] {s}")
    print("\nEXECUTIVE VERDICT: V6_1_PRESPEND_READY")
    print(out["result"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
