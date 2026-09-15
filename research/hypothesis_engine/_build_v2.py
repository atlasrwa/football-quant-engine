"""Build + verify the V2 manifest. ZERO spend, no Bedrock import anywhere in the chain."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import (battery_v2 as V2, controls, context_packet as CP,
                                            leakage, normalize, validator, query_plan,
                                            evaluation)

OUT = "/home/ubuntu/research/hypothesis_engine/out"
battery = json.load(open(os.path.join(OUT, "hypothesis_golden_battery_v1.json")))
packets = json.load(open(os.path.join(OUT, "frozen_packets_v1.json")))
packets_by_id = {fid: p for fid, p in packets.items()}

# snapshot originals to prove non-mutation
import copy
originals = copy.deepcopy(packets_by_id)

manifest, materialized = V2.build_manifest_v2(battery, packets_by_id, expected_cache_hits=0)

checks = {}

# 1. all 64 call specs resolve
checks["total_calls_64"] = (manifest["total_planned_calls"] == 64
                            and len(manifest["call_specs"]) == 64)
by_control = {}
for s in manifest["call_specs"]:
    by_control[s["control"]] = by_control.get(s["control"], 0) + 1
checks["call_counts"] = by_control
checks["call_counts_correct"] = (by_control == {
    "reference": 12, "repeatability": 12, "identity_alias": 8, "formation_ablation": 6,
    "profile_perturbation": 6, "venue_flip": 6, "irrelevant_field": 6,
    "evidence_starvation": 4, "unsupported_data_trap": 4})

# 2. reference mappings correct (12 refs map to the 12 battery fixtures, hash matches)
order = [f["fixture_id"] for f in battery["fixtures"]]
ref_specs = [s for s in manifest["call_specs"] if s["control"] == "reference"]
checks["reference_maps_12_fixtures"] = (
    [s["source_fixture"] for s in ref_specs] == order)
checks["reference_hashes_match_frozen"] = all(
    s["resulting_packet_hash"] == packets_by_id[s["source_fixture"]]["packet_hash"]
    for s in ref_specs)

# 3. repeatability hashes exactly equal their reference
rep_specs = [s for s in manifest["call_specs"] if s["control"] == "repeatability"]
checks["repeatability_reuses_reference_hash"] = all(
    s["resulting_packet_hash"] == packets_by_id[s["source_fixture"]]["packet_hash"]
    and s["transformation_version"] is None
    for s in rep_specs)
checks["repeatability_is_12_over_6_fixtures_x2"] = (
    len(rep_specs) == 12 and len(set(s["source_fixture"] for s in rep_specs)) == 6)

# 4. 40 transformed packets exist and are deterministic (rebuild, compare hash)
transform_specs = [s for s in manifest["call_specs"]
                   if s["control"] not in ("reference", "repeatability")]
checks["n_transformed_specs"] = len(transform_specs)
det_ok = True
for s in transform_specs:
    fid = s["source_fixture"]
    ctrl = s["control"]
    ref = packets_by_id[fid]
    if ctrl == "identity_alias":
        tp = controls.identity_alias(ref)
    elif ctrl == "formation_ablation":
        tp = controls.formation_ablation(ref)
    elif ctrl == "profile_perturbation":
        raise_band = s["transformation_params"]["direction"] == "RAISE"
        tp, _ = controls.profile_perturbation(ref, raise_band=raise_band)
    elif ctrl == "venue_flip":
        tp = controls.venue_flip(ref)
    elif ctrl == "irrelevant_field":
        tp = controls.irrelevant_field(ref)
    elif ctrl == "evidence_starvation":
        tp = controls.evidence_starvation(ref)
    elif ctrl == "unsupported_data_trap":
        tp = controls.unsupported_data_trap(ref)
    # recompute twice -> identical, and equals the manifest's frozen hash
    if tp["packet_hash"] != s["resulting_packet_hash"]:
        det_ok = False
    if CP.packet_hash(tp) != tp["packet_hash"]:
        det_ok = False
checks["transformed_deterministic_and_selfconsistent"] = det_ok

# 5. all transformed hashes reproduce in the materialized map
checks["materialized_hashes_match_specs"] = all(
    materialized[s["packet_key"]]["packet_hash"] == s["resulting_packet_hash"]
    for s in manifest["call_specs"])

# 6. original packets never mutated
checks["originals_unmutated"] = (originals == packets_by_id)

# 7. evidence refs resolve: every non-starved transformed packet keeps valid neutral ids;
#    (schema/grounding is tested at scoring time, here we assert ids remain HOME_/AWAY_)
idok = True
for key, pkt in materialized.items():
    for e in pkt.get("evidence", []):
        if e["id"].split("_")[0] not in ("HOME", "AWAY"):
            idok = False
checks["evidence_ids_identity_neutral"] = idok

# 8. leakage clean on every packet + serialized request
checks["manifest_leak_status"] = manifest["request_leakage_audit"]["status"]
checks["manifest_leak_findings"] = manifest["request_leakage_audit"]["total_findings"]

# 9. normalization/scoring deterministic & frozen (versions pinned + module hashes present)
checks["normalization_version"] = manifest["normalization_version"]
checks["evaluation_version"] = manifest["evaluation_version"]
checks["controls_version"] = manifest["controls_version"]
checks["has_module_hashes"] = all(k in manifest for k in
    ("controls_module_hash", "scoring_module_hash", "normalization_module_hash"))
checks["thresholds_frozen"] = (manifest["pass_fail_thresholds"] == dict(evaluation.THRESHOLDS))

# 10. unique packets count
checks["n_unique_packets"] = manifest["n_unique_packets"]

# ---- profile_perturbation BEFORE->AFTER for all 6 cases
profile_table = []
for s in transform_specs:
    if s["control"] == "profile_perturbation":
        profile_table.append({
            "fixture": s["source_fixture"],
            "direction": s["transformation_params"]["direction"],
            "factor": s["transformation_params"]["factor"],
            "changes": s["transformation_params"]["changes"],
        })

all_pass = all(v is True for k, v in checks.items()
               if isinstance(v, bool))

print(json.dumps({
    "all_bool_checks_pass": all_pass,
    "checks": checks,
    "manifest_hash": manifest["manifest_hash"],
    "cost": manifest["token_and_cost_estimate"],
    "profile_perturbation_table": profile_table,
}, indent=2, sort_keys=True, default=str))

# write only if clean
if all_pass and manifest["request_leakage_audit"]["status"] == "CLEAN":
    mpath, ppath = V2.write_manifest_v2(manifest, materialized)
    print("WROTE", mpath)
    print("WROTE", ppath)
else:
    print("NOT WRITTEN -- a check failed")
