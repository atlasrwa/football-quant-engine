"""Build the successor Item 6 Stage-1 RUN MANIFEST V2 (execution/spend amendment). ZERO SPEND.

WHY V2 EXISTS
The narrow zero-spend amendment changes EXECUTION/SPEND semantics only: the authoritative
pre-inference input-cost reservation now comes from the AWS Bedrock CountTokens operation
(model-specific, matches what would be charged), layered on top of the retained byte ceiling,
the frozen MAX output reservation, and the human dollar ceiling. Because spend semantics
changed, a SUCCESSOR run-manifest version is created; V1 is NOT overwritten (historical
record preserved).

WHAT V2 BINDS (in addition to everything V1 bound)
  * the CountTokens implementation path + version + source sha256;
  * the CountTokens request construction (derived from the exact canonical inference request);
  * the spend-guard v2 version + code hash;
  * the runner v2 code hash + execution-status code hash;
  * the price table + input/output price + MAX output tokens + byte ceiling + hard call cap.

INVARIANTS
  * EVERY scientific artifact hash is recomputed from the SAME on-disk files V1 bound and MUST
    equal V1's scientific hashes byte-for-byte (asserted here). No scientific artifact changes.
  * the CHAMPION hash is unchanged and only integrity-checked, never read into logic.
  * the human-authorized monetary ceiling stays NOT_YET_AUTHORIZED (null): authorization comes
    AFTER this proof passes.

Produces research/item6/ITEM6_STAGE1_RUN_MANIFEST_V2.json and prints
ITEM6_STAGE1_RUN_MANIFEST_V2_SHA256. Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V2.json"
V1_PATH = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V1.json"
RUN_MANIFEST_VERSION = "item6_stage1_run_manifest_v2"

# Same scientific artifact set V1 bound (paths identical => hashes MUST match V1 exactly).
SCIENTIFIC = {
    "research_protocol": "research/item6/ITEM6_RESEARCH_PROTOCOL_V1.md",
    "baseline_coverage_spec_md": "research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.md",
    "baseline_coverage_spec_json": "research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.json",
    "mechanism_prompt": "research/item6/ITEM6_MECHANISM_PROMPT_V1.md",
    "mechanism_schema_md": "research/item6/ITEM6_MECHANISM_SCHEMA_V1.md",
    "mechanism_schema_code": "src/research/item6/schema.py",
    "baseline_equivalence_detector": "src/research/item6/baseline_equivalence.py",
    "mechanism_formalizer": "src/research/item6/formalizer.py",
    "quality_protocol_md": "research/item6/STAGE1_QUALITY_PROTOCOL_V1.md",
    "quality_protocol_code": "src/research/item6/quality_protocol.py",
    "stage1_gate_md": "research/item6/STAGE1_GATE_V1.md",
    "stage1_gate_code": "src/research/item6/stage1_gate.py",
    "stage1_metrics_code": "src/research/item6/stage1_metrics.py",
    "power_cost": "research/item6/STAGE1_POWER_AND_COST_V1.md",
    "cohort_manifest": "research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json",
    "freeze_manifest": "research/item6/ITEM6_FREEZE_MANIFEST.json",
}
# Execution artifacts (V2 spend/execution apparatus).
EXECUTION = {
    "execution_config": "research/item6/ITEM6_STAGE1_EXECUTION_CONFIG_V1.json",
    "price_table": "research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json",
    "request_set": "research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V1.json",
    "pass_b_policy": "research/item6/ITEM6_STAGE1_PASS_B_POLICY_V1.json",
    "execution_status_code": "src/research/item6/execution/execution_status.py",
    "request_builder_code": "src/research/item6/execution/request_builder.py",
    "spend_guard_code": "src/research/item6/execution/spend_guard.py",
    "runner_code": "src/research/item6/execution/runner.py",
    "token_counter_code": "src/research/item6/execution/token_counter.py",
}
CHAMPION = "data/discovery/pilotC_stat_mixer.json"


def _sha(rel: str) -> str:
    with open(f"{ROOT}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def main() -> None:
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    reqset = json.load(open(f"{ROOT}/{EXECUTION['request_set']}"))
    v1 = json.load(open(V1_PATH))

    scientific_hashes = {k: _sha(v) for k, v in SCIENTIFIC.items()}
    # HARD INVARIANT: scientific artifacts unchanged vs V1 (byte-identical hashes).
    assert scientific_hashes == v1["scientific_artifact_hashes"], (
        "SCIENTIFIC ARTIFACT DRIFT vs V1 -- amendment must not change any scientific artifact")

    price = json.load(open(f"{ROOT}/{EXECUTION['price_table']}"))

    manifest = {
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "supersedes_run_manifest_version": v1["run_manifest_version"],
        "predecessor_run_manifest_sha256": v1["run_manifest_sha256"],
        "amendment": ("ITEM6_STAGE1_AUTHORITATIVE_PROVIDER_TOKEN_COUNT_PRECALL_RESERVATION"),
        "amendment_scope": "EXECUTION_AND_SPEND_SEMANTICS_ONLY_NO_SCIENTIFIC_CHANGE",
        "experiment": "ITEM6_NOVEL_HYPOTHESIS_DISCOVERY_AND_INCREMENTAL_VALUE",
        "stage": "STAGE_1_GENERATION",
        "source_head": head,
        "branch": "feat/item6-novel-hypothesis-discovery",

        # scientific identities: byte-identical to V1.
        "scientific_artifact_hashes": scientific_hashes,
        "scientific_artifact_paths": SCIENTIFIC,
        "scientific_artifacts_unchanged_vs_v1": True,

        "execution_artifact_hashes": {k: _sha(v) for k, v in EXECUTION.items()},
        "execution_artifact_paths": EXECUTION,

        "model_provider": "aws_bedrock",
        "model_profile_id": "us.anthropic.claude-sonnet-4-6",
        "model_id": "anthropic.claude-sonnet-4-6",
        "inference_profile_arn": ("arn:aws:bedrock:us-east-1:865147226910:"
                                  "inference-profile/us.anthropic.claude-sonnet-4-6"),
        "region": "us-east-1",
        "inference_parameters": {
            "max_tokens": 8192,
            "temperature": 0.0,
            "top_p_declared": 1.0,
            "top_p_on_wire": None,
            "tool_choice": "forced_single_tool:emit_item6_mechanisms",
            "max_turns": 1,
            "max_search_calls": 0,
            "network_search_enabled": False,
        },

        "stage1_n_fixtures": 120,
        "k_mechanisms_per_fixture": 5,
        "model_calls_per_fixture": 1,
        "one_response_contains_all_k": True,
        "one_call_per_mechanism": False,
        "planned_primary_model_calls": 120,

        "retry_policy": {
            "max_retries_per_fixture": 0,
            "max_paid_treatments_per_fixture": 1,
            "attempt_marker_precedes_transmission": True,
            "uncertain_attempt_not_retried": True,
            "unknown_status_fails_closed": True,
            "received_response_is_treatment": True,
            "abstention_is_valid_treatment": True,
            "abstention_triggers_retry": False,
        },
        "absolute_max_paid_calls": 120,
        "absolute_max_model_attempts": 120,

        # --- v2 spend/execution binding -------------------------------------------------
        "spend_control_version": "item6_stage1_spend_guard_v2",
        "runner_version": "item6_stage1_runner_v2",
        "execution_status_version": "item6_execution_status_v1",
        "token_counter_version": "item6_token_counter_v1",
        "token_counter_code_path": EXECUTION["token_counter_code"],
        "token_counter_code_sha256": _sha(EXECUTION["token_counter_code"]),
        "count_tokens_operation": "aws_bedrock_runtime_CountTokens",
        "count_tokens_request_construction": {
            "derived_from": "exact_canonical_converse_inference_request",
            "count_input_shape": "input.converse={messages,system,toolConfig}; modelId top-level",
            "inference_config_excluded_reason": (
                "inferenceConfig is an output/generation control and does not affect input "
                "tokenization; modelId is the top-level CountTokens parameter"),
            "binds_system_prompt": True,
            "binds_messages": True,
            "binds_tool_schema": True,
            "binds_tool_choice_model": "us.anthropic.claude-sonnet-4-6",
            "request_immutable_after_count": True,
            "recount_required_on_any_change": True,
        },
        "price_table_version": price["price_table_version"],
        "input_price_usd_per_mtok": price["input_price_usd_per_mtok"],
        "output_price_usd_per_mtok": price["output_price_usd_per_mtok"],
        "request_set_version": reqset["request_set_version"],
        "request_set_sha256": reqset["request_set_sha256"],
        "max_request_utf8_bytes": reqset["max_request_utf8_bytes"],
        "max_output_tokens_reserved": 8192,

        "spend_model": {
            "precall_spend_reservation": True,
            "provider_token_count_precall": True,
            "count_tokens_matches_actual_request": True,
            "count_tokens_failure_blocks_inference": True,
            "request_mutation_after_count_blocked": True,
            "input_token_reservation_authority": "authoritative_provider_count_tokens",
            "byte_ceiling_retained_independently": True,
            "hard_monetary_stop": True,
            "call_cap_stop": True,
            "reservation_is_monotonic": True,
            "reservation_uses_average_per_call": False,
            "input_token_bound_method": "authoritative_provider_count_tokens",
            "byte_ceiling_method": ("utf8_byte_upper_bound_over_canonical_request_capped_at_"
                                    "max_request_bytes"),
            "output_token_reservation_method": "frozen_max_tokens_always",
            "count_tokens_is_inference_treatment": False,
            "count_tokens_consumes_paid_treatment_slot": False,
            "human_authorized_monetary_ceiling_usd": None,
            "human_authorized_monetary_ceiling_note": (
                "NOT YET AUTHORIZED. Authorization comes AFTER this proof passes. The runner "
                "enforces the ceiling per call via an authoritative provider CountTokens "
                "input reservation + frozen MAX output reservation, and blocks before "
                "inference if the next reservation would breach the ceiling."),
            "can_actual_accounting_exceed_human_ceiling_without_precall_block": False,
            "actual_cost_cannot_exceed_human_ceiling_without_precall_block": True,
        },

        "pass_b_policy": {
            "role": "DIAGNOSTIC_ONLY",
            "pass_b_required_for_primary_gate": False,
            "pass_b_execution_deferred": True,
            "pass_b_included_in_stage1_generation_budget": False,
            "pass_b_requires_separate_human_spend_authorization": True,
            "primary_gate_computable_without_pass_b": True,
        },

        "stage2_activation": "BLOCKED_UNLESS_STAGE1_PASS",
        "champion_path": CHAMPION,
        "champion_sha256": _sha(CHAMPION),
        "champion_independent": True,
        "runner_has_no_champion_dependency": True,

        "live_sonnet_calls": 0,
        "bedrock_paid_calls": 0,
        "bedrock_inference_calls": 0,
        "pass_b_paid_calls": 0,
        "new_spend_usd": 0,
    }
    # HARD INVARIANT: CHAMPION unchanged vs V1.
    assert manifest["champion_sha256"] == v1["champion_sha256"], "CHAMPION DRIFT vs V1"

    manifest["run_manifest_sha256"] = hashlib.sha256(_canon(manifest)).hexdigest()
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"[run-manifest-v2] wrote {OUT}")
    print(f"[run-manifest-v2] ITEM6_STAGE1_RUN_MANIFEST_V2_SHA256="
          f"{manifest['run_manifest_sha256']}")


if __name__ == "__main__":
    main()
