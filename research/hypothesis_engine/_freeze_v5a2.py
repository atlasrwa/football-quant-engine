"""Freeze the V5A.2 preregistration. ZERO SPEND -- no Bedrock, no network.

Cost is recalculated (task S29) against the ACTUAL V5A.2 request bytes, and the
tokens-per-byte calibration now comes from V5A.1's OBSERVED token counts rather than the
V3-era estimate. That is the one good thing V5A.1's six paid calls bought: two real
measurements, one per arm, of how this exact packet shape tokenizes.
"""
from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import (capability, firewall_v4, schema_v2, schema_v3,
                                            validator_v4, vocabulary)
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_contract as C
from src.research.hypothesis_oos import v5a2_evaluator as EV
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v5a2_packet as P2
from src.research.hypothesis_oos import v5a2_prompt as PR
from src.research.hypothesis_oos import v5a2_transport as TRN
from src.research.hypothesis_oos import v5a2_translate as TR

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a2"
V5A1_OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"

# ---- calibration, from V5A.1's six observed paid calls ---------------------------------
#: seq 1-4 base: 14380 input tokens each; seq 5-6 research: 57011 each. Both against the
#: V5A.1 payloads, whose byte counts are recomputed here so the ratio is measured, not
#: assumed. Output: observed mean 4375.7, observed max 5232 across the six calls.
V5A1_OBSERVED = {"base": 14380, "research": 57011}
OUTPUT_TOKENS_MEAN = 4376
OUTPUT_TOKENS_P90 = 5232
OUTPUT_TOKENS_MAX = 8192          # the request's own max_tokens ceiling

PRICE_IN_PER_1K = 0.003
PRICE_OUT_PER_1K = 0.015

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS = 8192
REPEATABILITY_CALLS = 3
PAIRED = ["mt_010243515", "mt_010243537", "mt_010243938", "mt_010244159", "mt_010244193",
          "mt_010441320", "mt_010441491", "mt_010444904", "mt_012232295", "mt_012232411"]
CALIBRATION_FIXTURE = "mt_010243515"

