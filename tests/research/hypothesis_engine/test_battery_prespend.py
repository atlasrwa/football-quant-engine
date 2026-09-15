"""Mandate §26, §30 -- the frozen battery and the pre-spend manifest.

These tests assert that the battery is real, stratified, leak-clean and reproducible, and
that the spend path is CLOSED until authorized.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

from src.research.hypothesis_engine import battery as B, leakage, schema, validator

BATTERY_PATH = "/home/ubuntu/research/hypothesis_engine/out/hypothesis_golden_battery_v1.json"
PACKETS_PATH = "/home/ubuntu/research/hypothesis_engine/out/frozen_packets_v1.json"
MANIFEST_PATH = "/home/ubuntu/research/hypothesis_engine/out/PRESPEND_MANIFEST_v1.json"

pytestmark = pytest.mark.skipif(
    not os.path.exists(BATTERY_PATH),
    reason="frozen battery not present in this checkout")


@pytest.fixture(scope="module")
def bat():
    return json.load(open(BATTERY_PATH))


@pytest.fixture(scope="module")
def packets():
    return json.load(open(PACKETS_PATH))


@pytest.fixture(scope="module")
def manifest():
    return json.load(open(MANIFEST_PATH))


# ================================================================== battery is real
def test_battery_is_stratified_across_the_mandated_dimensions(bat):
    assert bat["n_fixtures"] >= 12
    covered = set(bat["strata_covered"])
    for required in ("FORMATION_RICH", "FORMATION_SPARSE", "THIN_HISTORY",
                     "HIGH_CORNER_PROFILE", "LOW_CORNER_PROFILE",
                     "HIGH_CARD_PROFILE", "HIGH_SHOT_VOLUME"):
        assert required in covered, f"battery misses stratum {required}"


def test_every_frozen_packet_is_leak_clean(packets):
    for fid, p in packets.items():
        assert leakage.audit_packet(p) == [], f"{fid} leaks"


def test_every_frozen_packet_is_serialization_clean(packets):
    for fid, p in packets.items():
        assert leakage.audit_serialized_request(json.dumps(p, default=str)) == [], fid


def test_packet_hashes_match_their_content(packets, bat):
    from src.research.hypothesis_engine import context_packet as CP
    by_id = {f["fixture_id"]: f["packet_hash"] for f in bat["fixtures"]}
    for fid, p in packets.items():
        assert CP.packet_hash(p) == p["packet_hash"], f"{fid} self-hash mismatch"
        assert by_id[fid] == p["packet_hash"], f"{fid} battery/packet hash mismatch"


def test_packets_carry_real_evidence_and_a_capability_manifest(packets):
    for fid, p in packets.items():
        assert len(p["evidence"]) >= 40, fid
        man = p["capability_manifest"]
        assert len(man["available_metrics"]) >= 15, fid
        assert man["available_dimensions"], fid
        assert man["unsupported_context"], "the model must always be told what is missing"
        assert all(e["temporal_status"] == "PIT_SAFE" for e in p["evidence"]), fid


def test_evidence_ids_are_identity_neutral(packets):
    """No club or competition name may appear in an evidence id, or the identity control
    is confounded before it starts."""
    for fid, p in packets.items():
        for e in p["evidence"]:
            assert e["id"].split("_")[0] in ("HOME", "AWAY"), e["id"]
        assert p["fixture"]["home"] == "HOME_TEAM"
        assert p["fixture"]["away"] == "AWAY_TEAM"


def test_battery_hash_is_content_addressed(bat):
    from src.research.hypothesis_engine import lifecycle as L
    recomputed = L.stable_hash({k: v for k, v in bat.items()
                                if k not in ("battery_hash", "written_to")})
    assert recomputed == bat["battery_hash"]


def test_battery_pins_the_exact_contract_it_will_be_run_under(bat):
    assert bat["schema_content_hash"] == schema.schema_content_hash()
    for key in ("schema_version", "vocabulary_version", "capability_inventory_version",
                "prompt_version", "prompt_content_hash", "generation_id"):
        assert bat[key], f"battery must pin {key}"


# ================================================================== manifest completeness
@pytest.mark.parametrize("key", [
    "model_id", "prompt_version", "schema_version", "n_fixtures",
    "calls_per_fixture_by_control", "total_planned_calls", "expected_cache_hits",
    "expected_new_paid_calls", "token_and_cost_estimate", "frozen_fixtures",
    "planned_controls", "scoring_rubric", "pass_fail_thresholds",
    "request_leakage_audit", "namespace_isolation", "artifacts_to_be_written",
])
def test_manifest_answers_every_mandated_question(manifest, key):
    assert key in manifest and manifest[key] not in (None, "", [], {})


def test_manifest_reports_packet_hashes_for_every_fixture(manifest, bat):
    assert len(manifest["frozen_fixtures"]) == bat["n_fixtures"]
    for f in manifest["frozen_fixtures"]:
        assert len(f["packet_hash"]) == 64


def test_manifest_leak_audit_is_clean(manifest):
    assert manifest["request_leakage_audit"]["status"] == "CLEAN"
    assert manifest["request_leakage_audit"]["total_findings"] == 0


def test_manifest_arithmetic_is_consistent(manifest):
    assert manifest["total_planned_calls"] == sum(
        manifest["planned_calls_by_control"].values())
    assert manifest["expected_new_paid_calls"] == (
        manifest["total_planned_calls"] - manifest["expected_cache_hits"])
    e = manifest["token_and_cost_estimate"]
    assert e["total_input_tokens"] == (
        manifest["expected_new_paid_calls"] * e["mean_input_tokens_per_call"])
    expected = (e["total_input_tokens"] / 1000 * e["price_per_1k_input_usd"]
                + e["total_output_tokens"] / 1000 * e["price_per_1k_output_usd"])
    assert abs(e["estimated_cost_usd"] - expected) < 0.01


def test_manifest_labels_its_estimate_as_an_estimate(manifest):
    assert "ESTIMATE" in manifest["token_and_cost_estimate"]["note"]


def test_manifest_isolates_its_cache_from_the_legacy_generation(manifest):
    iso = manifest["namespace_isolation"]
    assert iso["separate_from_legacy"] is True
    assert "hypothesis" in iso["cache_root"]
    assert "llm_matchup" not in iso["cache_root"]
    for legacy in iso["legacy_namespaces_untouched"]:
        assert "llm_matchup" in legacy


def test_manifest_protects_the_champion_and_the_legacy_artifacts(manifest):
    protected = " ".join(manifest["artifacts_that_must_not_be_touched"])
    assert "CHAMPION_FREEZE.json" in protected
    assert "llm_matchup" in protected
    assert "data/forward" in protected
    assert "data/prospective" in protected


def test_manifest_writes_nothing_outside_its_own_namespace(manifest):
    for path in manifest["artifacts_to_be_written"]:
        assert "/research/hypothesis_engine/out/" in path
        assert "llm_matchup" not in path


def test_thresholds_are_carried_into_the_manifest(manifest):
    from src.research.hypothesis_engine import evaluation as E
    assert manifest["pass_fail_thresholds"] == E.THRESHOLDS
    assert manifest["pass_fail_thresholds"]["max_numerical_authority_violations"] == 0
    assert "Fail closed" in manifest["gate_policy"]


# ========================================================================= spend is closed
def test_manifest_requires_authorization(manifest):
    assert manifest["authorization_required"] is True
    assert manifest["status"] == "HYPOTHESIS_SONNET_SPEND_AUTHORIZATION_REQUIRED"


def test_battery_module_exposes_no_execution_entry_point():
    """The absence of a runner is part of the guarantee, not an oversight."""
    for name in ("run", "execute", "run_battery", "call", "invoke", "submit"):
        assert not hasattr(B, name), f"battery.{name} would be a spend path"


def test_no_module_in_the_package_can_reach_bedrock():
    """Nothing in the hypothesis engine imports boto3 or any Bedrock client."""
    import ast
    import pathlib

    root = pathlib.Path("/home/ubuntu/src/research/hypothesis_engine")
    offenders = []
    for f in sorted(root.rglob("*.py")):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m.split(".")[0] in ("boto3", "botocore"):
                    offenders.append(f"{f.name} imports {m}")
    assert offenders == [], (
        "the zero-spend implementation must not be able to make a paid call:\n"
        + "\n".join(offenders))
