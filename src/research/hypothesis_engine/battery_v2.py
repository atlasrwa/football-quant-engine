"""V2 pre-spend manifest builder for HYPOTHESIS_GENERATOR_SONNET46_V1.

Fully preregisters every one of the 64 planned calls by MATERIALIZING and HASHING every
scientific input BEFORE inference. Reuses the frozen battery, frozen reference packets, the
frozen prompt/schema/vocabulary/capability inventory, the frozen thresholds and scoring
rubric, and the new frozen control-perturbation layer (`controls.py`).

Makes NO network call and imports no Bedrock client. Pure functions over frozen JSON.

Call layout (mandate-fixed), total 64:
    reference             12   REFERENCE packet, as-is
    repeatability         12   REFERENCE packet + hash, UNCHANGED (no transformed input)
    identity_alias         8   transformed
    formation_ablation     6   transformed
    profile_perturbation   6   transformed
    venue_flip             6   transformed
    irrelevant_field       6   transformed
    evidence_starvation    4   transformed
    unsupported_data_trap  4   transformed
                          --
                          64   ( = 12 reference + 12 repeatability + 40 transformed )
"""
from __future__ import annotations

import json
import os
from typing import Optional

from . import (battery as B, controls, evaluation, leakage, lifecycle, prompt as PROMPT,
               schema, normalize)

MANIFEST_VERSION = "hypothesis_prespend_manifest_v2"
GENERATION_ID = "HYPOTHESIS_LAYER_V1"
EXPERIMENT_ID = "HYPOTHESIS_GENERATOR_SONNET46_V1"
OUT_DIR = "/home/ubuntu/research/hypothesis_engine/out"

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
INFERENCE_PROFILE_ARN = ("arn:aws:bedrock:us-east-1:865147226910:inference-profile/"
                         "us.anthropic.claude-sonnet-4-6")
BASE_MODEL_ID = "anthropic.claude-sonnet-4-6"
REGION = "us-east-1"
CACHE_NAMESPACE = "hypothesis_v1_sonnet46_v2"

#: Frozen call layout. `n` participating fixtures are always the FIRST n in battery order.
CALL_LAYOUT = [
    ("reference", 12, "reference", None),
    ("repeatability", 12, "repeatability", None),
    ("identity_alias", 8, "transform", "identity_alias"),
    ("formation_ablation", 6, "transform", "formation_ablation"),
    ("profile_perturbation", 6, "transform", "profile_perturbation"),
    ("venue_flip", 6, "transform", "venue_flip"),
    ("irrelevant_field", 6, "transform", "irrelevant_field"),
    ("evidence_starvation", 4, "transform", "evidence_starvation"),
    ("unsupported_data_trap", 4, "transform", "unsupported_data_trap"),
]

PRICE_PER_1K_INPUT = B.PRICE_PER_1K_INPUT
PRICE_PER_1K_OUTPUT = B.PRICE_PER_1K_OUTPUT

#: Output-token assumption for Sonnet 4.6, taken from its OWN observed distribution in
#: LLM_MATCHUP_V3_SONNET46 (n=16): mean 6438.81, p90 6896, max 7126. Frozen here so the
#: cost is not a runtime choice. Labelled an ESTIMATE; output is the dominant uncertainty.
EST_OUTPUT_TOKENS_PER_CALL = 6439
EST_OUTPUT_TOKENS_P90 = 6896
EST_OUTPUT_TOKENS_MAX = 7126


def _expected_property(control: str) -> str:
    return {
        "reference": "baseline generation; defines the intent set every control is "
                     "compared against",
        "repeatability": "SAME packet+hash as reference; expect near-identical normalized "
                         "intent across the repeat call (self-noise floor)",
        "identity_alias": "INVARIANCE: synthetic display-label swap must not materially "
                          "move normalized scientific intent (Jaccard >= threshold)",
        "formation_ablation": "SENSITIVITY/REMOVAL: formation-conditioned intents should "
                              "disappear or abstain; raw-stat intents should remain",
        "profile_perturbation": "SENSITIVITY: coherent change to opponent concession "
                                "profile may move corner/cross-conditioned intent",
        "venue_flip": "SENSITIVITY(bounded): venue-conditioned intent may change; "
                      "non-venue intent should not",
        "irrelevant_field": "INVARIANCE: irrelevant metadata change must not move intent",
        "evidence_starvation": "ABSTENTION: starved packet should yield abstention or "
                               "narrower questions, never invention",
        "unsupported_data_trap": "CAPABILITY-AWARENESS: no injury/expected-formation "
                                 "hypothesis presented as fact; no fabricated evidence",
    }[control]


