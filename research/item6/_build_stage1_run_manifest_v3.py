"""Build the successor Item 6 Stage-1 RUN MANIFEST V3 (US-geo price freeze). ZERO SPEND.

WHY V3 EXISTS
The narrow US-geo price-freeze amendment corrects the EXECUTION PRICE BASIS only: the frozen
US geographic inference profile (us.anthropic.claude-sonnet-4-6) is priced with the
conservative US-only Sonnet 4.6 standard-rate basis 3.30 / 16.50 per MTok instead of the
global 3.00 / 15.00. Because the spend accounting changed, a SUCCESSOR run-manifest version
is created; V1 and V2 are NOT overwritten (historical record preserved).

WHAT V3 BINDS (vs V2)
  * corrected price table (item6_stage1_price_table_v2, 3.30 / 16.50);
  * corrected worst-case reservation (byte-ceiling input + frozen MAX output, 120 calls);
  * successor request set (item6_stage1_request_set_v2) whose REQUEST BYTES are byte-identical
    to V1/V2 (only price annotations changed);
  * predecessor V2 run-manifest sha (chain of custody).

WHAT IS UNCHANGED (asserted here, byte-for-byte vs V2)
  * every scientific artifact hash (protocol, prompt, schema, baseline coverage, baseline
    equivalence, formalizer, quality protocol, gate, metrics, power/cost, cohort, freeze);
  * the model / inference profile (us.anthropic.claude-sonnet-4-6) -- NOT switched to global;
  * the mechanism prompt / schema / cohort / Stage-1 gate;
  * the CountTokens implementation (token_counter_code sha) + spend-guard + runner + status;
  * MAX_REQUEST_UTF8_BYTES = 32768, MAX_OUTPUT_TOKENS_RESERVED = 8192,
    ABSOLUTE_MAX_PAID_CALLS = 120;
  * the CHAMPION hash (integrity-checked only, never read into logic).

The human-authorized monetary ceiling stays NOT_YET_AUTHORIZED (null): authorization comes
AFTER this proof passes and may then set a $30.00 hard maximum (a cap, not a spend target).

Produces research/item6/ITEM6_STAGE1_RUN_MANIFEST_V3.json and prints
ITEM6_STAGE1_RUN_MANIFEST_V3_SHA256. Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V3.json"
V2_PATH = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V2.json"
PRICE_V2_PATH = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json"
REQSET_V2_PATH = f"{ROOT}/research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V2.json"
RUN_MANIFEST_VERSION = "item6_stage1_run_manifest_v3"

# Same scientific artifact set V1/V2 bound (paths identical => hashes MUST match V2 exactly).
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
# Execution artifacts. Code is unchanged from V2 (no logic redesign). The price table is the
# corrected V2 table; the request set is the corrected V2 set.
EXECUTION = {
    "execution_config": "research/item6/ITEM6_STAGE1_EXECUTION_CONFIG_V1.json",
    "price_table": "research/item6/ITEM6_STAGE1_PRICE_TABLE_V2.json",
    "request_set": "research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V2.json",
    "pass_b_policy": "research/item6/ITEM6_STAGE1_PASS_B_POLICY_V1.json",
    "execution_status_code": "src/research/item6/execution/execution_status.py",
    "request_builder_code": "src/research/item6/execution/request_builder.py",
    "spend_guard_code": "src/research/item6/execution/spend_guard.py",
    "runner_code": "src/research/item6/execution/runner.py",
    "token_counter_code": "src/research/item6/execution/token_counter.py",
}
CHAMPION = "data/discovery/pilotC_stat_mixer.json"

# Frozen worst-case reservation constants (independent of code; asserted against math here).
MAX_REQUEST_UTF8_BYTES = 32768
MAX_OUTPUT_TOKENS_RESERVED = 8192
ABSOLUTE_MAX_PAID_CALLS = 120


def _sha(rel: str) -> str:
    with open(f"{ROOT}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def main() -> None:
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    v2 = json.load(open(V2_PATH))
    price = json.load(open(PRICE_V2_PATH))
    reqset = json.load(open(REQSET_V2_PATH))

    scientific_hashes = {k: _sha(v) for k, v in SCIENTIFIC.items()}
    # HARD INVARIANT: scientific artifacts unchanged vs V2 (byte-identical hashes).
    assert scientific_hashes == v2["scientific_artifact_hashes"], (
        "SCIENTIFIC ARTIFACT DRIFT vs V2 -- price amendment must not change any scientific "
        "artifact")

    # HARD INVARIANT: the CountTokens / spend-guard / runner / status CODE is unchanged vs V2
    # (no logic redesign; only prices change).
    for k in ("token_counter_code", "spend_guard_code", "runner_code",
              "execution_status_code", "request_builder_code"):
        assert _sha(EXECUTION[k]) == v2["execution_artifact_hashes"][k], (
            f"EXECUTION CODE DRIFT vs V2 for {k} -- price amendment must not redesign logic")

    # HARD INVARIANT: model / inference profile unchanged and NOT switched to global.
    in_mtok = float(price["input_price_usd_per_mtok"])
    out_mtok = float(price["output_price_usd_per_mtok"])
    assert price["model_profile_id"] == "us.anthropic.claude-sonnet-4-6"
    assert price["model_profile_id"] != "global.anthropic.claude-sonnet-4-6"
    assert (in_mtok, out_mtok) == (3.30, 16.50), "V3 must bind the US-geo 3.30/16.50 basis"

    # Deterministic worst-case reservation at the corrected prices.
    max_input_reserve = MAX_REQUEST_UTF8_BYTES * in_mtok / 1_000_000
    max_output_reserve = MAX_OUTPUT_TOKENS_RESERVED * out_mtok / 1_000_000
    max_total_reserve = max_input_reserve + max_output_reserve
    max_reserved_run = max_total_reserve * ABSOLUTE_MAX_PAID_CALLS
    assert abs(max_input_reserve - 0.1081344) < 1e-12
    assert abs(max_output_reserve - 0.135168) < 1e-12
    assert abs(max_total_reserve - 0.2433024) < 1e-12
    assert abs(max_reserved_run - 29.196288) < 1e-9
    # request BYTES unchanged vs V1/V2.
    assert reqset["request_bytes_unchanged_vs_v1"] is True

    manifest = {
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "supersedes_run_manifest_version": v2["run_manifest_version"],
        "predecessor_run_manifest_sha256": v2["run_manifest_sha256"],
        "amendment": "ITEM6_STAGE1_US_GEO_CONSERVATIVE_PRICE_FREEZE",
        "amendment_scope": "SPEND_CONTROL_ACCOUNTING_ONLY_NO_SCIENTIFIC_CHANGE",
        "experiment": "ITEM6_NOVEL_HYPOTHESIS_DISCOVERY_AND_INCREMENTAL_VALUE",
        "stage": "STAGE_1_GENERATION",
        "source_head": head,
        "branch": "feat/item6-novel-hypothesis-discovery",

        # scientific identities: byte-identical to V1/V2.
        "scientific_artifact_hashes": scientific_hashes,
        "scientific_artifact_paths": SCIENTIFIC,
        "scientific_artifacts_unchanged_vs_v1": True,
        "scientific_artifacts_unchanged_vs_v2": True,

        "execution_artifact_hashes": {k: _sha(v) for k, v in EXECUTION.items()},
        "execution_artifact_paths": EXECUTION,

        # model / profile: UNCHANGED (US geo). NOT switched to global.
        "model_provider": "aws_bedrock",
        "model_profile_id": "us.anthropic.claude-sonnet-4-6",
        "model_id": "anthropic.claude-sonnet-4-6",
        "inference_profile_arn": ("arn:aws:bedrock:us-east-1:865147226910:"
                                  "inference-profile/us.anthropic.claude-sonnet-4-6"),
        "region": "us-east-1",
        "model_profile_unchanged_vs_v2": True,
        "does_not_switch_to_global_profile": True,
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

        "retry_policy": v2["retry_policy"],
        "absolute_max_paid_calls": ABSOLUTE_MAX_PAID_CALLS,
        "absolute_max_model_attempts": 120,

        # --- unchanged v2 spend/execution apparatus (no logic redesign) ------------------
        "spend_control_version": v2["spend_control_version"],
        "runner_version": v2["runner_version"],
        "execution_status_version": v2["execution_status_version"],
        "token_counter_version": v2["token_counter_version"],
        "token_counter_code_path": EXECUTION["token_counter_code"],
        "token_counter_code_sha256": _sha(EXECUTION["token_counter_code"]),
        "count_tokens_operation": v2["count_tokens_operation"],
        "count_tokens_request_construction": v2["count_tokens_request_construction"],
        "count_tokens_implementation_unchanged_vs_v2": True,

        # --- corrected price binding -----------------------------------------------------
        "price_table_version": price["price_table_version"],
        "supersedes_price_table_version": price["supersedes_price_table_version"],
        "model_profile_scope": price["model_profile_scope"],
        "price_bound_type": price["price_bound_type"],
        "input_price_usd_per_mtok": in_mtok,
        "output_price_usd_per_mtok": out_mtok,
        "predecessor_input_price_usd_per_mtok": price["predecessor_input_price_usd_per_mtok"],
        "predecessor_output_price_usd_per_mtok": price["predecessor_output_price_usd_per_mtok"],
        "operative_price_note": price["operative_bound_note"],

        "request_set_version": reqset["request_set_version"],
        "supersedes_request_set_version": reqset["supersedes_request_set_version"],
        "request_set_sha256": reqset["request_set_sha256"],
        "predecessor_request_set_sha256": reqset["predecessor_request_set_sha256"],
        "request_bytes_unchanged_vs_v1": reqset["request_bytes_unchanged_vs_v1"],

        "max_request_utf8_bytes": MAX_REQUEST_UTF8_BYTES,
        "max_output_tokens_reserved": MAX_OUTPUT_TOKENS_RESERVED,

        # --- corrected worst-case reservation --------------------------------------------
        "worst_case_reservation": {
            "max_input_reserve_per_call_usd": 0.1081344,
            "max_output_reserve_per_call_usd": 0.135168,
            "max_total_reserve_per_call_usd": 0.2433024,
            "max_reserved_stage1_generation_spend_usd": 29.196288,
            "input_reserve_formula": "32768 * 3.30 / 1000000",
            "output_reserve_formula": "8192 * 16.50 / 1000000",
            "run_reserve_formula": "120 * 0.2433024",
        },

        "spend_model": {
            "precall_spend_reservation": True,
            "provider_token_count_precall": True,
            "count_tokens_matches_actual_request": True,
            "count_tokens_failure_blocks_inference": True,
            "request_mutation_after_count_blocked": True,
            "request_immutable_after_count": True,
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
                "NOT YET AUTHORIZED. Authorization comes AFTER this US-geo price-freeze proof "
                "passes and may then set a $30.00 HARD MAXIMUM (a cap, not an expected spend "
                "target) with ABSOLUTE_MAX_PAID_CALLS=120. $30.00 >= the mathematical "
                "worst-case reservation 29.196288 for a full 120-call run at 3.30/16.50."),
            "prospective_human_ceiling_usd": 30.00,
            "prospective_ceiling_covers_worst_case_run": True,
            "can_actual_accounting_exceed_human_ceiling_without_precall_block": False,
            "actual_cost_cannot_exceed_human_ceiling_without_precall_block": True,
        },

        "pass_b_policy": v2["pass_b_policy"],

        "stage2_activation": "BLOCKED_UNLESS_STAGE1_PASS",
        "champion_path": CHAMPION,
        "champion_sha256": _sha(CHAMPION),
        "champion_independent": True,
        "runner_has_no_champion_dependency": True,

        "live_sonnet_calls": 0,
        "bedrock_paid_calls": 0,
        "bedrock_inference_calls": 0,
        "pass_b_paid_calls": 0,
        "new_model_calls": 0,
        "new_spend_usd": 0,
    }
    # HARD INVARIANT: CHAMPION unchanged vs V2.
    assert manifest["champion_sha256"] == v2["champion_sha256"], "CHAMPION DRIFT vs V2"

    manifest["run_manifest_sha256"] = hashlib.sha256(_canon(manifest)).hexdigest()
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"[run-manifest-v3] wrote {OUT}")
    print(f"[run-manifest-v3] ITEM6_STAGE1_RUN_MANIFEST_V3_SHA256="
          f"{manifest['run_manifest_sha256']}")


if __name__ == "__main__":
    main()