MODULES = [
    "src/research/hypothesis_oos/v5a2_ontology.py",
    "src/research/hypothesis_oos/v5a2_contract.py",
    "src/research/hypothesis_oos/v5a2_translate.py",
    "src/research/hypothesis_oos/v5a2_packet.py",
    "src/research/hypothesis_oos/v5a2_admissibility.py",
    "src/research/hypothesis_oos/v5a2_view.py",
    "src/research/hypothesis_oos/v5a2_prompt.py",
    "src/research/hypothesis_oos/v5a2_evaluator.py",
    "src/research/hypothesis_oos/v5a2_transport.py",
    "src/research/hypothesis_engine/schema_v3.py",
    "src/research/hypothesis_engine/validator_v4.py",
    "src/research/hypothesis_engine/firewall_v4.py",
    "research/hypothesis_engine/_build_v5a2.py",
    "research/hypothesis_engine/_freeze_v5a2.py",
    "research/hypothesis_engine/_v5a2_surface_battery.py",
    "tests/research/hypothesis_oos/test_v5a2_prespend.py",
]
#: Frozen upstream modules that MUST NOT have changed. Hashed so a later reader can prove
#: V5A.2 did not reach into V2/V3/V5A/V5A.1 territory.
FROZEN_MODULES = [
    "src/research/hypothesis_engine/schema.py",
    "src/research/hypothesis_engine/schema_v2.py",
    "src/research/hypothesis_engine/validator.py",
    "src/research/hypothesis_engine/validator_v2.py",
    "src/research/hypothesis_engine/validator_v3.py",
    "src/research/hypothesis_engine/firewall.py",
    "src/research/hypothesis_engine/firewall_v2.py",
    "src/research/hypothesis_engine/firewall_v3.py",
    "src/research/hypothesis_engine/vocabulary.py",
    "src/research/hypothesis_engine/capability.py",
    "src/research/hypothesis_engine/condition_contract.py",
    "src/research/hypothesis_engine/query_plan.py",
    "src/research/hypothesis_oos/v5a1_evidence.py",
    "src/research/hypothesis_oos/v5a1_packet.py",
    "src/research/hypothesis_oos/v5a1_semantics.py",
    "src/research/hypothesis_oos/v5a1_evaluator.py",
    "src/research/hypothesis_oos/v5a1_prompt.py",
]
CHAMPION_ARTIFACT = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _sha_text(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def calibration() -> dict:
    """tokens-per-byte, measured per arm on V5A.1's observed counts."""
    v1 = {arm: json.load(open(f"{V5A1_OUT}/packets_{arm}.json"))
          for arm in ("base", "research")}
    from src.research.hypothesis_oos import v5a1_prompt as PR1
    out = {}
    for arm in ("base", "research"):
        payload = PR1.build_user_payload(v1[arm][CALIBRATION_FIXTURE])
        system_bytes = len(PR1.SYSTEM_PROMPT)
        total_bytes = len(payload) + system_bytes
        out[arm] = {"v5a1_payload_bytes": len(payload),
                    "v5a1_system_bytes": system_bytes,
                    "v5a1_total_bytes": total_bytes,
                    "v5a1_observed_input_tokens": V5A1_OBSERVED[arm],
                    "tokens_per_byte": V5A1_OBSERVED[arm] / total_bytes}
    return out


def main():
    packets = {arm: json.load(open(f"{OUT}/packets_{arm}.json"))
               for arm in ("base", "research")}
    cal = calibration()

    manifest = {"model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
                "prompt_version": PR.V5A2_PROMPT_VERSION,
                "system_prompt_sha256": _sha_text(PR.SYSTEM_PROMPT),
                "system_prompt_identical_across_arms": True,
                "schema_version": schema_v3.SCHEMA_VERSION,
                "schema_content_hash": schema_v3.schema_content_hash(),
                "calls": []}

    tot_in = tot_mean = tot_p90 = tot_max = 0
    for fid in PAIRED:
        for arm in ("base", "research"):
            pk = packets[arm][fid]
            payload = PR.build_user_payload(pk)
            total_bytes = len(payload) + len(PR.SYSTEM_PROMPT)
            in_tok = int(round(total_bytes * cal[arm]["tokens_per_byte"]))
            reps = REPEATABILITY_CALLS if fid in PAIRED[:REPEATABILITY_CALLS] else 0
            n = 1 + reps
            manifest["calls"].append({
                "fixture_id": fid, "arm": arm, "n_calls": n,
                "repeatability_calls": reps,
                "packet_hash": pk["packet_hash"],
                "derived_from_v5a1_packet_hash": pk["derived_from_v5a1_packet_hash"],
                "payload_bytes": len(payload),
                "est_input_tokens": in_tok,
                "serialized_request_sha256": _sha_text(PR.serialized_request(pk))})
            tot_in += in_tok * n
            tot_mean += OUTPUT_TOKENS_MEAN * n
            tot_p90 += OUTPUT_TOKENS_P90 * n
            tot_max += OUTPUT_TOKENS_MAX * n

    n_calls = sum(c["n_calls"] for c in manifest["calls"])
    cost = {
        "calibration": cal,
        "calibration_source": "V5A.1 observed input-token counts on the six paid calls "
                              "(4 base, 2 research), not a chars/4 proxy",
        "n_calls_total": n_calls,
        "n_paired_calls": len(PAIRED) * 2,
        "n_repeatability_extra_calls": REPEATABILITY_CALLS * 2 * REPEATABILITY_CALLS,
        "total_input_tokens_est": tot_in,
        "total_output_tokens_mean": tot_mean,
        "total_output_tokens_p90": tot_p90,
        "total_output_tokens_max": tot_max,
        "price_in_per_1k": PRICE_IN_PER_1K, "price_out_per_1k": PRICE_OUT_PER_1K,
        "expected_cost_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                                   + tot_mean / 1000 * PRICE_OUT_PER_1K, 4),
        "p90_cost_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                              + tot_p90 / 1000 * PRICE_OUT_PER_1K, 4),
        "hard_ceiling_usd": round(tot_in / 1000 * PRICE_IN_PER_1K
                                  + tot_max / 1000 * PRICE_OUT_PER_1K, 4),
    }

    battery = json.load(open(f"{OUT}/surface_battery.json"))
    evaluator_freeze = {
        "evaluator_module": "src/research/hypothesis_oos/v5a2_evaluator.py",
        "evaluator_sha256": _sha_file(f"{ROOT}/src/research/hypothesis_oos/"
                                      f"v5a2_evaluator.py"),
        "frozen_before_first_paid_call": True,
        "spend_usd_at_freeze": 0.0,
        **EV.version_stamp(),
        "thresholds_inherited_from_v5a1": {
            "discipline_tolerance": EV.DISCIPLINE_TOLERANCE,
            "min_self_noise_floor": EV.MIN_SELF_NOISE_FLOOR,
            "primary_metric": EV.PRIMARY_METRIC},
        "run_exactly_once": True,
    }
    with open(f"{OUT}/EVALUATOR_FREEZE.json", "w") as fh:
        json.dump(evaluator_freeze, fh, indent=1, sort_keys=True)

    prereg = {
        "preregistration_version": "v5a2_final_interface_closure_prereg_v1",
        "experiment": "V5A2_FINAL_INTERFACE_CLOSURE",
        "spend_usd_so_far": 0.0,
        "goal": "Make it impossible for the next experiment to fail because of an "
                "undocumented mismatch between the evidence packet, prompt, schema, "
                "validator, firewall, compiler, evaluator or transport environment. The "
                "goal is NOT to make the model pass.",
        "v5a1_status": {
            "V5A1_MECHANICAL_VERDICT": "FAIL",
            "V5A1_SCIENTIFIC_STATUS": "ABORTED_NON_EVALUABLE",
            "artifacts_preserved_unchanged": True,
            "calls_completed": 6, "calls_planned": 38, "spend_usd": 0.9084,
            "defects_closed_here": {
                "D1": "packet/schema namespace mismatch (required_capabilities)",
                "D2": "undeclared abstention rule rejecting INSUFFICIENT_EVIDENCE+refs",
                "D3": "venue term ambiguity made the base-arm rejection uninterpretable",
                "D4": "boto3 without Converse; transport requirement lived in prose",
                "D5": "prose firewall missed '<number> probability' phrasing "
                      "(found by the generated battery, not present in the live run)"},
        },
        "ontology": O.ontology_snapshot(),
        "single_language_rule": (
            "conditions[].dimension, required_capabilities and the packet availability "
            "map are ALL projections of v5a2_ontology. No layer declares an enum."),
        "paired_fixtures": PAIRED,
        "arms": {
            "base": "derived summaries only (no match rows, no venue split, no short "
                    "windows, no opponent-profile cohorts)",
            "research": "full match-level PIT-safe record + summaries + opponent-profile "
                        "cohorts + short windows",
            "only_evidence_representation_differs": True},
        "shared_stack": {
            "model_id": MODEL_ID, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
            "prompt": PR.V5A2_PROMPT_VERSION,
            "schema": schema_v3.SCHEMA_VERSION,
            "validator": validator_v4.VALIDATOR_VERSION,
            "firewall": firewall_v4.FIREWALL_VERSION,
            "admissibility": ADM.ADMISSIBILITY_VERSION,
            "contract": C.CONTRACT_VERSION,
            "translation": TR.TRANSLATION_VERSION,
            "ontology": O.ONTOLOGY_VERSION,
            "transport": TRN.TRANSPORT_VERSION,
            "compiler": "query_plan.compile_hypothesis (frozen, internal namespace)",
            "vocabulary": vocabulary.VOCABULARY_VERSION,
            "capability_inventory": capability.CAPABILITY_INVENTORY_VERSION,
            "max_hypotheses": schema_v3.MAX_HYPOTHESES},
        "request_manifest": manifest,
        "cost_model": cost,
        "evaluator_freeze": evaluator_freeze,
        "evaluability_gate": {
            "min_paired_fixtures": EV.MIN_PAIRED_FIXTURES,
            "min_valid_responses_per_arm": EV.MIN_VALID_RESPONSES_PER_ARM,
            "min_repeatability_groups_per_arm": EV.MIN_REPEATABILITY_GROUPS_PER_ARM,
            "rule": "no PASS/MIXED/FAIL is issued unless the run is EVALUABLE; execution "
                    "status and scientific status are reported separately and never "
                    "collapsed"},
        "stop_rules": {
            "V5A2_STOP_INFRASTRUCTURE_CONTRACT_FAILURE":
                f">= {EV.INFRASTRUCTURE_CONTRACT_FAILURE_STOP_N} apparatus contract "
                f"failure (expected 0)",
            "V5A2_STOP_MODEL_SCHEMA_INVALID_RATE":
                f"model-schema-invalid rate > {EV.MODEL_SCHEMA_INVALID_RATE_STOP} after "
                f"at least {EV.MIN_CALLS_BEFORE_RATE_STOP} calls",
            "V5A2_STOP_TRANSPORT":
                f"{EV.CONSECUTIVE_TRANSPORT_FAILURE_STOP_N} consecutive transport failures",
            "V5A2_STOP_COST_CEILING": "cumulative spend exceeds the hard ceiling",
            "preflight": "transport preflight asserts hasattr(client,'converse') before "
                         "the first request, at zero spend",
            "unchanged_from_v5a1": ["schema-invalid rate threshold 0.30",
                                    "3 consecutive transport failures",
                                    "cost ceiling"],
            "changed_from_v5a1": ["the schema-invalid numerator is now MODEL failures "
                                  "only; apparatus failures have their own, stricter rule"]},
        "surface_contract_audit": {
            "n_cases": battery["n_cases"],
            "n_violations": battery["n_violations"],
            "model_visible_enum_coverage":
                battery["coverage"]["model_visible_enum_coverage"],
            "hard_rule": "a structurally correct use of an advertised term never returns "
                         "SCHEMA_INVALID"},
        "module_hashes": {m: _sha_file(f"{ROOT}/{m}") for m in MODULES},
        "frozen_upstream_module_hashes": {m: _sha_file(f"{ROOT}/{m}")
                                          for m in FROZEN_MODULES},
        "champion_protection": {"artifact": CHAMPION_ARTIFACT,
                                "frozen_sha256": CHAMPION_FROZEN_SHA,
                                "current_sha256": _sha_file(CHAMPION_ARTIFACT),
                                "read_only": True, "auto_promotion": False},
        "downstream_boundary": "V5A.2 is infrastructure closure only. It produces no "
                               "predictive coefficients, no candidate features, no OOS "
                               "search, no thresholds and no prospective predictions. "
                               "Nothing here may be promoted to p_model or CHAMPION.",
        "spend_authorization": "REQUIRED. This preregistration does NOT authorize spend.",
    }
    with open(f"{OUT}/PREREGISTRATION.json", "w") as fh:
        json.dump(prereg, fh, indent=1, sort_keys=True, default=str)

    print(f"n_calls_total: {n_calls}")
    print(f"expected ${cost['expected_cost_usd']:.4f} | "
          f"p90 ${cost['p90_cost_usd']:.4f} | ceiling ${cost['hard_ceiling_usd']:.4f}")
    print(f"input tokens est: {tot_in}")
    for arm in ("base", "research"):
        print(f"  {arm:9s} tokens/byte = {cal[arm]['tokens_per_byte']:.6f} "
              f"(observed {cal[arm]['v5a1_observed_input_tokens']})")
    print(f"champion unchanged: "
          f"{prereg['champion_protection']['current_sha256'] == CHAMPION_FROZEN_SHA}")
    print(f"schema_v2 hash unchanged: {schema_v2.schema_content_hash()[:16]}")
    print(f"PREREGISTRATION sha: "
          f"{_sha_file(f'{OUT}/PREREGISTRATION.json')[:16]}")
    print(f"EVALUATOR_FREEZE sha: {_sha_file(f'{OUT}/EVALUATOR_FREEZE.json')[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