def _serialize_request(packet: dict) -> str:
    """The literal text that would be transmitted: system prompt + user message + tool
    schema. Used for the leakage audit AND for exact input-token measurement."""
    return (PROMPT.system_prompt()
            + PROMPT.build_user_message(packet)
            + json.dumps(PROMPT.tool_spec(), sort_keys=True))


def _input_tokens(packet: dict) -> int:
    """chars/4 over the exact serialized request (the manifest's measured convention)."""
    return len(_serialize_request(packet)) // 4


def build_call_specs(battery: dict, packets_by_id: dict) -> tuple[list[dict], dict]:
    """Materialize every one of the 64 call specs with frozen, hash-verifiable inputs.

    Returns (call_specs, materialized_packets) where materialized_packets maps a stable
    packet_key -> the exact packet dict that will be sent.
    """
    order = [f["fixture_id"] for f in battery["fixtures"]]
    call_specs: list[dict] = []
    materialized: dict[str, dict] = {}
    profile_changes: dict[str, list] = {}

    seq = 0
    for control, n, kind, transform in CALL_LAYOUT:
        fixtures = order[:n]

        # repeatability: which fixtures + how many repeats. 12 calls over 6 fixtures = 2
        # calls each (the frozen calls_per_fixture=2), each reusing the reference packet.
        if control == "repeatability":
            rep_fixtures = order[:6]
            for rep in range(2):
                for fid in rep_fixtures:
                    ref = packets_by_id[fid]
                    key = f"reference::{fid}"       # SAME packet+hash as reference
                    materialized[key] = ref
                    call_specs.append({
                        "seq": seq, "control": control, "repeat_index": rep,
                        "source_fixture": fid, "source_packet_hash": ref["packet_hash"],
                        "control_type": control, "transformation_version": None,
                        "transformation": "NONE (reuses reference packet and hash)",
                        "transformation_params": {},
                        "packet_key": key,
                        "resulting_packet_hash": ref["packet_hash"],
                        "expected_property": _expected_property(control),
                    })
                    seq += 1
            continue

        for i, fid in enumerate(fixtures):
            ref = packets_by_id[fid]

            if kind == "reference":
                key = f"reference::{fid}"
                materialized[key] = ref
                spec = {
                    "seq": seq, "control": control, "source_fixture": fid,
                    "source_packet_hash": ref["packet_hash"],
                    "control_type": control, "transformation_version": None,
                    "transformation": "NONE (frozen reference packet, sent as-is)",
                    "transformation_params": {},
                    "packet_key": key,
                    "resulting_packet_hash": ref["packet_hash"],
                    "expected_property": _expected_property(control),
                }
            else:  # transform
                params: dict = {}
                if transform == "identity_alias":
                    tp = controls.identity_alias(ref)
                    params = {"alias_map": dict(controls.IDENTITY_ALIAS_MAP)}
                elif transform == "formation_ablation":
                    tp = controls.formation_ablation(ref)
                    params = {"removed_dimensions": list(controls.FORMATION_DIMENSIONS)}
                elif transform == "profile_perturbation":
                    raise_band = i in controls.PROFILE_RAISE_INDICES
                    tp, changes = controls.profile_perturbation(ref, raise_band=raise_band)
                    profile_changes[fid] = changes
                    params = {
                        "axes": list(controls.PROFILE_PERTURBATION_AXES),
                        "subject": controls.PROFILE_PERTURBATION_SUBJECT,
                        "side": controls.PROFILE_PERTURBATION_SIDE,
                        "direction": "RAISE" if raise_band else "LOWER",
                        "factor": (controls.PROFILE_RAISE_FACTOR if raise_band
                                   else controls.PROFILE_LOWER_FACTOR),
                        "changes": changes,
                    }
                elif transform == "venue_flip":
                    tp = controls.venue_flip(ref)
                    params = {"swap": "HOME<->AWAY labels, evidence subject prefixes, "
                                      "scope.subject, formation_distribution keys"}
                elif transform == "irrelevant_field":
                    tp = controls.irrelevant_field(ref)
                    params = {"note_tag": controls.IRRELEVANT_FIELD_TAG}
                elif transform == "evidence_starvation":
                    tp = controls.evidence_starvation(ref)
                    params = {"keep_n": controls.STARVATION_KEEP_N,
                              "selection": "first STARVATION_KEEP_N by sorted evidence id, "
                                           "values blanked"}
                elif transform == "unsupported_data_trap":
                    tp = controls.unsupported_data_trap(ref)
                    params = {"trap_note": controls.UNSUPPORTED_DATA_TRAP_NOTE}
                else:
                    raise ValueError(f"unknown transform {transform!r}")

                key = f"{control}::{fid}"
                materialized[key] = tp
                spec = {
                    "seq": seq, "control": control, "source_fixture": fid,
                    "source_packet_hash": ref["packet_hash"],
                    "control_type": control,
                    "transformation_version": controls.CONTROLS_VERSION,
                    "transformation": f"controls.{transform}",
                    "transformation_params": params,
                    "packet_key": key,
                    "resulting_packet_hash": tp["packet_hash"],
                    "expected_property": _expected_property(control),
                }
            call_specs.append(spec)
            seq += 1

    return call_specs, materialized


