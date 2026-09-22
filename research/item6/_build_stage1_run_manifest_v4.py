"""Build the successor Item 6 Stage-1 RUN MANIFEST V4 (authentic live-transport readiness).

ZERO PAID INFERENCE. Importing/running this builder makes no Bedrock inference call.

WHY V4 EXISTS
The prior authorized Stage-1 run correctly STOPPED before any treatment because (B1) no
committed authentic Bedrock transport/driver bound the runner to a real bedrock-runtime
client, and (B2) the declared SDK pin predated the Converse/CountTokens operations. This
amendment closes both: it adds a committed authentic live transport + live driver (reusing
the frozen V5A.2/V6 transport primitives), and pins the SDK to a build whose service model
exposes both operations. Because the EXECUTION apparatus changed, a SUCCESSOR run-manifest
version is created; V1/V2/V3 are NOT overwritten.

WHAT V4 BINDS (vs V3)
  * the pinned AWS SDK identities (boto3 / botocore) proven to expose Converse + CountTokens;
  * the authentic live transport identity/version/source-hash;
  * the live driver identity/version/source-hash;
  * the CountTokens + Converse capability contract and the model-identifier semantics
    (CountTokens -> foundation-model id; Converse -> inference-profile id);
  * the reused frozen transport module hashes (v5a2 / v6 / v6_token_count).

WHAT IS UNCHANGED (asserted here, byte-for-byte vs V3)
  * EVERY scientific artifact hash;
  * the model / inference profile (us.anthropic.claude-sonnet-4-6), NOT switched to global;
  * the US-geo price table (3.30 / 16.50) and the worst-case reservation 29.196288;
  * the request set (request BYTES byte-identical) and the mechanism prompt/schema;
  * the frozen Item 6 CountTokens implementation (token_counter), spend guard, runner,
    execution status, request builder CODE;
  * the CHAMPION hash (integrity-checked only, never read into logic).

SCIENTIFIC MODEL-VISIBLE REQUEST UNCHANGED
The live transport does NOT rebuild or alter the request: the runner builds the ONE
canonical Converse request (request_builder.canonical_request) and the transport splats it
verbatim into client.converse(**request). CountTokens receives the same system+messages+
toolConfig content; only the CountTokens `modelId` is mapped to the foundation-model id (a
tokenizer-identical route), which does NOT change the model-visible inference content. The
request builder + prompt + schema + request set are byte-identical to V3, so
SCIENTIFIC_MODEL_VISIBLE_REQUEST_UNCHANGED holds.

The human ceiling stays NOT_YET_AUTHORIZED (null): because the execution CODE changed,
re-authorization is required. The live driver requires an explicit run-time ceiling and
never embeds authorized=true.

Produces research/item6/ITEM6_STAGE1_RUN_MANIFEST_V4.json and prints its SHA256.
Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V4.json"
V3_PATH = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V3.json"
RUN_MANIFEST_VERSION = "item6_stage1_run_manifest_v4"

LIVE_TRANSPORT_SRC = "src/research/item6/execution/live_transport.py"
LIVE_DRIVER_SRC = "src/research/item6/execution/live_driver.py"
REUSED_TRANSPORT = {
    "v5a2_transport": "src/research/hypothesis_oos/v5a2_transport.py",
    "v6_transport": "src/research/hypothesis_oos/v6_transport.py",
    "v6_token_count": "src/research/hypothesis_oos/v6_token_count.py",
}
CHAMPION = "data/discovery/pilotC_stat_mixer.json"


def _sha(rel: str) -> str:
    with open(f"{ROOT}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sdk_capability() -> dict:
    import boto3
    import botocore
    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    ops = set(client.meta.service_model.operation_names)
    return {
        "boto3_version": boto3.__version__,
        "botocore_version": botocore.__version__,
        "bedrock_runtime_has_converse": "Converse" in ops,
        "bedrock_runtime_has_count_tokens": "CountTokens" in ops,
    }


def main() -> None:
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    v3 = json.load(open(V3_PATH))
    cap = _sdk_capability()
    # HARD INVARIANT: the SDK actually exposes both operations (asserted from service model).
    assert cap["bedrock_runtime_has_converse"], "SDK lacks Converse"
    assert cap["bedrock_runtime_has_count_tokens"], "SDK lacks CountTokens"

    # HARD INVARIANT: scientific artifacts byte-identical vs V3.
    scientific_hashes = {k: _sha(v) for k, v in v3["scientific_artifact_paths"].items()}
    assert scientific_hashes == v3["scientific_artifact_hashes"], "SCIENTIFIC DRIFT vs V3"

    # HARD INVARIANT: the frozen Item 6 execution CODE (counter/guard/runner/status/builder)
    # and the price table + request set are unchanged vs V3.
    for k in ("token_counter_code", "spend_guard_code", "runner_code",
              "execution_status_code", "request_builder_code", "price_table", "request_set"):
        assert _sha(v3["execution_artifact_paths"][k]) == v3["execution_artifact_hashes"][k], (
            f"EXECUTION ARTIFACT DRIFT vs V3 for {k}")

    execution_paths = dict(v3["execution_artifact_paths"])
    # add the NEW live-transport + live-driver sources to the bound execution set.
    execution_paths["live_transport_code"] = LIVE_TRANSPORT_SRC
    execution_paths["live_driver_code"] = LIVE_DRIVER_SRC
    execution_hashes = {k: _sha(v) for k, v in execution_paths.items()}

    manifest = {
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "supersedes_run_manifest_version": v3["run_manifest_version"],
        "predecessor_run_manifest_sha256": v3["run_manifest_sha256"],
        "amendment": "ITEM6_STAGE1_AUTHENTIC_LIVE_TRANSPORT_READINESS",
        "amendment_scope": "EXECUTION_TRANSPORT_AND_SDK_ONLY_NO_SCIENTIFIC_CHANGE",
        "experiment": "ITEM6_NOVEL_HYPOTHESIS_DISCOVERY_AND_INCREMENTAL_VALUE",
        "stage": "STAGE_1_GENERATION",
        "source_head": head,
        "branch": "feat/item6-novel-hypothesis-discovery",

        # scientific identities: byte-identical to V1/V2/V3.
        "scientific_artifact_hashes": scientific_hashes,
        "scientific_artifact_paths": v3["scientific_artifact_paths"],
        "scientific_artifacts_unchanged_vs_v1": True,
        "scientific_artifacts_unchanged_vs_v3": True,
        "scientific_model_visible_request_unchanged": True,
        "scientific_model_visible_request_unchanged_note": (
            "The live transport does not rebuild or alter the request: the frozen runner "
            "builds the ONE canonical Converse request (request_builder.canonical_request) "
            "and the transport splats it verbatim into client.converse(**request). "
            "CountTokens receives the same system+messages+toolConfig; only the CountTokens "
            "modelId is mapped to the tokenizer-identical foundation-model id. request "
            "builder + prompt + schema + request set are byte-identical to V3, so no "
            "model-visible scientific content changed."),

        "execution_artifact_hashes": execution_hashes,
        "execution_artifact_paths": execution_paths,

        # model / profile: UNCHANGED. NOT switched to global.
        "model_provider": "aws_bedrock",
        "model_profile_id": "us.anthropic.claude-sonnet-4-6",
        "model_id": "anthropic.claude-sonnet-4-6",
        "inference_profile_arn": v3["inference_profile_arn"],
        "region": "us-east-1",
        "model_profile_unchanged_vs_v3": True,
        "does_not_switch_to_global_profile": True,
        "inference_parameters": v3["inference_parameters"],

        "stage1_n_fixtures": 120,
        "k_mechanisms_per_fixture": 5,
        "model_calls_per_fixture": 1,
        "one_response_contains_all_k": True,
        "one_call_per_mechanism": False,
        "planned_primary_model_calls": 120,
        "retry_policy": v3["retry_policy"],
        "absolute_max_paid_calls": 120,
        "absolute_max_model_attempts": 120,

        # --- unchanged spend/count apparatus (no logic redesign) -------------------------
        "spend_control_version": v3["spend_control_version"],
        "runner_version": v3["runner_version"],
        "execution_status_version": v3["execution_status_version"],
        "token_counter_version": v3["token_counter_version"],
        "token_counter_code_path": v3["token_counter_code_path"],
        "token_counter_code_sha256": _sha(v3["token_counter_code_path"]),
        "count_tokens_operation": v3["count_tokens_operation"],
        "count_tokens_request_construction": v3["count_tokens_request_construction"],
        "count_tokens_implementation_unchanged_vs_v3": True,

        # --- NEW: authentic live transport + driver identities ---------------------------
        "live_transport_version": "item6_bedrock_transport_v1",
        "live_transport_source_path": LIVE_TRANSPORT_SRC,
        "live_transport_source_sha256": _sha(LIVE_TRANSPORT_SRC),
        "live_driver_version": "item6_stage1_live_driver_v1",
        "live_driver_source_path": LIVE_DRIVER_SRC,
        "live_driver_source_sha256": _sha(LIVE_DRIVER_SRC),
        "reused_transport_sources": REUSED_TRANSPORT,
        "reused_transport_source_sha256": {k: _sha(v) for k, v in REUSED_TRANSPORT.items()},

        # --- SDK / capability contract ---------------------------------------------------
        "aws_sdk_dependency_file": "pyproject.toml",
        "boto3_version": cap["boto3_version"],
        "botocore_version": cap["botocore_version"],
        "bedrock_runtime_has_converse": cap["bedrock_runtime_has_converse"],
        "bedrock_runtime_has_count_tokens": cap["bedrock_runtime_has_count_tokens"],
        "sdk_capability_asserted_from_service_model": True,
        "converse_model_identifier": "inference_profile_id:us.anthropic.claude-sonnet-4-6",
        "count_tokens_model_identifier": "foundation_model_id:anthropic.claude-sonnet-4-6",
        "count_tokens_profile_compatibility_verified": True,
        "count_tokens_profile_compatibility_basis": (
            "AWS CountTokens API takes the foundation-model id and an input.converse block "
            "compatible with that model; its returned count matches what Converse would "
            "charge for the same input. Claude tokenization is a model-family property, "
            "identical across the regional routes the US inference profile fans out to."),

        "live_execution_contract": {
            "mode_explicit": True,
            "modes": ["LIVE_BEDROCK", "STANDIN"],
            "live_mode_rejects_standin": True,
            "standin_cannot_emit_live_receipt": True,
            "no_generic_operator_callable_in_live_mode": True,
            "count_tokens_bound_to_converse_request": True,
            "request_immutable_after_count": True,
            "attempt_marker_precedes_transmission": True,
            "fail_closed_startup_preflight": True,
            "requires_explicit_runtime_ceiling": True,
            "embeds_authorized_true": False,
        },

        # --- price / reservation (unchanged US-geo basis) --------------------------------
        "price_table_version": v3["price_table_version"],
        "input_price_usd_per_mtok": v3["input_price_usd_per_mtok"],
        "output_price_usd_per_mtok": v3["output_price_usd_per_mtok"],
        "request_set_version": v3["request_set_version"],
        "request_set_sha256": v3["request_set_sha256"],
        "request_bytes_unchanged_vs_v1": v3["request_bytes_unchanged_vs_v1"],
        "max_request_utf8_bytes": v3["max_request_utf8_bytes"],
        "max_output_tokens_reserved": v3["max_output_tokens_reserved"],
        "worst_case_reservation": v3["worst_case_reservation"],

        "spend_model": {
            **v3["spend_model"],
            "human_authorized_monetary_ceiling_usd": None,
            "human_authorized_monetary_ceiling_note": (
                "NOT YET AUTHORIZED. Because the execution CODE changed (authentic live "
                "transport + driver + SDK pin), the prior Stage-1 authorization does NOT "
                "carry over. Re-authorization is required. The live driver requires an "
                "explicit run-time ceiling (prospective $30.00 hard maximum, >= worst-case "
                "29.196288) and never embeds authorized=true."),
            "prospective_human_ceiling_usd": 30.00,
            "reauthorization_required_after_execution_code_change": True,
        },

        "pass_b_policy": v3["pass_b_policy"],
        "stage2_activation": "BLOCKED_UNLESS_STAGE1_PASS",
        "champion_path": CHAMPION,
        "champion_sha256": _sha(CHAMPION),
        "champion_independent": True,
        "runner_has_no_champion_dependency": True,

        "live_sonnet_generation_calls": 0,
        "bedrock_paid_inference_calls": 0,
        "new_paid_inference_spend_usd": 0,
        "live_sonnet_calls": 0,
        "bedrock_paid_calls": 0,
        "new_spend_usd": 0,
    }
    # HARD INVARIANT: CHAMPION unchanged vs V3.
    assert manifest["champion_sha256"] == v3["champion_sha256"], "CHAMPION DRIFT vs V3"

    manifest["run_manifest_sha256"] = hashlib.sha256(_canon(manifest)).hexdigest()
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"[run-manifest-v4] wrote {OUT}")
    print(f"[run-manifest-v4] ITEM6_STAGE1_RUN_MANIFEST_V4_SHA256="
          f"{manifest['run_manifest_sha256']}")


if __name__ == "__main__":
    main()
