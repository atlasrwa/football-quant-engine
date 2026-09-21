"""Composed zero-spend authorization review for the Item 6 execution amendment.

Asserts every flag the mission's COMPOSED AUTHORIZATION REVIEW requires, reading the frozen
artifacts and module version stamps. No network, no model call.
"""
from __future__ import annotations

import json

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import runner as RUN
from src.research.item6.execution import spend_guard as SG

ROOT = "/home/ubuntu"


def _j(rel):
    return json.load(open(f"{ROOT}/{rel}"))


def test_composed_review_all_flags():
    cfg = _j("research/item6/ITEM6_STAGE1_EXECUTION_CONFIG_V1.json")
    manifest = _j("research/item6/ITEM6_STAGE1_RUN_MANIFEST_V1.json")
    reqset = _j("research/item6/out/execution/ITEM6_STAGE1_REQUEST_SET_V1.json")
    passb = _j("research/item6/ITEM6_STAGE1_PASS_B_POLICY_V1.json")

    review = {}

    # execution model + inference config frozen
    review["EXECUTION_MODEL_IDENTITY_FROZEN"] = (
        cfg["model_provider"] == "aws_bedrock"
        and cfg["model_profile_id"] == "us.anthropic.claude-sonnet-4-6"
        and cfg["model_id"] == "anthropic.claude-sonnet-4-6")
    review["EXECUTION_INFERENCE_CONFIG_FROZEN"] = (
        cfg["max_tokens"] == 8192 and cfg["temperature"] == 0.0
        and cfg["top_p_declared"] == 1.0 and cfg["top_p_on_wire"] is None
        and cfg["max_search_calls"] == 0 and cfg["network_search_enabled"] is False)

    # treatment unit
    review["ONE_CALL_PER_FIXTURE"] = cfg["model_calls_per_fixture"] == 1
    review["K_MECHANISMS_PER_CALL"] = cfg["k_mechanisms_per_fixture"] == 5
    review["MAX_RETRIES_PER_FIXTURE"] = ES.MAX_RETRIES_PER_FIXTURE == 0
    review["MAX_PAID_TREATMENTS_PER_FIXTURE"] = ES.MAX_PAID_TREATMENTS_PER_FIXTURE == 1
    review["ABSOLUTE_MAX_PAID_CALLS"] = ES.ABSOLUTE_MAX_PAID_CALLS == 120

    # attempt discipline
    review["ATTEMPT_MARKER_PRECEDES_TRANSMISSION"] = \
        cfg["attempt_marker_precedes_transmission"] is True
    review["UNCERTAIN_ATTEMPT_NOT_RETRIED"] = cfg["uncertain_attempt_not_retried"] is True

    # run manifest
    review["STAGE1_RUN_MANIFEST_EXISTS"] = bool(manifest.get("run_manifest_sha256"))
    review["RUN_MANIFEST_BINDS_ALL_SCIENTIFIC_IDENTITIES"] = all(
        k in manifest["scientific_artifact_hashes"] for k in
        ("research_protocol", "baseline_coverage_spec_md", "mechanism_prompt",
         "mechanism_schema_md", "baseline_equivalence_detector", "mechanism_formalizer",
         "quality_protocol_md", "stage1_gate_md", "power_cost", "cohort_manifest"))
    review["RUN_MANIFEST_BINDS_MODEL_CONFIG"] = (
        manifest["model_profile_id"] == "us.anthropic.claude-sonnet-4-6"
        and manifest["inference_parameters"]["max_tokens"] == 8192)
    review["RUN_MANIFEST_BINDS_RETRY_POLICY"] = (
        manifest["retry_policy"]["max_retries_per_fixture"] == 0)
    review["RUN_MANIFEST_BINDS_CALL_CAP"] = manifest["absolute_max_paid_calls"] == 120

    # request set
    review["REQUEST_SET_FROZEN"] = (
        reqset["n_fixtures"] == 120 and bool(reqset.get("request_set_sha256")))

    # spend
    review["PRECALL_SPEND_RESERVATION"] = SG.version_stamp()["precall_spend_reservation"]
    review["HARD_MONETARY_STOP"] = SG.version_stamp()["hard_monetary_stop"]
    review["ACTUAL_PROVIDER_USAGE_RECONCILED"] = hasattr(SG.SpendGuard, "reconcile")
    review["V3_STYLE_FIXED_PER_CALL_ACCOUNTING_ONLY"] = not (
        SG.version_stamp()["reservation_uses_input_byte_upper_bound"]
        and SG.version_stamp()["reservation_uses_frozen_max_output_tokens"])

    # pass B
    review["PASS_B_REQUIRED_FOR_PRIMARY_GATE"] = passb["pass_b_required_for_primary_gate"]
    review["PASS_B_EXECUTION_DEFERRED"] = passb["pass_b_execution_deferred"]
    review["PASS_B_REQUIRES_SEPARATE_AUTHORIZATION"] = \
        passb["pass_b_requires_separate_human_spend_authorization"]
    review["PRIMARY_GATE_COMPUTABLE_WITHOUT_PASS_B"] = \
        passb["primary_gate_computable_without_pass_b"]

    # firewall + integrity
    review["STAGE2_STILL_BLOCKED"] = manifest["stage2_activation"] == "BLOCKED_UNLESS_STAGE1_PASS"
    review["CHAMPION_UNCHANGED"] = (
        manifest["champion_sha256"]
        == "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9")
    review["RUNNER_NO_CHAMPION_DEPENDENCY"] = \
        RUN.version_stamp()["champion_dependency"] is False

    # zero spend
    review["LIVE_SONNET_CALLS_0"] = cfg["live_sonnet_calls"] == 0
    review["BEDROCK_PAID_CALLS_0"] = cfg["bedrock_paid_calls"] == 0
    review["NEW_SPEND_USD_0"] = cfg["new_spend_usd"] == 0

    # EVERY expected flag must be truthy. Note V3_STYLE... must be FALSE (we assert its
    # negation is False i.e. the value stored is False).
    expected_true = {k: v for k, v in review.items()
                     if k != "V3_STYLE_FIXED_PER_CALL_ACCOUNTING_ONLY"
                     and k != "PASS_B_REQUIRED_FOR_PRIMARY_GATE"}
    failures = [k for k, v in expected_true.items() if not v]
    assert not failures, f"composed-review flags failed: {failures}"
    assert review["V3_STYLE_FIXED_PER_CALL_ACCOUNTING_ONLY"] is False
    assert review["PASS_B_REQUIRED_FOR_PRIMARY_GATE"] is False

    # count: total flags evaluated
    assert len(review) == 29
