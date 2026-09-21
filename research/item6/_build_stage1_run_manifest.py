"""Build the single immutable Item 6 Stage-1 RUN MANIFEST (B2). ZERO SPEND, no network.

Binds, in ONE canonical-hashed document:
  * source identity (HEAD),
  * every frozen scientific artifact hash (protocol, coverage spec, prompt, schema,
    baseline-equivalence detector, formalizer, quality protocol, gate, power/cost, cohort),
  * the execution config + all inference parameters + model/provider/profile identity,
  * N=120, K=5, one-call-per-fixture semantics, retry/attempt policy, absolute call cap,
  * the spend-control version + price table + monetary ceiling model + request-set hash,
  * the Pass B execution policy,
  * the CHAMPION hash.

Produces research/item6/ITEM6_STAGE1_RUN_MANIFEST_V1.json and prints
ITEM6_STAGE1_RUN_MANIFEST_SHA256. Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V1.json"
RUN_MANIFEST_VERSION = "item6_stage1_run_manifest_v1"

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
EXECUTION = {
    "execution_config": "research/item6/ITEM6_STAGE1_EXECUTION_CONFIG_V1.json",
    "price_table": "research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json",
    "request_set": "research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V1.json",
    "pass_b_policy": "research/item6/ITEM6_STAGE1_PASS_B_POLICY_V1.json",
    "execution_status_code": "src/research/item6/execution/execution_status.py",
    "request_builder_code": "src/research/item6/execution/request_builder.py",
    "spend_guard_code": "src/research/item6/execution/spend_guard.py",
    "runner_code": "src/research/item6/execution/runner.py",
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

    manifest = {
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "experiment": "ITEM6_NOVEL_HYPOTHESIS_DISCOVERY_AND_INCREMENTAL_VALUE",
        "stage": "STAGE_1_GENERATION",
        "source_head": head,
        "branch": "feat/item6-novel-hypothesis-discovery",

        "scientific_artifact_hashes": {k: _sha(v) for k, v in SCIENTIFIC.items()},
        "scientific_artifact_paths": SCIENTIFIC,

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

        "spend_control_version": "item6_stage1_spend_guard_v1",
        "price_table_version": "item6_stage1_price_table_v1",
        "request_set_version": reqset["request_set_version"],
        "request_set_sha256": reqset["request_set_sha256"],
        "max_request_utf8_bytes": reqset["max_request_utf8_bytes"],
        "spend_model": {
            "precall_spend_reservation": True,
            "hard_monetary_stop": True,
            "call_cap_stop": True,
            "reservation_is_monotonic": True,
            "reservation_uses_average_per_call": False,
            "input_token_bound_method": ("utf8_byte_upper_bound_over_canonical_request_"
                                         "capped_at_max_request_bytes"),
            "output_token_reservation_method": "frozen_max_tokens_always",
            "per_call_max_reservation_usd": reqset["per_call_max_reservation_usd"],
            "expected_stage1_generation_spend_usd": reqset[
                "expected_stage1_generation_spend_usd"],
            "p90_stage1_generation_spend_usd": reqset["p90_stage1_generation_spend_usd"],
            "max_reserved_stage1_generation_spend_usd": reqset[
                "max_reserved_stage1_generation_spend_usd"],
            "human_authorized_monetary_ceiling_usd": None,
            "human_authorized_monetary_ceiling_note": (
                "NOT YET AUTHORIZED. The future human ceiling must be >= "
                "max_reserved_stage1_generation_spend_usd for a full run; the runner enforces "
                "the ceiling per call via pre-call reservation and stops otherwise."),
            "can_actual_accounting_exceed_human_ceiling_without_precall_block": False,
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
        "pass_b_paid_calls": 0,
        "new_spend_usd": 0,
    }
    manifest["run_manifest_sha256"] = hashlib.sha256(_canon(manifest)).hexdigest()
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"[run-manifest] wrote {OUT}")
    print(f"[run-manifest] ITEM6_STAGE1_RUN_MANIFEST_SHA256={manifest['run_manifest_sha256']}")


if __name__ == "__main__":
    main()
