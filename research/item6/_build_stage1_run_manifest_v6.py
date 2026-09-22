"""Build the successor Item 6 Stage-1 RUN MANIFEST V6 (PROVENANCE + HASH SEMANTICS ONLY).

ZERO PAID INFERENCE. Importing/running this builder makes no Bedrock/LLM/network call.

WHY V6 EXISTS -- IT CHANGES NO SCIENTIFIC TREATMENT
V5 froze the correct treatment input (the point-in-time evidence packet contract, the
materializer, the 120 populated packets and the 120 materialized requests). V6 does NOT
regenerate, re-order or re-hash any of that: it binds the SAME frozen treatment by the SAME
identities and fixes two provenance defects in the manifest layer.

  DEFECT 1 -- SELF-REFERENTIAL EXECUTION HEAD.
  V5 carried `execution_head_expected = 3dc1e4880...`, the PARENT of the commit that landed
  V5, i.e. a commit where the evidence apparatus and the empty-packet firewall do not exist.
  Simply substituting the V5 commit sha would be wrong too: once V6 is committed, the actual
  execution HEAD becomes V6's own sha, and any self-declared value goes stale again. A commit
  sha cannot be non-circularly self-declared inside an artifact committed AT that sha.

  V6 fixes the MODEL: it separates
    * `apparatus_provenance_commit` -- the commit that introduced the frozen V5 PIT evidence
      apparatus (45876df4d...). Historical, stable, and explicitly NOT a claim about the
      future runtime HEAD; and
    * the EXACT execution head -- supplied externally by the authorizing human at run time
      (`AUTHORIZED_EXECUTION_HEAD`) and verified by the live driver against the actual git
      HEAD before any CountTokens/Converse call.
  V6 therefore declares `exact_execution_head_source = EXTERNAL_HUMAN_AUTHORIZATION` and
  carries NO `execution_head_expected` field. Do NOT re-add one, and do NOT amend V6 after
  committing it to embed its own sha -- that would recreate the circularity.

  DEFECT 2 -- AMBIGUOUS HASH SEMANTICS.
  V5's `new_scientific_input_artifact_hashes` mixed RAW FILE sha256 values with CANONICAL
  SELF-HASH values (the evidence packet set and materialized request set are bound by the
  canonical hash of their own content EXCLUDING the self-hash field -- the identity the live
  provider verifies) under one dict with no discriminator, so a naive raw-file verifier
  reports a FALSE DRIFT on those two files. V6 DROPS that ambiguous dict and replaces it with
  `artifact_hash_index`: one authoritative entry per artifact carrying {path, hash_scheme,
  sha256, self_hash_field?}. `provenance.verify_manifest_artifacts` verifies it scheme-aware
  and fails closed on an unknown scheme or a scheme/method mismatch. The underlying artifacts
  are NOT rewritten to make the schemes uniform -- only the semantics are made explicit.

SOURCE_HEAD SEMANTICS (investigated, not blindly changed)
Across the lineage `source_head` is the repository HEAD at manifest BUILD time, which is the
parent of the commit that lands the manifest: V2 -> b419f0827 (landed in 0fd5d418c), V3 ->
0fd5d418c (landed in a2c83d028), V4 -> a2c83d028 (landed in 3dc1e4880). V5's builder copied
V4's value (`v4.get("source_head")`) instead of reading build-time HEAD, so V5's source_head
(a2c83d028) is a COPY DEFECT, not a different semantic. V6 records the true build-time HEAD
and documents the meaning in `source_head_semantics`. Here it coincides with
`apparatus_provenance_commit`; each field states its own meaning so the coincidence is not
an ambiguity.

WHAT IS UNCHANGED (asserted byte-for-byte / identity-for-identity vs V5)
  * the research protocol, mechanism PROMPT, mechanism SCHEMA, baseline coverage spec,
    baseline-equivalence detector, formalizer, quality protocol, Stage-1 gate + thresholds,
    Stage-1 metrics, cohort manifest, K=5, model/profile, inference settings, price table,
    CountTokens contract, transport, runner, spend guard, Pass-B policy, CHAMPION;
  * the evidence packet contract, materializer source, frozen packet provider source, the
    evidence packet set and the materialized request set (the model-visible treatment);
  * the human monetary ceiling stays NOT_YET_AUTHORIZED (null).
The ONLY code identity that changes is live_driver.py (v2 -> v3), which gains the external
authorized-HEAD preflight; runner.py is deliberately untouched.

Produces research/item6/ITEM6_STAGE1_RUN_MANIFEST_V6.json and prints its SHA256.
Re-running is byte-idempotent.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.environ.get("ITEM6_CODE_ROOT", "/home/ubuntu")
sys.path.insert(0, ROOT)

from src.research.item6.execution import provenance as PROV  # noqa: E402

OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V6.json"
V5_PATH = f"{ROOT}/research/item6/ITEM6_STAGE1_RUN_MANIFEST_V5.json"
RUN_MANIFEST_VERSION = "item6_stage1_run_manifest_v6"

LIVE_DRIVER_SRC = "src/research/item6/execution/live_driver.py"
RUNNER_SRC = "src/research/item6/execution/runner.py"
PROVENANCE_SRC = "src/research/item6/execution/provenance.py"

PACKET_SET = "research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"
REQUEST_SET = "research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"

RAW = PROV.HashScheme.RAW_FILE_SHA256
CANON = PROV.HashScheme.CANONICAL_JSON_EXCLUDING_SELF_HASH


def _sha(rel: str) -> str:
    return PROV.raw_file_sha256(f"{ROOT}/{rel}")


def _canon(obj) -> bytes:
    return PROV.canonical_bytes(obj)


def _raw_entry(rel: str) -> dict:
    return {"path": rel, "hash_scheme": RAW, "sha256": _sha(rel)}


def _canon_entry(rel: str, self_field: str) -> dict:
    with open(f"{ROOT}/{rel}", "r", encoding="utf-8") as f:
        obj = json.load(f)
    return {"path": rel, "hash_scheme": CANON, "self_hash_field": self_field,
            "sha256": PROV.canonical_self_excluded_sha256(obj, self_field)}


def main() -> None:
    v5 = json.load(open(V5_PATH))

    # ---- HARD INVARIANT 1: every PRE-EXISTING scientific artifact byte-identical vs V5. ----
    scientific_hashes = {k: _sha(v) for k, v in v5["scientific_artifact_paths"].items()}
    assert scientific_hashes == v5["scientific_artifact_hashes"], "SCIENTIFIC DRIFT vs V5"

    # ---- HARD INVARIANT 2: the model-visible treatment input is untouched. -----------------
    ev5 = v5["evidence_input"]
    packet_set = json.load(open(f"{ROOT}/{PACKET_SET}"))
    request_set = json.load(open(f"{ROOT}/{REQUEST_SET}"))
    packet_set_sha = PROV.canonical_self_excluded_sha256(packet_set, "evidence_packet_set_sha256")
    request_set_sha = PROV.canonical_self_excluded_sha256(
        request_set, "materialized_request_set_sha256")
    assert packet_set_sha == packet_set["evidence_packet_set_sha256"], "PACKET SET SELF-HASH"
    assert request_set_sha == request_set["materialized_request_set_sha256"], "REQ SET SELF-HASH"
    assert packet_set_sha == ev5["evidence_packet_set_sha256"], "EVIDENCE PACKET SET DRIFT vs V5"
    assert request_set_sha == ev5["materialized_request_set_sha256"], "REQUEST SET DRIFT vs V5"
    assert _sha(ev5["evidence_packet_contract_path"]) == ev5["evidence_packet_contract_sha256"], \
        "PACKET CONTRACT DRIFT vs V5"
    assert _sha(ev5["evidence_packet_materializer_path"]) == \
        ev5["evidence_packet_materializer_source_sha256"], "MATERIALIZER DRIFT vs V5"
    assert _sha(ev5["frozen_packet_provider_path"]) == \
        ev5["frozen_packet_provider_source_sha256"], "FROZEN PACKET PROVIDER DRIFT vs V5"
    assert _sha(ev5["packet_compression_policy_path"]) == \
        ev5["packet_compression_policy_sha256"], "COMPRESSION POLICY DRIFT vs V5"

    # ---- HARD INVARIANT 3: execution apparatus unchanged EXCEPT the live driver. -----------
    execution_paths = dict(v5["execution_artifact_paths"])
    execution_hashes = dict(v5["execution_artifact_hashes"])
    for key, rel in execution_paths.items():
        if key == "live_driver_code":
            continue
        assert _sha(rel) == execution_hashes[key], f"EXECUTION ARTIFACT DRIFT vs V5: {key}"
    assert _sha(RUNNER_SRC) == v5["execution_artifact_hashes"]["runner_code"], \
        "runner.py must NOT change in a provenance-only amendment"
    execution_hashes["live_driver_code"] = _sha(LIVE_DRIVER_SRC)
    assert execution_hashes["live_driver_code"] != v5["execution_artifact_hashes"][
        "live_driver_code"], "live_driver expected to change (external authorized-HEAD check)"
    execution_paths["provenance_code"] = PROVENANCE_SRC
    execution_hashes["provenance_code"] = _sha(PROVENANCE_SRC)

    # ---- the authoritative, scheme-tagged artifact identity index -------------------------
    artifact_hash_index = {}
    for key, rel in v5["scientific_artifact_paths"].items():
        artifact_hash_index[f"scientific.{key}"] = _raw_entry(rel)
    for key, rel in execution_paths.items():
        artifact_hash_index[f"execution.{key}"] = _raw_entry(rel)
    artifact_hash_index["evidence_input.evidence_packet_contract"] = _raw_entry(
        ev5["evidence_packet_contract_path"])
    artifact_hash_index["evidence_input.packet_compression_policy"] = _raw_entry(
        ev5["packet_compression_policy_path"])
    artifact_hash_index["evidence_input.evidence_packet_materializer_source"] = _raw_entry(
        ev5["evidence_packet_materializer_path"])
    artifact_hash_index["evidence_input.frozen_packet_provider_source"] = _raw_entry(
        ev5["frozen_packet_provider_path"])
    artifact_hash_index["evidence_input.evidence_package_init"] = _raw_entry(
        v5["new_scientific_input_artifact_paths"]["evidence_package_init"])
    # the two SET artifacts are bound by their CANONICAL self-excluded hash, never raw bytes.
    artifact_hash_index["evidence_input.evidence_packet_set"] = _canon_entry(
        PACKET_SET, "evidence_packet_set_sha256")
    artifact_hash_index["evidence_input.materialized_request_set"] = _canon_entry(
        REQUEST_SET, "materialized_request_set_sha256")
    artifact_hash_index["champion"] = _raw_entry(v5["champion_path"])

    n_raw = sum(1 for e in artifact_hash_index.values() if e["hash_scheme"] == RAW)
    n_canon = sum(1 for e in artifact_hash_index.values() if e["hash_scheme"] == CANON)
    assert n_canon == 2, "exactly the two frozen SET artifacts use the canonical scheme"

    cost = v5["materialized_cost_diagnostics"]

    manifest = {
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "supersedes_run_manifest_version": v5["run_manifest_version"],
        "predecessor_run_manifest_sha256": v5["run_manifest_sha256"],
        "amendment": "ITEM6_STAGE1_PROVENANCE_AND_HASH_SEMANTICS",
        "amendment_scope": "PROVENANCE_ONLY_NO_SCIENTIFIC_TREATMENT_CHANGE",
        "experiment": v5["experiment"],
        "stage": "STAGE_1_GENERATION",
        "branch": v5["branch"],

        # --- provenance model (DEFECT 1 closed) --------------------------------------------
        "apparatus_provenance_commit": PROV.APPARATUS_PROVENANCE_COMMIT,
        "apparatus_provenance_commit_semantics": (
            "The commit that introduced the frozen Item 6 V5 point-in-time evidence apparatus "
            "(packet contract, materializer, frozen packet set, materialized request set, "
            "LIVE populated-packet binding). A historical fact about where the frozen "
            "scientific input came from. It is explicitly NOT a claim about the future "
            "execution HEAD and must never be used in place of human run-time authorization."),
        "source_head": PROV.APPARATUS_PROVENANCE_COMMIT,
        "source_head_semantics": (
            "Repository HEAD at manifest BUILD time (the parent of the commit that lands this "
            "manifest). Lineage: V2=b419f0827, V3=0fd5d418c, V4=a2c83d028. V5 recorded "
            "a2c83d028 because its builder copied V4's value instead of reading build-time "
            "HEAD; that was a copy defect, not a different semantic. V6 records the true "
            "build-time HEAD (45876df4d), which here coincides with "
            "apparatus_provenance_commit."),
        "exact_execution_head_source": PROV.EXACT_EXECUTION_HEAD_SOURCE,
        "external_authorized_head_required": True,
        "self_referential_execution_head_field_present": False,
        "self_referential_execution_head_removed": True,
        "removed_field_from_v5": {
            "field": "execution_head_expected",
            "v5_value": v5.get("execution_head_expected"),
            "why_removed": (
                "It named the PARENT commit (3dc1e4880), where neither the evidence apparatus "
                "nor the LIVE empty-packet firewall exists, so an executor honouring it would "
                "reproduce the very defect V5 closed. Substituting V6's own sha is impossible "
                "without circularity: the sha is not known until this manifest is committed, "
                "and a successor commit would stale it again."),
        },
        "execution_head_policy": {
            "exact_execution_head_source": PROV.EXACT_EXECUTION_HEAD_SOURCE,
            "authorized_head_parameter": "AUTHORIZED_EXECUTION_HEAD",
            "supplied_by": "the authorizing human at spend-authorization time",
            "verified_by": "src/research/item6/execution/live_driver.py::preflight",
            "verification_rule": (
                "git HEAD == AUTHORIZED_EXECUTION_HEAD, checked BEFORE any CountTokens or "
                "Converse call; missing, malformed or mismatched => LiveDriverRefused at zero "
                "spend."),
            "apparatus_commit_may_not_substitute": True,
            "manifest_may_not_self_declare_runtime_head": True,
            "do_not_amend_this_manifest_to_embed_its_own_commit": True,
        },

        # --- hash semantics (DEFECT 2 closed) -----------------------------------------------
        "hash_metadata_format": "PER_ARTIFACT_SCHEME_TAGGED_INDEX",
        "hash_schemes_explicit": True,
        "naive_hash_ambiguity_eliminated": True,
        "artifact_hash_index": artifact_hash_index,
        "artifact_hash_index_semantics": (
            "Authoritative artifact identity record. Every entry declares its own hash_scheme: "
            "RAW_FILE_SHA256 = sha256 of the committed file bytes; "
            "CANONICAL_JSON_EXCLUDING_SELF_HASH = sha256 of canonical JSON (sort_keys, compact "
            "separators, ensure_ascii=False, allow_nan=False) of the document with its own "
            "self_hash_field removed -- the identity the frozen packet provider and live "
            "driver verify. V5's mixed, untagged new_scientific_input_artifact_hashes dict is "
            "REMOVED in V6: verify with provenance.verify_manifest_artifacts, which fails "
            "closed on an unknown scheme or a scheme/method mismatch."),
        "artifact_hash_index_counts": {
            "RAW_FILE_SHA256": n_raw,
            "CANONICAL_JSON_EXCLUDING_SELF_HASH": n_canon,
            "UNKNOWN": 0,
        },
        "hash_verifier_path": PROVENANCE_SRC,
        "hash_verifier_version": PROV.ITEM6_PROVENANCE_VERSION,
        "hash_verifier_source_sha256": _sha(PROVENANCE_SRC),
        "v5_ambiguous_hash_dict_removed": "new_scientific_input_artifact_hashes",

        # --- scientific treatment: IDENTICAL to V5 ------------------------------------------
        "scientific_model_visible_request_changed": False,
        "model_visible_bytes_unchanged_vs_v5": True,
        "model_visible_change_reason": None,
        "scientific_treatment_identical_to_v5": True,
        "scientific_artifact_hashes": scientific_hashes,
        "scientific_artifact_paths": v5["scientific_artifact_paths"],
        "preexisting_scientific_artifacts_unchanged": True,
        "item6_research_question_unchanged": True,
        "mechanism_prompt_unchanged": True,
        "mechanism_schema_unchanged": True,
        "baseline_coverage_unchanged": True,
        "stage1_gate_unchanged": True,
        "stage1_gate_thresholds_unchanged": True,
        "stage1_cohort_unchanged": True,
        "new_scientific_input_artifacts_added": False,
        "new_scientific_input_artifact_paths": v5["new_scientific_input_artifact_paths"],
        "evidence_input": {
            **ev5,
            "unchanged_vs_v5": True,
            "evidence_packet_set_hash_scheme": CANON,
            "materialized_request_set_hash_scheme": CANON,
        },

        "execution_artifact_hashes": execution_hashes,
        "execution_artifact_paths": execution_paths,

        # model / profile / inference: UNCHANGED vs V5.
        "model_provider": v5["model_provider"],
        "model_profile_id": v5["model_profile_id"],
        "model_id": v5["model_id"],
        "inference_profile_arn": v5["inference_profile_arn"],
        "region": v5["region"],
        "inference_parameters": v5["inference_parameters"],
        "converse_model_identifier": v5["converse_model_identifier"],
        "count_tokens_model_identifier": v5["count_tokens_model_identifier"],

        "stage1_n_fixtures": v5["stage1_n_fixtures"],
        "k_mechanisms_per_fixture": v5["k_mechanisms_per_fixture"],
        "model_calls_per_fixture": v5["model_calls_per_fixture"],
        "one_response_contains_all_k": v5["one_response_contains_all_k"],
        "planned_primary_model_calls": v5["planned_primary_model_calls"],
        "retry_policy": v5["retry_policy"],
        "absolute_max_paid_calls": v5["absolute_max_paid_calls"],
        "absolute_max_model_attempts": v5["absolute_max_model_attempts"],

        "spend_control_version": v5["spend_control_version"],
        "runner_version": v5["runner_version"],
        "execution_status_version": v5["execution_status_version"],
        "token_counter_version": v5["token_counter_version"],
        "token_counter_code_path": v5["token_counter_code_path"],
        "token_counter_code_sha256": v5["token_counter_code_sha256"],
        "count_tokens_operation": v5["count_tokens_operation"],
        "count_tokens_request_construction": v5["count_tokens_request_construction"],

        "live_transport_version": v5["live_transport_version"],
        "live_transport_source_path": v5["live_transport_source_path"],
        "live_transport_source_sha256": _sha(v5["live_transport_source_path"]),
        "live_driver_version": "item6_stage1_live_driver_v3",
        "live_driver_source_path": LIVE_DRIVER_SRC,
        "live_driver_source_sha256": _sha(LIVE_DRIVER_SRC),
        "live_execution_contract": {
            **v5["live_execution_contract"],
            "requires_external_authorized_execution_head": True,
            "authorized_execution_head_verified_before_count_tokens": True,
            "apparatus_commit_may_not_substitute_for_authorization": True,
        },

        "aws_sdk_dependency_file": v5["aws_sdk_dependency_file"],
        "boto3_version": v5["boto3_version"],
        "botocore_version": v5["botocore_version"],
        "bedrock_runtime_has_converse": v5["bedrock_runtime_has_converse"],
        "bedrock_runtime_has_count_tokens": v5["bedrock_runtime_has_count_tokens"],
        "sdk_capability_asserted_from_service_model": True,
        "count_tokens_profile_compatibility_verified": True,

        "price_table_version": v5["price_table_version"],
        "input_price_usd_per_mtok": v5["input_price_usd_per_mtok"],
        "output_price_usd_per_mtok": v5["output_price_usd_per_mtok"],
        "max_request_utf8_bytes": v5["max_request_utf8_bytes"],
        "max_output_tokens_reserved": v5["max_output_tokens_reserved"],
        "worst_case_reservation": v5["worst_case_reservation"],
        "materialized_cost_diagnostics": cost,

        "spend_model": v5["spend_model"],

        "pass_b_policy": v5["pass_b_policy"],
        "stage2_activation": "BLOCKED_UNLESS_STAGE1_PASS",
        "champion_path": v5["champion_path"],
        "champion_sha256": _sha(v5["champion_path"]),
        "champion_independent": True,
        "runner_has_no_champion_dependency": True,

        "live_sonnet_generation_calls": 0,
        "bedrock_paid_inference_calls": 0,
        "new_paid_inference_spend_usd": 0,
        "live_sonnet_calls": 0,
        "bedrock_paid_calls": 0,
        "new_spend_usd": 0,
    }

    # HARD INVARIANTS on the composed manifest.
    assert PROV.SELF_REFERENTIAL_HEAD_FIELD not in manifest, "self-referential head field"
    assert manifest["champion_sha256"] == v5["champion_sha256"], "CHAMPION DRIFT vs V5"
    assert manifest["spend_model"]["human_authorized_monetary_ceiling_usd"] is None, \
        "ceiling must remain NOT_YET_AUTHORIZED"
    assert "new_scientific_input_artifact_hashes" not in manifest, \
        "the ambiguous mixed-scheme dict must not survive into V6"
    PROV.assert_execution_head_policy(manifest)
    report = PROV.verify_manifest_artifacts(manifest, root=ROOT)
    assert report["ok"], f"artifact index verification failed: {report['problems'][:5]}"

    manifest["run_manifest_sha256"] = hashlib.sha256(_canon(manifest)).hexdigest()
    with open(OUT, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"[run-manifest-v6] wrote {OUT}")
    print(f"[run-manifest-v6] ITEM6_STAGE1_RUN_MANIFEST_V6_SHA256="
          f"{manifest['run_manifest_sha256']}")
    print(f"[run-manifest-v6] apparatus_provenance_commit="
          f"{manifest['apparatus_provenance_commit']}")
    print(f"[run-manifest-v6] exact_execution_head_source="
          f"{manifest['exact_execution_head_source']}")
    print(f"[run-manifest-v6] artifact_hash_index: {n_raw} RAW_FILE_SHA256, "
          f"{n_canon} CANONICAL_JSON_EXCLUDING_SELF_HASH, 0 unknown")


if __name__ == "__main__":
    main()