def build_manifest_v2(battery: dict, packets_by_id: dict,
                      *, expected_cache_hits: int = 0) -> tuple[dict, dict]:
    call_specs, materialized = build_call_specs(battery, packets_by_id)

    total_calls = len(call_specs)
    unique_packets = {v["packet_hash"]: v for v in materialized.values()}

    # exact input tokens: sum the serialized request tokens for EVERY one of the 64 calls
    # (repeatability's two passes both count, since both are paid transmissions).
    per_call_input = []
    for spec in call_specs:
        pkt = materialized[spec["packet_key"]]
        per_call_input.append(_input_tokens(pkt))
    total_input = sum(per_call_input)
    new_calls = max(0, total_calls - expected_cache_hits)

    # cost from ACTUAL frozen serialized requests (input) + frozen 4.6 output assumption.
    def _cost(out_per_call: int) -> float:
        total_out = new_calls * out_per_call
        # scale input by the paid fraction too (cache hits pay nothing)
        paid_input = int(total_input * (new_calls / total_calls)) if total_calls else 0
        return round(paid_input / 1000 * PRICE_PER_1K_INPUT
                     + total_out / 1000 * PRICE_PER_1K_OUTPUT, 2)

    leak = _leakage_audit(materialized)

    out_root = os.path.join(OUT_DIR, CACHE_NAMESPACE)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "generation_id": GENERATION_ID,
        "supersedes": {
            "v1_manifest": "PRESPEND_MANIFEST_sonnet46_v1.json",
            "v1_status": "SONNET46_MANIFEST_DRIFT_ABORT (control inputs were not frozen)",
        },
        "model_id": MODEL_ID,
        "bedrock_identity": {
            "requested_model_id": MODEL_ID,
            "inference_profile_arn": INFERENCE_PROFILE_ARN,
            "base_model_id": BASE_MODEL_ID,
            "region": REGION,
            "model_id_is_date_pinned": False,
            "identifier_source":
                "research/llm_matchup/out/FREEZE_LLM_MATCHUP_V3_SONNET46.json; resolved on "
                "every prior 4.6 call.",
            "entitlement_probe": "zero-token check_bedrock_capability(); no tokens spent.",
        },
        "prompt_version": battery["prompt_version"],
        "prompt_content_hash": battery["prompt_content_hash"],
        "schema_version": battery["schema_version"],
        "schema_content_hash": battery["schema_content_hash"],
        "vocabulary_version": battery["vocabulary_version"],
        "capability_inventory_version": battery["capability_inventory_version"],
        "controls_version": controls.CONTROLS_VERSION,
        "controls_module_hash": _module_hash(
            "/home/ubuntu/src/research/hypothesis_engine/controls.py"),
        "evaluation_version": evaluation.EVALUATION_VERSION,
        "normalization_version": normalize.INTENT_VERSION,
        "scoring_module_hash": _module_hash(
            "/home/ubuntu/src/research/hypothesis_engine/evaluation.py"),
        "normalization_module_hash": _module_hash(
            "/home/ubuntu/src/research/hypothesis_engine/normalize.py"),
        "battery_hash": battery["battery_hash"],
        "n_fixtures": battery["n_fixtures"],
        "total_planned_calls": total_calls,
        "planned_calls_by_control": {c: n for c, n, *_ in CALL_LAYOUT},
        "n_reference_calls": 12,
        "n_repeatability_calls": 12,
        "n_transformed_control_calls": 40,
        "expected_cache_hits": expected_cache_hits,
        "expected_new_paid_calls": new_calls,
        "n_unique_packets": len(unique_packets),
        "call_specs": call_specs,
        "token_and_cost_estimate": {
            "measurement": "input tokens are chars/4 of the EXACT serialized request "
                           "(system prompt + user message + tool schema) for each of the "
                           "64 frozen calls; output is a frozen ESTIMATE from Sonnet 4.6's "
                           "own observed distribution.",
            "total_input_tokens_all_64": total_input,
            "min_input_tokens_per_call": min(per_call_input),
            "max_input_tokens_per_call": max(per_call_input),
            "mean_input_tokens_per_call": total_input // total_calls,
            "estimated_output_tokens_per_call": EST_OUTPUT_TOKENS_PER_CALL,
            "estimated_output_tokens_per_call_p90": EST_OUTPUT_TOKENS_P90,
            "estimated_output_tokens_per_call_max": EST_OUTPUT_TOKENS_MAX,
            "price_per_1k_input_usd": PRICE_PER_1K_INPUT,
            "price_per_1k_output_usd": PRICE_PER_1K_OUTPUT,
            "expected_cost_usd": _cost(EST_OUTPUT_TOKENS_PER_CALL),
            "p90_cost_usd": _cost(EST_OUTPUT_TOKENS_P90),
            "conservative_ceiling_usd": _cost(EST_OUTPUT_TOKENS_MAX),
        },
        "pass_fail_thresholds": dict(evaluation.THRESHOLDS),
        "gate_policy": "Fail closed. An unmeasured control gate is None and does NOT count "
                       "as a pass.",
        "scoring_rubric": {
            "A_schema_validity": "fraction of responses conforming exactly",
            "B_query_compilability": "fraction of accepted hypotheses compiling to plans",
            "C_evidence_grounding": "fraction citing only real packet evidence ids",
            "D_capability_awareness": "rate of requests for unavailable data",
            "E_numerical_authority": "HARD GATE: zero probabilities/odds/EV/grades",
            "F_relevance": "deterministic family x metric x condition relevance",
            "G_non_redundancy": "median redundancy_rate over distinct normalized intents",
            "H_metric_richness": "median distinct metrics and families per fixture",
            "I_identity_robustness": "median intent Jaccard under synthetic alias swap",
            "J_evidence_sensitivity": "fraction of real perturbations that move intent",
            "K_irrelevant_invariance": "fraction of irrelevant changes that do NOT move "
                                       "intent",
            "L_abstention_quality": "abstention rate on deliberately starved packets",
        },
        "request_leakage_audit": leak,
        "namespace_isolation": {
            "cache_namespace": CACHE_NAMESPACE,
            "cache_root": os.path.join(out_root, "cache"),
            "separate_from_legacy": True,
            "legacy_namespaces_untouched": [
                "research/llm_matchup/out/cache",
                "research/llm_matchup/out/hardening/cache",
                "research/llm_matchup/out/hardening_v3/cache",
                "research/llm_matchup/out/v3_sonnet46",
                "hypothesis_v1_sonnet5", "hypothesis_v1_sonnet46",
            ],
            "note": "Cache key includes model id, prompt/schema hash and packet hash; a "
                    "legacy or V1 response can never be served to V2.",
        },
        "artifacts_to_be_written": [
            os.path.join(out_root, "hypothesis_states.jsonl"),
            os.path.join(out_root, "execution_ledger.json"),
            os.path.join(out_root, "call_manifest.csv"),
            os.path.join(out_root, "controls.json"),
            os.path.join(out_root, "evaluation_report.json"),
            os.path.join(out_root, "materialized_packets.json"),
            os.path.join(out_root, "cache/<sha256>.json"),
        ],
        "artifacts_that_must_not_be_touched": list(B.PROTECTED_PATHS) + [
            "research/hypothesis_engine/out/PRESPEND_MANIFEST_v1.json (Sonnet 5, frozen)",
            "research/hypothesis_engine/out/PRESPEND_MANIFEST_sonnet46_v1.json (V1, "
            "drift-aborted, frozen)",
        ],
        "authorization_required": True,
        "status": "HYPOTHESIS_SONNET_SPEND_AUTHORIZATION_REQUIRED",
    }
    manifest["manifest_hash"] = lifecycle.stable_hash(
        {k: v for k, v in manifest.items() if k != "manifest_hash"})
    return manifest, materialized


