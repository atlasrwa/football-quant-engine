"""Build + verify the SONNET46_HYPOTHESIS_V3 preregistration. ZERO SPEND.

No Bedrock import anywhere in the chain. Every check below runs offline against frozen
JSON and the frozen V3 modules, and the script refuses to write the manifest if any check
fails.

It also runs a DRY VERDICT: the frozen V3 thresholds are applied to the already-recorded
V2 replay measurements, proving the verdict function is mechanically computable and showing
exactly where V2's behaviour would have landed against V3's bar. That is a preregistration
artifact, not a V2 rescoring -- V2's verdict is FAIL and is untouched.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")

from research.hypothesis_engine import (availability, battery_v3 as V3, capability,
                                        condition_contract, context_packet as CP,
                                        controls, controls_v3, leakage, multicondition,
                                        normalize, prompt_v2, query_plan, schema_v2,
                                        validator_v2, verdict_v3)

OUT = f"{ROOT}/research/hypothesis_engine/out"
REPLAY = f"{OUT}/V2_COUNTERFACTUAL_REPLAY_v3contract/counterfactual_replay_report.json"

battery = json.load(open(f"{OUT}/hypothesis_golden_battery_v1.json"))
packets_by_id = json.load(open(f"{OUT}/frozen_packets_v1.json"))
originals = copy.deepcopy(packets_by_id)

checks: dict = {}

manifest, materialized = V3.build_manifest(battery, packets_by_id, expected_cache_hits=0)

# ---------------------------------------------------------------------------------
# 1. Call layout is exactly as preregistered
# ---------------------------------------------------------------------------------
by_control: dict = {}
for s in manifest["call_specs"]:
    by_control[s["control"]] = by_control.get(s["control"], 0) + 1
checks["call_counts"] = by_control
checks["call_counts_correct"] = by_control == {
    "reference": 12, "repeatability": 12, "identity_alias": 6, "irrelevant_field": 6,
    "profile_axis_perturbation": 6, "availability_ablation": 6,
    "evidence_starvation": 4, "unsupported_data_trap": 4}
checks["total_calls_56"] = (manifest["total_planned_calls"] == 56
                            and len(manifest["call_specs"]) == 56)
checks["seq_is_dense_and_ordered"] = [s["seq"] for s in manifest["call_specs"]] == list(
    range(56))

# ---------------------------------------------------------------------------------
# 2. Reference + repeatability bind to the frozen packets, unchanged
# ---------------------------------------------------------------------------------
order = [f["fixture_id"] for f in battery["fixtures"]]
ref_specs = [s for s in manifest["call_specs"] if s["control"] == "reference"]
checks["reference_maps_12_fixtures_in_frozen_order"] = (
    [s["source_fixture"] for s in ref_specs] == order)
checks["reference_hashes_match_frozen"] = all(
    s["resulting_packet_hash"] == packets_by_id[s["source_fixture"]]["packet_hash"]
    for s in ref_specs)

rep_specs = [s for s in manifest["call_specs"] if s["control"] == "repeatability"]
checks["repeatability_reuses_reference_hash"] = all(
    s["resulting_packet_hash"] == packets_by_id[s["source_fixture"]]["packet_hash"]
    and s["transformation_version"] is None for s in rep_specs)
checks["repeatability_is_6_fixtures_x2"] = (
    len(rep_specs) == 12 and len(set(s["source_fixture"] for s in rep_specs)) == 6
    and all(sum(1 for r in rep_specs if r["source_fixture"] == f) == 2
            for f in set(s["source_fixture"] for s in rep_specs)))
checks["repeatability_yields_18_same_input_pairs"] = (
    manifest["repeatability_structure"]["same_input_pairs"] == 18)

# ---------------------------------------------------------------------------------
# 3. Every transformed packet is deterministic, self-consistent and non-mutating
# ---------------------------------------------------------------------------------
det_ok = True
for s in manifest["call_specs"]:
    if s["control_type"] != "transform":
        continue
    ref = packets_by_id[s["source_fixture"]]
    ctrl = s["control"]
    if ctrl == "identity_alias":
        tp = controls.identity_alias(ref)
    elif ctrl == "irrelevant_field":
        tp = controls.irrelevant_field(ref)
    elif ctrl == "profile_axis_perturbation":
        tp, _ = controls_v3.profile_axis_perturbation(
            ref, raise_band=s["transformation_params"]["direction"] == "RAISE")
    elif ctrl == "availability_ablation":
        tp = controls_v3.availability_ablation(ref)
    elif ctrl == "evidence_starvation":
        tp = controls.evidence_starvation(ref)
    elif ctrl == "unsupported_data_trap":
        tp = controls.unsupported_data_trap(ref)
    else:
        det_ok = False
        continue
    if tp["packet_hash"] != s["resulting_packet_hash"]:
        det_ok = False
    if CP.packet_hash(tp) != tp["packet_hash"]:
        det_ok = False
checks["transformed_deterministic_and_selfconsistent"] = det_ok
checks["source_packets_not_mutated"] = packets_by_id == originals
checks["materialized_hashes_match_specs"] = all(
    materialized[s["packet_key"]]["packet_hash"] == s["resulting_packet_hash"]
    for s in manifest["call_specs"])

# ---------------------------------------------------------------------------------
# 4. The profile-axis perturbation actually moved the intended surface
# ---------------------------------------------------------------------------------
prov = manifest["transform_provenance"]
checks["profile_axis_changed_two_metrics_per_fixture"] = (
    len(prov) == 6 and all(len(v) == 2 for v in prov.values()))
checks["profile_axis_moved_only_frozen_metrics"] = all(
    c["metric"] in controls_v3.PROFILE_AXIS_PERTURBATION_METRICS
    for v in prov.values() for c in v)
checks["profile_axis_raise_lower_split_is_3_3"] = (
    sum(1 for s in manifest["call_specs"]
        if s["control"] == "profile_axis_perturbation"
        and s["transformation_params"]["direction"] == "RAISE") == 3)
checks["profile_axis_surface_is_disjoint_from_v2"] = not (
    set(controls_v3.PROFILE_AXIS_PERTURBATION_METRICS)
    & set(controls.PROFILE_PERTURBATION_AXES))

# ---------------------------------------------------------------------------------
# 5. Availability ablation withdraws the capability and leaves evidence intact
# ---------------------------------------------------------------------------------
abl_ok = True
for s in manifest["call_specs"]:
    if s["control"] != "availability_ablation":
        continue
    ref = packets_by_id[s["source_fixture"]]
    abl = materialized[s["packet_key"]]
    if abl["evidence"] != ref["evidence"]:
        abl_ok = False
    ont = availability.build_ontology(abl)
    if ont.dimensions["opponent_profile"].status != availability.WITHHELD:
        abl_ok = False
    if "opponent_profile" in availability.fixture_condition_space(ont)["dimensions"]:
        abl_ok = False
checks["ablation_withdraws_capability_and_keeps_evidence"] = abl_ok

# ---------------------------------------------------------------------------------
# 6. The exposed prompt never names a withheld dimension or an unresolvable axis
# ---------------------------------------------------------------------------------
exposure_ok = True
axis_ok = True
for key, packet in sorted(materialized.items()):
    ont = availability.build_ontology(packet)
    msg = prompt_v2.build_user_message(packet, ont)
    for dim in ont.withheld_dimensions():
        if dim != "referee" and dim in msg:
            exposure_ok = False
    # Check the RESEARCH SPACE header -- the part that tells the model what it MAY
    # select -- not the whole message. A naive substring test over the evidence dump
    # false-positives, because the unresolvable axis `shots_for` is a substring of the
    # legitimate evidence metric name `total_shots_for`.
    header = msg.split("=== BEGIN UNTRUSTED EVIDENCE DATA ===")[0]
    exposed_axes = set()
    for entry in availability.fixture_condition_space(ont)["dimensions"].values():
        exposed_axes.update(entry.get("axes") or [])
    for axis in condition_contract.unresolvable_axes():
        if axis in exposed_axes:
            axis_ok = False
        # the token must also not appear as a standalone word in the selection surface
        if f"'{axis}'" in header or f'"{axis}"' in header:
            axis_ok = False
checks["prompt_never_names_a_withheld_dimension"] = exposure_ok
checks["prompt_never_exposes_an_unresolvable_axis"] = axis_ok
checks["unresolvable_axes_are_exactly_two"] = (
    condition_contract.unresolvable_axes() == ("shots_for", "shots_against"))

# ---------------------------------------------------------------------------------
# 7. Leakage audit is clean on every packet AND every serialized request
# ---------------------------------------------------------------------------------
checks["leakage_audit_status"] = manifest["request_leakage_audit"]["status"]
checks["leakage_findings_zero"] = (
    manifest["request_leakage_audit"]["total_findings"] == 0)

# ---------------------------------------------------------------------------------
# 8. Contract soundness end to end on the exact packets that will be sent
# ---------------------------------------------------------------------------------
CONTRACT_FAILURES = {"UNSUPPORTED_DIMENSION", "QUERY_INVALID"}
sweep_ok = True
for key, packet in sorted(materialized.items()):
    cm = packet["capability_manifest"]
    man = capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        coverage=dict(cm.get("coverage") or {}))
    ont = availability.build_ontology(packet, man)
    metric = (cm["available_metrics"] or ["corners"])[0]
    for dim in ont.selectable_dimensions():
        d = ont.dimensions[dim]
        axes = d.available_axes or (None,)
        for value in condition_contract.dimension_values(dim):
            for axis in axes:
                cond = {"dimension": dim, "value": value}
                if axis:
                    cond["axis"] = axis
                h = {"hypothesis_id": "H1", "research_family": "VENUE_EFFECT",
                     "subject": "HOME_TEAM", "target_metrics": [metric], "side": "FOR",
                     "window": "ALL_PRIOR", "conditions": [cond],
                     "comparison": "SUBJECT_OVERALL_BASELINE"}
                for r in query_plan.compile_hypothesis(
                        h, fixture_id=cm["fixture_id"],
                        cutoff_unix=packet.get("information_cutoff_unix", 0),
                        manifest=man):
                    if r.failure in CONTRACT_FAILURES:
                        sweep_ok = False
checks["every_exposed_condition_reaches_the_compiler"] = sweep_ok

# ---------------------------------------------------------------------------------
# 9. Fixture capability matrix -- the eligibility denominators
# ---------------------------------------------------------------------------------
matrix = V3.fixture_capability_matrix(battery, packets_by_id)
checks["depth_denominators"] = matrix["depth_denominators"]
checks["formation_contrastive_fixtures"] = matrix[
    "eligible_fixtures_by_dimension"].get("own_formation_family", [])
checks["score_state_eligible_nowhere"] = (
    "half_score_state" not in matrix["eligible_fixtures_by_dimension"])

# ---------------------------------------------------------------------------------
# 10. The verdict function is mechanically computable, and fails closed
# ---------------------------------------------------------------------------------
empty = verdict_v3.compute({})
checks["verdict_fails_closed_on_no_measurements"] = empty.verdict == verdict_v3.FAIL
checks["verdict_stop_rule_short_circuits"] = (
    verdict_v3.compute({}, stop_triggered=True).verdict
    == "INFRASTRUCTURE_OR_PROMPT_FAILURE")

# DRY VERDICT on the frozen V2 replay measurements. Preregistration artifact only:
# it shows where V2's ALREADY-RECORDED behaviour lands against V3's bar, and proves the
# thresholds are computable. It does NOT rescore V2, whose verdict is FAIL and is frozen.
replay = json.load(open(REPLAY))
u = replay["utilization"]
v2_measurements = {
    "P1_meaningful_multi_condition_rate": {"value": 0.0, "n": 132},
    "P2_beyond_venue_condition_rate": {"value": u["depth_beyond_venue"]["rate"],
                                       "n": u["n_counterfactual_intents_over_12_reference_responses"]},
    "P3_opponent_profile_fixture_utilization": {
        "value": u["availability_gated_fixture_level"]["opponent_profile"]["utilization"],
        "n": u["availability_gated_fixture_level"]["opponent_profile"][
            "n_fixtures_where_expectable"]},
    "P4_comparison_entropy": {"value": u["comparison_shannon_entropy_bits"], "n": 146},
}
dry = verdict_v3.compute(v2_measurements)
checks["dry_verdict_on_v2_replay"] = {
    "depth_criteria_met": dry.depth_met,
    "depth_outcome": dry.depth_outcome,
    "per_criterion": {r["key"]: {"value": r["value"], "threshold": r["threshold"],
                                 "met": r["met"]} for r in dry.depth},
    "note": ("diagnostic only: V2's frozen verdict is FAIL and is not recomputed. Every "
             "depth criterion is unmet on V2's recorded behaviour, which is what makes "
             "the V3 bar a real bar."),
}
checks["v2_replay_meets_zero_depth_criteria"] = dry.depth_met == 0

# ---------------------------------------------------------------------------------
# 11. Thresholds are fully specified
# ---------------------------------------------------------------------------------
spec_ok = all(
    c.statement and c.numerator and c.denominator and c.rationale and c.minimum_n > 0
    for c in verdict_v3.ALL_CRITERIA)
checks["every_threshold_fully_specified"] = spec_ok
checks["n_criteria"] = {"discipline": len(verdict_v3.DISCIPLINE),
                        "restraint": len(verdict_v3.RESTRAINT),
                        "depth": len(verdict_v3.DEPTH)}
checks["one_multicondition_hypothesis_is_not_sufficient_for_pass"] = (
    verdict_v3.compute({
        "P1_meaningful_multi_condition_rate": {"value": 1 / 144, "n": 144},
    }).verdict == verdict_v3.FAIL)

# ---------------------------------------------------------------------------------
# 12. Zero-spend proof
# ---------------------------------------------------------------------------------
import subprocess
grep = subprocess.run(
    ["grep", "-rn", "boto3\\|bedrock_client\\|invoke_model\\|converse",
     f"{ROOT}/src/research/hypothesis_engine/battery_v3.py",
     f"{ROOT}/src/research/hypothesis_engine/controls_v3.py",
     f"{ROOT}/src/research/hypothesis_engine/verdict_v3.py",
     f"{ROOT}/src/research/hypothesis_engine/multicondition.py",
     f"{ROOT}/src/research/hypothesis_engine/prompt_v2.py"],
    capture_output=True, text=True)
checks["no_bedrock_import_in_v3_modules"] = grep.returncode != 0

ALL_OK = all(v is True for k, v in checks.items()
             if isinstance(v, bool))

print(json.dumps(checks, indent=1, sort_keys=True, default=str))
print()
print("ALL_CHECKS_PASS:", ALL_OK)

if ALL_OK:
    mpath, ppath = V3.write_manifest(manifest, materialized, out_dir=OUT)
    with open(f"{OUT}/FIXTURE_CAPABILITY_MATRIX_v3.json", "w") as fh:
        json.dump(matrix, fh, indent=1, sort_keys=True, default=str)
    with open(f"{OUT}/PRESPEND_VERIFICATION_v3.json", "w") as fh:
        json.dump({"checks": checks, "all_checks_pass": ALL_OK,
                   "manifest_hash": manifest["manifest_hash"]},
                  fh, indent=1, sort_keys=True, default=str)
    print("wrote", mpath)
    print("wrote", ppath)
    print("manifest_hash:", manifest["manifest_hash"])
else:
    print("REFUSING TO WRITE MANIFEST -- a verification check failed")
    raise SystemExit(1)
