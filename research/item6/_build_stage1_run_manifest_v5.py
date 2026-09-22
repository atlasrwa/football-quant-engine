"""Build the successor Item 6 Stage-1 RUN MANIFEST V5 (evidence-input materialization).

ZERO PAID INFERENCE. Importing/running this builder makes no Bedrock/LLM call.

WHY V5 EXISTS
V4 correctly stopped Stage-1 before treatment #1 because the frozen live path transmitted an
EMPTY evidence_packet ({}) while the frozen prompt/schema require a populated pre-target
evidence packet. This amendment supplies the intended input: a deterministic point-in-time
evidence-packet materializer, a frozen evidence packet set + materialized request set, and a
live-path binding that makes an empty packet impossible in LIVE mode. Because the MODEL-VISIBLE
scientific input changed (empty skeleton -> populated packet), a SUCCESSOR run-manifest version
is created; V1/V2/V3/V4 are NOT overwritten.

WHAT V5 CHANGES vs V4
  * SCIENTIFIC_MODEL_VISIBLE_REQUEST_CHANGED = true (reason: empty skeleton replaced by the
    intended pre-target evidence packet); SCIENTIFIC_REQUEST_BYTES_UNCHANGED is explicitly NOT
    claimed;
  * NEW scientific-INPUT artifacts bound (evidence packet contract, materializer source,
    frozen packet provider source, evidence packet set, materialized request set, compression
    policy) via a new `evidence_input` block + `new_scientific_input_artifact_hashes`;
  * updated execution artifact hashes for the two files that changed to enforce the populated
    packet: live_driver.py (v2, frozen-packet binding) and runner.py (LIVE empty-packet
    firewall);
  * cost DIAGNOSTICS recomputed from the REAL materialized request bytes (byte-upper-bound);
    the hard worst-case reservation (byte-ceiling based) is UNCHANGED.

WHAT IS UNCHANGED (asserted, byte-for-byte vs V4)
  * the Item 6 research protocol, mechanism PROMPT, mechanism SCHEMA, baseline coverage spec,
    baseline-equivalence detector, mechanism formalizer, quality protocol, Stage-1 gate + MD,
    Stage-1 metrics, cohort manifest, K=5, model/profile, inference settings, price table,
    transport source, SDK pins, CHAMPION;
  * the human monetary ceiling stays NOT_YET_AUTHORIZED (null): re-authorization is required
    because the model-visible scientific input changed.

Produces research/item6/ITEM6_STAGE1_RUN_MANIFEST_V5.json and prints its SHA256.
Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import os

ROOT = os.environ.get("ITEM6_CODE_ROOT", "/home/ubuntu")
OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V5.json"
V4_PATH = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V4.json"
RUN_MANIFEST_VERSION = "item6_stage1_run_manifest_v5"

LIVE_DRIVER_SRC = "src/research/item6/execution/live_driver.py"
RUNNER_SRC = "src/research/item6/execution/runner.py"

# NEW scientific-input artifacts (paths relative to ROOT).
EVIDENCE_CONTRACT = "research/item6/ITEM6_STAGE1_EVIDENCE_PACKET_CONTRACT_V1.json"
COMPRESSION_POLICY = "research/item6/ITEM6_PACKET_COMPRESSION_POLICY_V1.json"
MATERIALIZER_SRC = "src/research/item6/evidence/packet_materializer.py"
FROZEN_PROVIDER_SRC = "src/research/item6/evidence/frozen_packet_provider.py"
EVIDENCE_PKG_INIT = "src/research/item6/evidence/__init__.py"
PACKET_SET = "research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"
REQUEST_SET = "research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"


def _sha(rel: str) -> str:
    with open(f"{ROOT}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def main() -> None:
    v4 = json.load(open(V4_PATH))

    # HARD INVARIANT: every PRE-EXISTING scientific artifact is byte-identical vs V4.
    scientific_hashes = {k: _sha(v) for k, v in v4["scientific_artifact_paths"].items()}
    assert scientific_hashes == v4["scientific_artifact_hashes"], "SCIENTIFIC DRIFT vs V4"

    # HARD INVARIANT: prompt, schema, coverage, gate, cohort, metrics, formalizer, equivalence,
    # quality unchanged (subset assertion, explicit).
    for k in ("mechanism_prompt", "mechanism_schema_md", "mechanism_schema_code",
              "baseline_coverage_spec_md", "baseline_coverage_spec_json",
              "baseline_equivalence_detector", "mechanism_formalizer",
              "quality_protocol_md", "quality_protocol_code", "stage1_gate_md",
              "stage1_gate_code", "stage1_metrics_code", "cohort_manifest",
              "research_protocol"):
        assert scientific_hashes[k] == v4["scientific_artifact_hashes"][k], f"DRIFT {k}"

    # HARD INVARIANT: price table + request builder + token counter + spend guard + status +
    # transport unchanged vs V4 (only live_driver + runner change to enforce the packet).
    for k in ("token_counter_code", "spend_guard_code", "execution_status_code",
              "request_builder_code", "price_table", "live_transport_code"):
        assert _sha(v4["execution_artifact_paths"][k]) == v4["execution_artifact_hashes"][k], \
            f"EXECUTION ARTIFACT DRIFT vs V4 for {k}"

    # updated execution artifact hashes: live_driver + runner changed.
    execution_paths = dict(v4["execution_artifact_paths"])
    execution_hashes = dict(v4["execution_artifact_hashes"])
    execution_hashes["live_driver_code"] = _sha(LIVE_DRIVER_SRC)
    execution_hashes["runner_code"] = _sha(RUNNER_SRC)
    assert execution_hashes["live_driver_code"] != v4["execution_artifact_hashes"]["live_driver_code"], \
        "live_driver expected to change (populated-packet binding)"
    assert execution_hashes["runner_code"] != v4["execution_artifact_hashes"]["runner_code"], \
        "runner expected to change (LIVE empty-packet firewall)"

    # NEW scientific-INPUT artifact identities.
    packet_set = json.load(open(f"{ROOT}/{PACKET_SET}"))
    request_set = json.load(open(f"{ROOT}/{REQUEST_SET}"))
    evidence_packet_set_sha = packet_set["evidence_packet_set_sha256"]        # canonical self-hash
    materialized_request_set_sha = request_set["materialized_request_set_sha256"]

    new_input_hashes = {
        "evidence_packet_contract": _sha(EVIDENCE_CONTRACT),
        "packet_compression_policy": _sha(COMPRESSION_POLICY),
        "evidence_packet_materializer_source": _sha(MATERIALIZER_SRC),
        "frozen_packet_provider_source": _sha(FROZEN_PROVIDER_SRC),
        "evidence_package_init": _sha(EVIDENCE_PKG_INIT),
        # set identities are the CANONICAL SELF-HASHES (what the live provider verifies),
        # NOT the raw file bytes.
        "evidence_packet_set": evidence_packet_set_sha,
        "materialized_request_set": materialized_request_set_sha,
    }
    new_input_paths = {
        "evidence_packet_contract": EVIDENCE_CONTRACT,
        "packet_compression_policy": COMPRESSION_POLICY,
        "evidence_packet_materializer_source": MATERIALIZER_SRC,
        "frozen_packet_provider_source": FROZEN_PROVIDER_SRC,
        "evidence_package_init": EVIDENCE_PKG_INIT,
        "evidence_packet_set": PACKET_SET,
        "materialized_request_set": REQUEST_SET,
    }

    cost = request_set["cost_diagnostics_byte_upper_bound"]

    manifest = {
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "supersedes_run_manifest_version": v4["run_manifest_version"],
        "predecessor_run_manifest_sha256": v4["run_manifest_sha256"],
        "amendment": "ITEM6_STAGE1_EVIDENCE_INPUT_MATERIALIZATION",
        "amendment_scope": "SCIENTIFIC_MODEL_VISIBLE_INPUT_ADDED_NO_PROMPT_SCHEMA_GATE_COHORT_CHANGE",
        "experiment": v4["experiment"],
        "stage": "STAGE_1_GENERATION",
        "source_head": v4.get("source_head"),
        "execution_head_expected": "3dc1e4880e84168f090cbf8f45010537cab6b7e8",
        "branch": "feat/item6-novel-hypothesis-discovery",

        # --- model-visible input CHANGED (be precise) --------------------------------------
        "scientific_model_visible_request_changed": True,
        "model_visible_change_reason": "EMPTY_SKELETON_REPLACED_BY_INTENDED_PRETARGET_EVIDENCE_PACKET",
        "scientific_request_bytes_unchanged": False,
        "scientific_request_bytes_unchanged_note": (
            "FALSE by construction: the empty evidence_packet placeholder ({}) was replaced by "
            "the intended populated point-in-time evidence packet, so the model-visible request "
            "bytes changed. This is the whole point of the amendment."),

        # --- pre-existing scientific artifacts: byte-identical vs V1..V4 --------------------
        "scientific_artifact_hashes": scientific_hashes,
        "scientific_artifact_paths": v4["scientific_artifact_paths"],
        "preexisting_scientific_artifacts_unchanged": True,
        "preexisting_scientific_artifacts_unchanged_vs_v4": True,
        "item6_research_question_unchanged": True,
        "mechanism_prompt_unchanged": True,
        "mechanism_schema_unchanged": True,
        "baseline_coverage_unchanged": True,
        "stage1_gate_unchanged": True,
        "stage1_gate_thresholds_unchanged": True,
        "stage1_cohort_unchanged": True,

        # --- NEW scientific-INPUT artifacts added ------------------------------------------
        "new_scientific_input_artifacts_added": True,
        "new_scientific_input_artifact_hashes": new_input_hashes,
        "new_scientific_input_artifact_paths": new_input_paths,
        "evidence_input": {
            "evidence_packet_contract_version": "item6_stage1_evidence_packet_contract_v1",
            "evidence_packet_contract_path": EVIDENCE_CONTRACT,
            "evidence_packet_contract_sha256": new_input_hashes["evidence_packet_contract"],
            "evidence_packet_materializer_version": "item6_evidence_packet_materializer_v1",
            "evidence_packet_materializer_path": MATERIALIZER_SRC,
            "evidence_packet_materializer_source_sha256":
                new_input_hashes["evidence_packet_materializer_source"],
            "frozen_packet_provider_version": "item6_frozen_packet_provider_v1",
            "frozen_packet_provider_path": FROZEN_PROVIDER_SRC,
            "frozen_packet_provider_source_sha256":
                new_input_hashes["frozen_packet_provider_source"],
            "evidence_packet_set_path": PACKET_SET,
            "evidence_packet_set_sha256": evidence_packet_set_sha,
            "materialized_request_set_path": REQUEST_SET,
            "materialized_request_set_sha256": materialized_request_set_sha,
            "packet_compression_policy_path": COMPRESSION_POLICY,
            "packet_compression_policy_sha256": new_input_hashes["packet_compression_policy"],
            "packet_compression_applied": False,
            "provider": "footystats",
            "single_provider_only": True,
            "npxg_included": False,
            "npxg_semantics_status": "EXCLUDED_THESTATSAPI_ONLY_ABSENT_FROM_FOOTYSTATS_CORPUS",
            "packet_information_cutoff_policy": "PACKET_INFORMATION_CUTOFF == target kickoff_unix; all source observations strictly before cutoff",
            "n_fixtures": request_set["n_fixtures"],
            "n_packet_materialization_failures": packet_set["n_packet_materialization_failures"],
            "all_within_byte_budget": request_set["all_within_byte_budget"],
            "live_empty_evidence_packet_allowed": False,
            "live_packet_hash_enforced": True,
            "count_tokens_uses_materialized_request": True,
            "converse_uses_counted_request": True,
        },

        "execution_artifact_hashes": execution_hashes,
        "execution_artifact_paths": execution_paths,

        # model / profile / inference: UNCHANGED vs V4.
        "model_provider": v4["model_provider"],
        "model_profile_id": v4["model_profile_id"],
        "model_id": v4["model_id"],
        "inference_profile_arn": v4["inference_profile_arn"],
        "region": v4["region"],
        "inference_parameters": v4["inference_parameters"],
        "converse_model_identifier": v4["converse_model_identifier"],
        "count_tokens_model_identifier": v4["count_tokens_model_identifier"],

        "stage1_n_fixtures": 120,
        "k_mechanisms_per_fixture": 5,
        "model_calls_per_fixture": 1,
        "one_response_contains_all_k": True,
        "planned_primary_model_calls": 120,
        "retry_policy": v4["retry_policy"],
        "absolute_max_paid_calls": 120,
        "absolute_max_model_attempts": 120,

        # unchanged spend/count apparatus.
        "spend_control_version": v4["spend_control_version"],
        "runner_version": v4["runner_version"],
        "execution_status_version": v4["execution_status_version"],
        "token_counter_version": v4["token_counter_version"],
        "token_counter_code_path": v4["token_counter_code_path"],
        "token_counter_code_sha256": v4["token_counter_code_sha256"],
        "count_tokens_operation": v4["count_tokens_operation"],
        "count_tokens_request_construction": v4["count_tokens_request_construction"],

        # transport unchanged; live driver bumped to v2.
        "live_transport_version": v4["live_transport_version"],
        "live_transport_source_path": v4["live_transport_source_path"],
        "live_transport_source_sha256": _sha(v4["live_transport_source_path"]),
        "live_driver_version": "item6_stage1_live_driver_v2",
        "live_driver_source_path": LIVE_DRIVER_SRC,
        "live_driver_source_sha256": _sha(LIVE_DRIVER_SRC),
        "live_execution_contract": {
            **v4["live_execution_contract"],
            "requires_frozen_populated_evidence_packet": True,
            "live_empty_evidence_packet_allowed": False,
            "live_packet_hash_enforced": True,
        },

        # SDK / capability contract: UNCHANGED vs V4.
        "aws_sdk_dependency_file": v4["aws_sdk_dependency_file"],
        "boto3_version": v4["boto3_version"],
        "botocore_version": v4["botocore_version"],
        "bedrock_runtime_has_converse": v4["bedrock_runtime_has_converse"],
        "bedrock_runtime_has_count_tokens": v4["bedrock_runtime_has_count_tokens"],
        "sdk_capability_asserted_from_service_model": True,
        "count_tokens_profile_compatibility_verified": True,

        # price / reservation (US-geo basis unchanged); cost diagnostics recomputed on REAL reqs.
        "price_table_version": v4["price_table_version"],
        "input_price_usd_per_mtok": v4["input_price_usd_per_mtok"],
        "output_price_usd_per_mtok": v4["output_price_usd_per_mtok"],
        "max_request_utf8_bytes": v4["max_request_utf8_bytes"],
        "max_output_tokens_reserved": v4["max_output_tokens_reserved"],
        "worst_case_reservation": v4["worst_case_reservation"],
        "materialized_cost_diagnostics": {
            "basis": "byte_upper_bound_over_real_materialized_requests",
            "expected_stage1_spend_usd_byte_upper_bound":
                cost["expected_stage1_spend_usd_byte_upper_bound"],
            "p90_per_call_usd_byte_upper_bound": cost["p90_per_call_usd_byte_upper_bound"],
            "max_reserved_stage1_spend_usd": v4["worst_case_reservation"][
                "max_reserved_stage1_generation_spend_usd"],
            "request_bytes_min": request_set["request_bytes_min"],
            "request_bytes_p50": request_set["request_bytes_p50"],
            "request_bytes_p90": request_set["request_bytes_p90"],
            "request_bytes_max": request_set["request_bytes_max"],
            "hard_worst_case_reservation_unchanged": True,
        },

        "spend_model": {
            **v4["spend_model"],
            "human_authorized_monetary_ceiling_usd": None,
            "human_authorized_monetary_ceiling_note": (
                "NOT YET AUTHORIZED. The MODEL-VISIBLE scientific input changed (empty skeleton "
                "-> populated point-in-time evidence packet), so the prior authorization does "
                "NOT carry over. Explicit human Stage-1 re-authorization is required. The live "
                "driver requires an explicit run-time ceiling (prospective $30.00 hard maximum, "
                ">= worst-case 29.196288) and never embeds authorized=true."),
            "prospective_human_ceiling_usd": 30.00,
            "reauthorization_required_after_model_visible_input_change": True,
        },

        "pass_b_policy": v4["pass_b_policy"],
        "stage2_activation": "BLOCKED_UNLESS_STAGE1_PASS",
        "champion_path": v4["champion_path"],
        "champion_sha256": _sha(v4["champion_path"]),
        "champion_independent": True,
        "runner_has_no_champion_dependency": True,

        "live_sonnet_generation_calls": 0,
        "bedrock_paid_inference_calls": 0,
        "new_paid_inference_spend_usd": 0,
        "live_sonnet_calls": 0,
        "bedrock_paid_calls": 0,
        "new_spend_usd": 0,
    }
    # HARD INVARIANT: CHAMPION unchanged vs V4.
    assert manifest["champion_sha256"] == v4["champion_sha256"], "CHAMPION DRIFT vs V4"

    manifest["run_manifest_sha256"] = hashlib.sha256(_canon(manifest)).hexdigest()
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"[run-manifest-v5] wrote {OUT}")
    print(f"[run-manifest-v5] ITEM6_STAGE1_RUN_MANIFEST_V5_SHA256="
          f"{manifest['run_manifest_sha256']}")
    print(f"[run-manifest-v5] evidence_packet_set_sha256={evidence_packet_set_sha}")
    print(f"[run-manifest-v5] materialized_request_set_sha256={materialized_request_set_sha}")


if __name__ == "__main__":
    main()