def _leakage_audit(materialized: dict) -> dict:
    total = 0
    for pkt in materialized.values():
        total += len(leakage.audit_packet(pkt))
        total += len(leakage.audit_serialized_request(_serialize_request(pkt)))
    return {
        "packets_audited": len(materialized),
        "total_findings": total,
        "status": "CLEAN" if total == 0 else "BLOCKED",
        "method": "leakage.audit_packet + leakage.audit_serialized_request on every "
                  "materialized packet (reference + transformed) and its exact serialized "
                  "request; a finding refuses the call.",
    }


def _module_hash(path: str) -> str:
    with open(path, "rb") as fh:
        import hashlib
        return hashlib.sha256(fh.read()).hexdigest()


def write_manifest_v2(manifest: dict, materialized: dict, *, out_dir: str = OUT_DIR
                      ) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    mpath = os.path.join(out_dir, "PRESPEND_MANIFEST_sonnet46_v2.json")
    tmp = mpath + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    os.replace(tmp, mpath)

    # freeze the exact materialized packets so execution reads them, makes no new choice.
    ppath = os.path.join(out_dir, "MATERIALIZED_PACKETS_sonnet46_v2.json")
    tmp2 = ppath + ".tmp"
    with open(tmp2, "w") as fh:
        json.dump(materialized, fh, indent=2, sort_keys=True)
    os.replace(tmp2, ppath)
    return mpath, ppath
