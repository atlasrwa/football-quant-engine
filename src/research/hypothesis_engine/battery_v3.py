"""V3 pre-spend manifest builder for SONNET46_HYPOTHESIS_V3.

Fully preregisters every planned call by MATERIALIZING and HASHING every scientific input
BEFORE inference. Makes NO network call and imports no Bedrock client: pure functions over
frozen JSON.

WHY 56 CALLS AND NOT 64
-----------------------
The battery is sized per control by what it has to answer, not by copying V2's shape.
Every arm below is justified in the preregistration; two V2 arms are deliberately dropped:

  * `venue_flip` -- V2 ran it to test bounded venue sensitivity. V3's headline depth
    question is about conditioning BEYOND venue, and venue sensitivity is already covered
    by the availability ablation and the profile-axis perturbation. Dropped: 6 calls.
  * `formation_ablation` -- formation is genuinely CONTRASTIVE in only 3 of the 12
    fixtures, so an ablation arm would have at most 3 informative cases. V3 therefore
    MEASURES formation utilization on those 3 fixtures and does not CONTROL it. The
    consequence is stated plainly in the preregistration: no formation claim can be made
    in either direction at N=3. Dropped: 6 calls.

And one arm is deliberately made LARGER than a minimal design would suggest:

  * `repeatability` is 6 fixtures x 2 repeat calls = 12 calls, giving 3 samples per fixture
    and 18 same-input pairs. The same-input Jaccard median is the DENOMINATOR of two hard
    gates (D12, D13), so a noisy floor would turn a borderline identity result into a coin
    flip. 4 extra calls is the cheapest reliability in the battery.

CALL LAYOUT (frozen), total 56:
    reference                  12   frozen REFERENCE packet, as-is
    repeatability              12   6 fixtures x 2, REFERENCE packet + hash UNCHANGED
    identity_alias              6   transformed (controls.identity_alias)
    irrelevant_field            6   transformed (controls.irrelevant_field)
    profile_axis_perturbation   6   transformed (controls_v3, NEW)
    availability_ablation       6   transformed (controls_v3, NEW)
    evidence_starvation         4   transformed (controls.evidence_starvation)
    unsupported_data_trap       4   transformed (controls.unsupported_data_trap)
                               --
                               56
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

from . import (availability, capability, condition_contract, controls, controls_v3,
               evaluation_v2, firewall_v2, leakage, multicondition, normalize,
               prompt_v2 as PROMPT, query_plan, schema_v2, validator_v2, verdict_v3,
               vocabulary)

MANIFEST_VERSION = "hypothesis_prespend_manifest_v3"
GENERATION_ID = "HYPOTHESIS_LAYER_V1"
EXPERIMENT_ID = "SONNET46_HYPOTHESIS_V3"
OUT_DIR = "/home/ubuntu/research/hypothesis_engine/out"
RUN_DIR_NAME = "hypothesis_v3_sonnet46"

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
INFERENCE_PROFILE_ARN = ("arn:aws:bedrock:us-east-1:865147226910:inference-profile/"
                         "us.anthropic.claude-sonnet-4-6")
BASE_MODEL_ID = "anthropic.claude-sonnet-4-6"
REGION = "us-east-1"
CACHE_NAMESPACE = "hypothesis_v3_sonnet46"

INFERENCE_CONFIG = {"maxTokens": 8192, "temperature": 0.0}

#: (control, n_calls, kind, transform). Participating fixtures are always the FIRST n in
#: frozen battery order, exactly as V2 did, so fixture selection involves no choice.
CALL_LAYOUT = [
    ("reference", 12, "reference", None),
    ("repeatability", 12, "repeatability", None),
    ("identity_alias", 6, "transform", "identity_alias"),
    ("irrelevant_field", 6, "transform", "irrelevant_field"),
    ("profile_axis_perturbation", 6, "transform", "profile_axis_perturbation"),
    ("availability_ablation", 6, "transform", "availability_ablation"),
    ("evidence_starvation", 4, "transform", "evidence_starvation"),
    ("unsupported_data_trap", 4, "transform", "unsupported_data_trap"),
]

TOTAL_PLANNED_CALLS = sum(n for _c, n, _k, _t in CALL_LAYOUT)

#: repeatability: 6 fixtures, 2 extra calls each. With the reference call that is 3
#: same-input samples per fixture and C(3,2)=3 pairs, so 18 pairs.
REPEATABILITY_FIXTURES = 6
REPEATABILITY_CALLS_PER_FIXTURE = 2

PRICE_PER_1K_INPUT = 0.003
PRICE_PER_1K_OUTPUT = 0.015

#: Output-token assumption, frozen from Sonnet 4.6's OWN observed distribution in the
#: completed V2 run (n=64 recorded responses), not from a guess:
#:     mean 2580.1   median 2695.5   p90 2957   max 3213   min 110
#: Verified by `_build_v3.py` against `hypothesis_states.jsonl`.
EST_OUTPUT_TOKENS_PER_CALL = 2581
EST_OUTPUT_TOKENS_P90 = 2957
EST_OUTPUT_TOKENS_MAX = 3213

#: INPUT-TOKEN CALIBRATION -- a correction V2's manifest did not make.
#:
#: V2 estimated input tokens as chars/4 of the serialized request and reported 770,528 for
#: 64 calls. Bedrock actually billed 1,228,036. The chars/4 convention UNDERSTATED real
#: input by a factor of 1.5938, so V2's $8.49 "expected cost" was structurally low.
#:
#: chars/4 is retained as the primary measurement because it is exact, reproducible from
#: the frozen request text and comparable with V2's manifest. But every COST figure below
#: is computed on the CALIBRATED count, so the money numbers reflect what will actually be
#: billed rather than a convention.
INPUT_TOKEN_CALIBRATION = 1.5938
INPUT_TOKEN_CALIBRATION_BASIS = (
    "measured on the completed V2 run: 1,228,036 billed input tokens across 64 calls "
    "against 770,528 estimated by chars/4 of the identical serialized requests")

#: Hard ceiling uses the model's configured maxTokens, not the observed max: the ceiling
#: must bound the worst case the API can actually produce.
CEILING_OUTPUT_TOKENS = INFERENCE_CONFIG["maxTokens"]


#: Paths this experiment must never write. Declared as a module-level PROTECTED_PATHS
#: constant, which is the convention `test_architecture_isolation` recognises as a
#: PROTECTIVE mention: the isolation scan elides this assignment so a deny-list entry does
#: not read as a dependency, while any real reference elsewhere still fails the scan.
PROTECTED_PATHS = (
    "research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/** "
    "(SONNET46_HYPOTHESIS_V2 = FAIL, permanently frozen)",
    "research/hypothesis_engine/out/PRESPEND_MANIFEST_sonnet46_v2.json (frozen)",
    "research/hypothesis_engine/out/PRESPEND_MANIFEST_sonnet46_v1.json (frozen)",
    "research/hypothesis_engine/out/PRESPEND_MANIFEST_v1.json (frozen)",
    "research/hypothesis_engine/out/V2_COUNTERFACTUAL_REPLAY_v3contract/** "
    "(diagnostic replay, frozen)",
    "research/llm_matchup/** (LLM_LATENT_STATE_EXPERIMENT, frozen)",
    "research/contextual_matchup/CHAMPION_FREEZE.json",
    "data/forward/**",
    "data/prospective/**",
    "data/forecast_broadcast/**",
    "data/discovery/pilotC_stat_mixer.json",
)


def _expected_property(control: str) -> str:
    return {
        "reference": "baseline generation on the untouched frozen packet; defines the "
                     "intent set every control is compared against AND is the ONLY arm "
                     "from which research-depth and restraint metrics are computed",
        "repeatability": "SAME packet and hash as the reference call. Establishes the "
                         "generator's same-input noise floor, which is the denominator "
                         "of the relative invariance gates D12 and D13",
        "identity_alias": "INVARIANCE: a synthetic display-label swap must not move "
                          "normalized scientific intent more than a rerun of the "
                          "identical input does",
        "irrelevant_field": "INVARIANCE: a provably irrelevant metadata note must not "
                            "move normalized scientific intent",
        "profile_axis_perturbation": "SENSITIVITY: a coherent change to the away side's "
                                     "OFFENSIVE shot profile should move intent on that "
                                     "surface. Reported separately: does the chosen "
                                     "opponent-profile AXIS track the perturbation?",
        "availability_ablation": "CAPABILITY BOUNDARY: opponent_profile is withdrawn "
                                 "while its evidence is left intact. Profile-conditioned "
                                 "questions must disappear or abstain; every other "
                                 "question should survive. Its paired 'with the "
                                 "dimension' arm is the untouched reference call",
        "evidence_starvation": "ABSTENTION: a starved packet should yield abstention or "
                               "narrower questions, never invention. Scored with the "
                               "CORRECTED definition in which an empty hypothesis set is "
                               "full abstention",
        "unsupported_data_trap": "CAPABILITY AWARENESS: a note dangles injuries and a "
                                 "rumoured shape that no evidence or capability "
                                 "supports; no hypothesis may treat either as fact and "
                                 "no evidence id may be fabricated",
    }[control]


def _serialize_request(packet: dict) -> str:
    """The literal text that would be transmitted: system prompt + user message + tool
    schema. Used for the leakage audit AND for exact input-token measurement."""
    return (PROMPT.system_prompt()
            + PROMPT.build_user_message(packet)
            + json.dumps(PROMPT.tool_spec(), sort_keys=True))


def _input_tokens(packet: dict) -> int:
    """chars/4 over the exact serialized request -- the manifest's measured convention,
    identical to V2's so the two generations' token accounting is comparable."""
    return len(_serialize_request(packet)) // 4


def _manifest_of(packet: dict) -> capability.FixtureCapabilityManifest:
    cm = packet["capability_manifest"]
    return capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()))


def _module_hash(module) -> str:
    import inspect
    return hashlib.sha256(inspect.getsource(module).encode()).hexdigest()


def _self_hash() -> str:
    """Hash of THIS module's own source, so the manifest builder is pinned too."""
    with open(__file__, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# ======================================================================================
# Fixture capability matrix -- the eligibility denominators, frozen pre-spend
# ======================================================================================
def fixture_capability_matrix(battery: dict, packets_by_id: dict) -> dict:
    """Per-fixture availability of every exposed research dimension.

    This is what makes every research-depth denominator eligibility-aware. A metric is
    only ever divided by the fixtures where the dimension it measures is genuinely
    AVAILABLE, never by all fixtures.
    """
    rows = []
    eligible: dict[str, list] = {}
    for f in battery["fixtures"]:
        fid = f["fixture_id"]
        packet = packets_by_id[fid]
        ont = availability.build_ontology(packet, _manifest_of(packet))
        row = {"fixture_id": fid, "stratum": f.get("stratum"),
               "n_evidence": len(packet.get("evidence") or []),
               "n_available_metrics": len(
                   packet["capability_manifest"]["available_metrics"]),
               "dimensions": {}, "comparisons": {}}
        for name, d in sorted(ont.dimensions.items()):
            row["dimensions"][name] = {
                "status": d.status,
                "eligible_for_depth_denominator": d.expectable,
                "coverage_rate": d.coverage_rate,
                "observed_levels": list(d.observed_levels),
                "available_axes": list(d.available_axes),
                "withheld_axes": list(d.withheld_axes),
            }
            if d.expectable:
                eligible.setdefault(name, []).append(fid)
        for name, c in sorted(ont.comparisons.items()):
            row["comparisons"][name] = {"status": c.status,
                                        "eligible": c.expectable}
        rows.append(row)

    return {
        "availability_version": availability.AVAILABILITY_VERSION,
        "n_fixtures": len(rows),
        "per_fixture": rows,
        "eligible_fixtures_by_dimension": {k: sorted(v)
                                           for k, v in sorted(eligible.items())},
        "depth_denominators": {
            k: len(v) for k, v in sorted(eligible.items())},
        "note": ("`eligible_for_depth_denominator` is True only for status AVAILABLE. "
                 "AVAILABLE_LOW_CONTRAST, COMPILE_AVAILABLE_NO_EVIDENCE and WITHHELD are "
                 "all EXCLUDED from denominators -- never scored as a zero."),
    }


# ======================================================================================
# Call specs
# ======================================================================================
def build_call_specs(battery: dict, packets_by_id: dict) -> tuple[list[dict], dict, dict]:
    """Materialize every planned call with frozen, hash-verifiable inputs.

    Returns (call_specs, materialized_packets, transform_provenance).
    """
    order = [f["fixture_id"] for f in battery["fixtures"]]
    call_specs: list[dict] = []
    materialized: dict[str, dict] = {}
    provenance: dict[str, list] = {}

    seq = 0
    for control, n, kind, transform in CALL_LAYOUT:
        if control == "repeatability":
            fixtures = []
            for fid in order[:REPEATABILITY_FIXTURES]:
                fixtures.extend([fid] * REPEATABILITY_CALLS_PER_FIXTURE)
        else:
            fixtures = order[:n]

        for idx, fid in enumerate(fixtures):
            ref = packets_by_id[fid]
            params: dict = {}

            if kind in ("reference", "repeatability"):
                packet = ref
                packet_key = f"reference::{fid}"
                tversion = None
                tdesc = ("NONE (frozen reference packet, sent as-is)"
                         if kind == "reference" else
                         "NONE (reference packet and hash reused unchanged; a repeat "
                         "call has no transformed scientific input to freeze)")
            elif transform == "identity_alias":
                packet = controls.identity_alias(ref)
                packet_key = f"identity_alias::{fid}"
                tversion = controls.CONTROLS_VERSION
                tdesc = "controls.identity_alias (synthetic display labels only)"
                params = {"alias_map": dict(controls.IDENTITY_ALIAS_MAP)}
            elif transform == "irrelevant_field":
                packet = controls.irrelevant_field(ref)
                packet_key = f"irrelevant_field::{fid}"
                tversion = controls.CONTROLS_VERSION
                tdesc = "controls.irrelevant_field (one provably-irrelevant note)"
                params = {"tag": controls.IRRELEVANT_FIELD_TAG}
            elif transform == "profile_axis_perturbation":
                raise_band = idx in controls_v3.PROFILE_AXIS_RAISE_INDICES
                packet, changed = controls_v3.profile_axis_perturbation(
                    ref, raise_band=raise_band)
                packet_key = f"profile_axis_perturbation::{fid}"
                tversion = controls_v3.CONTROLS_V3_VERSION
                tdesc = ("controls_v3.profile_axis_perturbation (away-side OFFENSIVE "
                         "shot profile scaled coherently)")
                params = {
                    "direction": "RAISE" if raise_band else "LOWER",
                    "factor": (controls_v3.PROFILE_AXIS_RAISE_FACTOR if raise_band
                               else controls_v3.PROFILE_AXIS_LOWER_FACTOR),
                    "metrics": list(controls_v3.PROFILE_AXIS_PERTURBATION_METRICS),
                    "subject": controls_v3.PROFILE_AXIS_PERTURBATION_SUBJECT,
                }
                provenance[packet_key] = changed
            elif transform == "availability_ablation":
                packet = controls_v3.availability_ablation(ref)
                packet_key = f"availability_ablation::{fid}"
                tversion = controls_v3.CONTROLS_V3_VERSION
                tdesc = ("controls_v3.availability_ablation (capability withdrawn, "
                         "evidence untouched)")
                params = {"dimensions":
                          list(controls_v3.AVAILABILITY_ABLATION_DIMENSIONS),
                          "paired_with_arm": "reference"}
            elif transform == "evidence_starvation":
                packet = controls.evidence_starvation(ref)
                packet_key = f"evidence_starvation::{fid}"
                tversion = controls.CONTROLS_VERSION
                tdesc = "controls.evidence_starvation"
                params = {"keep_n": controls.STARVATION_KEEP_N}
            elif transform == "unsupported_data_trap":
                packet = controls.unsupported_data_trap(ref)
                packet_key = f"unsupported_data_trap::{fid}"
                tversion = controls.CONTROLS_VERSION
                tdesc = "controls.unsupported_data_trap (dangling note, no evidence added)"
                params = {"note": controls.UNSUPPORTED_DATA_TRAP_NOTE}
            else:
                raise ValueError(f"unknown transform {transform!r}")

            materialized[packet_key] = packet
            call_specs.append({
                "seq": seq,
                "control": control,
                "control_type": kind,
                "source_fixture": fid,
                "packet_key": packet_key,
                "source_packet_hash": ref["packet_hash"],
                "resulting_packet_hash": packet["packet_hash"],
                "transformation": tdesc,
                "transformation_version": tversion,
                "transformation_params": params,
                "expected_property": _expected_property(control),
                "input_tokens": _input_tokens(packet),
                "serialized_request_sha256": hashlib.sha256(
                    _serialize_request(packet).encode()).hexdigest(),
            })
            seq += 1

    return call_specs, materialized, provenance


# ======================================================================================
# Manifest
# ======================================================================================
def build_manifest(battery: dict, packets_by_id: dict, *,
                   expected_cache_hits: int = 0) -> tuple[dict, dict]:
    call_specs, materialized, provenance = build_call_specs(battery, packets_by_id)

    # ---- leakage audit on every materialized packet AND its serialized request --------
    audit_findings = []
    for key, packet in sorted(materialized.items()):
        for f in leakage.audit_packet(
                packet, cutoff_unix=packet.get("information_cutoff_unix")):
            audit_findings.append({"packet_key": key, "finding": str(f)})
        for f in leakage.audit_serialized_request(_serialize_request(packet)):
            audit_findings.append({"packet_key": key, "request_finding": str(f)})

    tokens = [s["input_tokens"] for s in call_specs]
    total_in = sum(tokens)
    n = len(call_specs)

    calibrated_in = int(round(total_in * INPUT_TOKEN_CALIBRATION))

    def cost(out_per_call: int) -> float:
        """Cost on CALIBRATED input tokens -- see INPUT_TOKEN_CALIBRATION."""
        return round(calibrated_in / 1000 * PRICE_PER_1K_INPUT
                     + n * out_per_call / 1000 * PRICE_PER_1K_OUTPUT, 4)

    by_control: dict[str, int] = {}
    for s in call_specs:
        by_control[s["control"]] = by_control.get(s["control"], 0) + 1

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generation_id": GENERATION_ID,
        "experiment_id": EXPERIMENT_ID,
        "status": "SONNET46_HYPOTHESIS_V3_SPEND_AUTHORIZATION_REQUIRED",
        "authorization_required": True,

        "scientific_question": (
            "When given a corrected typed contract and an explicit but non-forcing "
            "research ontology, can Sonnet 4.6 generate fixture-specific, "
            "evidence-grounded, deterministic-query-compilable conditional football "
            "hypotheses that go beyond trivial single-dimension baseline comparisons "
            "while preserving restraint and capability awareness?"),
        "what_this_is_not": [
            "NOT a football prediction experiment",
            "NOT a test of whether any hypothesis is statistically true",
            "NO hypothesis becomes a predictive feature",
            "NO deterministic effect estimation is part of this experiment",
        ],

        "bedrock_identity": {
            "requested_model_id": MODEL_ID,
            "base_model_id": BASE_MODEL_ID,
            "inference_profile_arn": INFERENCE_PROFILE_ARN,
            "region": REGION,
            "model_id_is_date_pinned": False,
            "inference_config": dict(INFERENCE_CONFIG),
            "identifier_source": ("research/llm_matchup/out/"
                                  "FREEZE_LLM_MATCHUP_V3_SONNET46.json; resolved on "
                                  "every prior 4.6 call"),
        },

        # ---- frozen component identity ------------------------------------------------
        "prompt_version": PROMPT.PROMPT_VERSION,
        "prompt_content_hash": PROMPT.prompt_content_hash(),
        "schema_version": schema_v2.SCHEMA_VERSION,
        "schema_content_hash": schema_v2.schema_content_hash(),
        "condition_contract_version": condition_contract.CONTRACT_VERSION,
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
        "availability_version": availability.AVAILABILITY_VERSION,
        "firewall_version": firewall_v2.FIREWALL_VERSION,
        "normalization_version": normalize.INTENT_VERSION,
        "query_plan_version": query_plan.QUERY_PLAN_VERSION,
        "validator_version": validator_v2.VALIDATOR_VERSION,
        "evaluation_version": evaluation_v2.EVALUATION_VERSION,
        "multicondition_classifier_version": multicondition.CLASSIFIER_VERSION,
        "verdict_version": verdict_v3.VERDICT_VERSION,
        "controls_version": controls.CONTROLS_VERSION,
        "controls_v3_version": controls_v3.CONTROLS_V3_VERSION,

        "module_hashes": {
            "condition_contract": _module_hash(condition_contract),
            "schema_v2": _module_hash(schema_v2),
            "availability": _module_hash(availability),
            "firewall_v2": _module_hash(firewall_v2),
            "normalize": _module_hash(normalize),
            "query_plan": _module_hash(query_plan),
            "validator_v2": _module_hash(validator_v2),
            "evaluation_v2": _module_hash(evaluation_v2),
            "multicondition": _module_hash(multicondition),
            "verdict_v3": _module_hash(verdict_v3),
            "controls": _module_hash(controls),
            "controls_v3": _module_hash(controls_v3),
            "prompt_v2": _module_hash(PROMPT),
            "battery_v3": _self_hash(),
        },

        # ---- battery ------------------------------------------------------------------
        "battery_hash": battery["battery_hash"],
        "n_fixtures": len(battery["fixtures"]),
        "fixture_ids_in_frozen_order": [f["fixture_id"] for f in battery["fixtures"]],
        "call_layout": [{"control": c, "n_calls": n_, "kind": k, "transform": t}
                        for c, n_, k, t in CALL_LAYOUT],
        "planned_calls_by_control": by_control,
        "total_planned_calls": TOTAL_PLANNED_CALLS,
        "n_unique_packets": len(materialized),
        "expected_cache_hits": expected_cache_hits,
        "expected_new_paid_calls": TOTAL_PLANNED_CALLS - expected_cache_hits,
        "repeatability_structure": {
            "n_fixtures": REPEATABILITY_FIXTURES,
            "repeat_calls_per_fixture": REPEATABILITY_CALLS_PER_FIXTURE,
            "samples_per_fixture_including_reference":
                REPEATABILITY_CALLS_PER_FIXTURE + 1,
            "same_input_pairs": REPEATABILITY_FIXTURES * 3,
            "why": ("the same-input Jaccard median is the DENOMINATOR of gates D12 and "
                    "D13, so it is deliberately over-sampled relative to a minimal design"),
        },
        "dropped_v2_arms": {
            "venue_flip": ("V3's depth question is about conditioning BEYOND venue; venue "
                           "sensitivity is already covered by the availability ablation "
                           "and the profile-axis perturbation"),
            "formation_ablation": ("formation is contrastive in only 3 of 12 fixtures, so "
                                   "an ablation arm would have at most 3 informative "
                                   "cases. V3 MEASURES formation utilization on those 3 "
                                   "and does not CONTROL it; no formation claim can be "
                                   "made in either direction at N=3"),
        },
        "context_addition_control": controls_v3.CONTEXT_ADDITION_REJECTION,

        # ---- scoring, frozen -----------------------------------------------------------
        "verdict_rule": verdict_v3.version_stamp(),
        "depth_metrics_are_eligibility_aware": True,
        "depth_and_restraint_measured_on": "the 12 reference responses only",
        "discipline_measured_on": "all completed calls",
        "gate_policy": ("Fail closed. An unmeasured gate is NOT a pass, and a criterion "
                        "below its minimum N scores NOT MET rather than being excluded."),
        "interpretation_policy": (
            "Two outputs are produced and kept separate. The MECHANICAL VERDICT is a pure "
            "function of these frozen thresholds. The SCIENTIFIC INTERPRETATION is written "
            "afterwards and discusses usefulness to a football quant researcher, whether "
            "conditional structures exploit the supplied evidence, whether output remains "
            "generic, and whether complexity looks meaningful or prompt-induced. The "
            "interpretation MAY NOT alter the mechanical verdict."),

        "request_leakage_audit": {
            "method": ("leakage.audit_packet + leakage.audit_serialized_request on every "
                       "materialized packet and its exact serialized request; a finding "
                       "refuses the call"),
            "packets_audited": len(materialized),
            "total_findings": len(audit_findings),
            "findings": audit_findings,
            "status": "CLEAN" if not audit_findings else "FINDINGS_PRESENT",
        },

        # ---- cost ----------------------------------------------------------------------
        "token_and_cost_estimate": {
            "measurement": ("input tokens are chars/4 of the EXACT serialized request "
                            "(system prompt + user message + tool schema) for each of the "
                            f"{n} frozen calls -- the same convention V2 used. Output is a "
                            "frozen ESTIMATE from Sonnet 4.6's OWN observed distribution "
                            "in the completed V2 run (n=64)."),
            "price_per_1k_input_usd": PRICE_PER_1K_INPUT,
            "price_per_1k_output_usd": PRICE_PER_1K_OUTPUT,
            "total_input_tokens_all_calls_chars_over_4": total_in,
            "mean_input_tokens_per_call_chars_over_4": round(total_in / n, 1),
            "min_input_tokens_per_call_chars_over_4": min(tokens),
            "max_input_tokens_per_call_chars_over_4": max(tokens),
            "input_token_calibration_factor": INPUT_TOKEN_CALIBRATION,
            "input_token_calibration_basis": INPUT_TOKEN_CALIBRATION_BASIS,
            "total_input_tokens_all_calls_calibrated": calibrated_in,
            "mean_input_tokens_per_call_calibrated": round(calibrated_in / n, 1),
            "costs_are_computed_on": "the CALIBRATED input count",
            "estimated_output_tokens_per_call": EST_OUTPUT_TOKENS_PER_CALL,
            "estimated_output_tokens_per_call_p90": EST_OUTPUT_TOKENS_P90,
            "estimated_output_tokens_per_call_observed_max": EST_OUTPUT_TOKENS_MAX,
            "ceiling_output_tokens_per_call": CEILING_OUTPUT_TOKENS,
            "expected_cost_usd": cost(EST_OUTPUT_TOKENS_PER_CALL),
            "p90_cost_usd": cost(EST_OUTPUT_TOKENS_P90),
            "observed_max_cost_usd": cost(EST_OUTPUT_TOKENS_MAX),
            "hard_spend_ceiling_usd": cost(CEILING_OUTPUT_TOKENS),
            "ceiling_basis": ("every call returns the configured maxTokens "
                             f"({CEILING_OUTPUT_TOKENS}); this is the most the API can "
                             "bill for this battery and is the figure authorization is "
                             "requested against"),
        },

        # ---- isolation / protection ------------------------------------------------------
        "namespace_isolation": {
            "cache_namespace": CACHE_NAMESPACE,
            "cache_root": f"{OUT_DIR}/{RUN_DIR_NAME}/cache",
            "separate_from_legacy": True,
            "note": ("cache key includes model id, prompt/schema hash and packet hash, so "
                     "no V1/V2 or legacy response can ever be served to V3"),
        },
        "artifacts_to_be_written": [
            f"{OUT_DIR}/{RUN_DIR_NAME}/hypothesis_states.jsonl",
            f"{OUT_DIR}/{RUN_DIR_NAME}/execution_ledger.json",
            f"{OUT_DIR}/{RUN_DIR_NAME}/call_manifest.csv",
            f"{OUT_DIR}/{RUN_DIR_NAME}/controls.json",
            f"{OUT_DIR}/{RUN_DIR_NAME}/evaluation_report.json",
            f"{OUT_DIR}/{RUN_DIR_NAME}/verdict.json",
            f"{OUT_DIR}/{RUN_DIR_NAME}/cache/<sha256>.json",
        ],
        "artifacts_that_must_not_be_touched": list(PROTECTED_PATHS),
        "production_architecture_untouched": {
            "CHAMPION": "unchanged", "p_model": "unchanged",
            "calibration": "unchanged", "prediction_engine": "unchanged",
            "market_comparison": "unchanged", "prospective_publication": "unchanged",
            "funnel": ("LLM hypothesis -> deterministic historical measurement -> "
                       "sample/coverage sufficiency -> confounder-aware analysis -> "
                       "walk-forward OOS -> prospective validation -> candidate feature "
                       "-> quant model"),
        },

        "lifecycle": [
            "manifest", "call spec", "packet hash", "serialized request", "raw response",
            "validation", "normalized intent", "compiled query plan", "evaluation",
            "verdict",
        ],

        "call_specs": call_specs,
        "transform_provenance": provenance,
    }

    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return manifest, materialized


def write_manifest(manifest: dict, materialized: dict, *, out_dir: str = OUT_DIR) -> tuple:
    os.makedirs(out_dir, exist_ok=True)
    mpath = os.path.join(out_dir, "PRESPEND_MANIFEST_sonnet46_v3.json")
    ppath = os.path.join(out_dir, "MATERIALIZED_PACKETS_sonnet46_v3.json")
    with open(mpath, "w") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True, default=str)
    with open(ppath, "w") as fh:
        json.dump(materialized, fh, indent=1, sort_keys=True, default=str)
    return mpath, ppath
