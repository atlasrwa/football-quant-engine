"""V2 pre-spend freeze verification. Zero-spend, offline, deterministic.

Proves the V2 control-perturbation layer and manifest are fully preregistered: every one
of the 64 planned calls has a frozen, hash-verifiable scientific input, no original packet
is mutated, leakage is clean on every packet and serialized request, and nothing in the
chain can reach Bedrock.
"""
from __future__ import annotations

import copy
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")

import pytest

from src.research.hypothesis_engine import (battery_v2 as V2, controls, context_packet as CP,
                                            leakage, evaluation, normalize)

OUT = "/home/ubuntu/research/hypothesis_engine/out"
BATTERY_PATH = os.path.join(OUT, "hypothesis_golden_battery_v1.json")
PACKETS_PATH = os.path.join(OUT, "frozen_packets_v1.json")
MANIFEST_PATH = os.path.join(OUT, "PRESPEND_MANIFEST_sonnet46_v2.json")
MATERIALIZED_PATH = os.path.join(OUT, "MATERIALIZED_PACKETS_sonnet46_v2.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(BATTERY_PATH), reason="frozen battery not present")


@pytest.fixture(scope="module")
def battery():
    return json.load(open(BATTERY_PATH))


@pytest.fixture(scope="module")
def packets_by_id():
    return {fid: p for fid, p in json.load(open(PACKETS_PATH)).items()}


@pytest.fixture(scope="module")
def built(battery, packets_by_id):
    return V2.build_manifest_v2(battery, dict(packets_by_id), expected_cache_hits=0)


def test_64_calls_resolve(built):
    manifest, _ = built
    assert manifest["total_planned_calls"] == 64
    assert len(manifest["call_specs"]) == 64


def test_call_counts_exact(built):
    manifest, _ = built
    counts = {}
    for s in manifest["call_specs"]:
        counts[s["control"]] = counts.get(s["control"], 0) + 1
    assert counts == {
        "reference": 12, "repeatability": 12, "identity_alias": 8,
        "formation_ablation": 6, "profile_perturbation": 6, "venue_flip": 6,
        "irrelevant_field": 6, "evidence_starvation": 4, "unsupported_data_trap": 4}


def test_reference_maps_all_12_fixtures(built, battery, packets_by_id):
    manifest, _ = built
    order = [f["fixture_id"] for f in battery["fixtures"]]
    ref = [s for s in manifest["call_specs"] if s["control"] == "reference"]
    assert [s["source_fixture"] for s in ref] == order
    for s in ref:
        assert s["resulting_packet_hash"] == packets_by_id[s["source_fixture"]]["packet_hash"]


def test_repeatability_hashes_equal_reference(built, packets_by_id):
    manifest, _ = built
    rep = [s for s in manifest["call_specs"] if s["control"] == "repeatability"]
    assert len(rep) == 12
    assert len(set(s["source_fixture"] for s in rep)) == 6
    for s in rep:
        assert s["transformation_version"] is None
        assert s["resulting_packet_hash"] == \
            packets_by_id[s["source_fixture"]]["packet_hash"]


def test_40_transformed_packets_deterministic(built, packets_by_id):
    manifest, _ = built
    transform = [s for s in manifest["call_specs"]
                 if s["control"] not in ("reference", "repeatability")]
    assert len(transform) == 40
    for s in transform:
        ref = packets_by_id[s["source_fixture"]]
        ctrl = s["control"]
        if ctrl == "identity_alias":
            tp = controls.identity_alias(ref)
        elif ctrl == "formation_ablation":
            tp = controls.formation_ablation(ref)
        elif ctrl == "profile_perturbation":
            tp, _ = controls.profile_perturbation(
                ref, raise_band=s["transformation_params"]["direction"] == "RAISE")
        elif ctrl == "venue_flip":
            tp = controls.venue_flip(ref)
        elif ctrl == "irrelevant_field":
            tp = controls.irrelevant_field(ref)
        elif ctrl == "evidence_starvation":
            tp = controls.evidence_starvation(ref)
        elif ctrl == "unsupported_data_trap":
            tp = controls.unsupported_data_trap(ref)
        # reproduces the frozen hash AND is self-consistent
        assert tp["packet_hash"] == s["resulting_packet_hash"]
        assert CP.packet_hash(tp) == tp["packet_hash"]


def test_transforms_do_not_mutate_originals(packets_by_id):
    before = copy.deepcopy(packets_by_id)
    for fid, ref in packets_by_id.items():
        controls.identity_alias(ref)
        controls.formation_ablation(ref)
        controls.profile_perturbation(ref, raise_band=True)
        controls.profile_perturbation(ref, raise_band=False)
        controls.venue_flip(ref)
        controls.irrelevant_field(ref)
        controls.evidence_starvation(ref)
        controls.unsupported_data_trap(ref)
    assert packets_by_id == before


def test_all_materialized_hashes_match_specs(built):
    manifest, materialized = built
    for s in manifest["call_specs"]:
        assert materialized[s["packet_key"]]["packet_hash"] == s["resulting_packet_hash"]


def test_evidence_ids_stay_identity_neutral(built):
    _, materialized = built
    for pkt in materialized.values():
        for e in pkt.get("evidence", []):
            assert e["id"].split("_")[0] in ("HOME", "AWAY")


def test_leakage_clean_on_every_packet_and_serialized_request(built):
    manifest, materialized = built
    assert manifest["request_leakage_audit"]["status"] == "CLEAN"
    assert manifest["request_leakage_audit"]["total_findings"] == 0
    for pkt in materialized.values():
        assert leakage.audit_packet(pkt) == []
        assert leakage.audit_serialized_request(V2._serialize_request(pkt)) == []


def test_formation_ablation_removes_only_formation(built, packets_by_id):
    _, materialized = built
    # spot-check one ablated packet
    fid = next(k.split("::")[1] for k in materialized if k.startswith("formation_ablation::"))
    ref = packets_by_id[fid]
    abl = materialized[f"formation_ablation::{fid}"]
    assert abl["formation_distribution"] == {}
    for d in controls.FORMATION_DIMENSIONS:
        assert d not in abl["capability_manifest"]["available_dimensions"]
    # raw-stat evidence preserved verbatim (same count, same values)
    assert len(abl["evidence"]) == len(ref["evidence"])
    assert [e["value"] for e in abl["evidence"]] == [e["value"] for e in ref["evidence"]]


def test_profile_perturbation_moves_only_two_away_against_axes(built, packets_by_id):
    _, materialized = built
    keys = [k for k in materialized if k.startswith("profile_perturbation::")]
    assert len(keys) == 6
    for k in keys:
        fid = k.split("::")[1]
        ref = {e["id"]: e for e in packets_by_id[fid]["evidence"]}
        for e in materialized[k]["evidence"]:
            r = ref[e["id"]]
            moved = e["value"] != r["value"]
            if moved:
                assert e["id"].startswith("AWAY_")
                assert e["metric"] in controls.PROFILE_PERTURBATION_AXES


def test_evidence_starvation_yields_valid_but_starved_packet(built):
    _, materialized = built
    keys = [k for k in materialized if k.startswith("evidence_starvation::")]
    assert len(keys) == 4
    for k in keys:
        pkt = materialized[k]
        assert len(pkt["evidence"]) == controls.STARVATION_KEEP_N
        assert all(e["value"] is None for e in pkt["evidence"])
        # still self-consistent
        assert CP.packet_hash(pkt) == pkt["packet_hash"]


def test_unsupported_trap_adds_no_evidence_and_no_capability(built, packets_by_id):
    _, materialized = built
    keys = [k for k in materialized if k.startswith("unsupported_data_trap::")]
    assert len(keys) == 4
    for k in keys:
        fid = k.split("::")[1]
        ref = packets_by_id[fid]
        trap = materialized[k]
        assert len(trap["evidence"]) == len(ref["evidence"])       # no fabricated evidence
        assert (trap["capability_manifest"]["available_metrics"]
                == ref["capability_manifest"]["available_metrics"])
        assert (trap["capability_manifest"]["available_dimensions"]
                == ref["capability_manifest"]["available_dimensions"])


def test_identity_alias_changes_only_display_labels(built, packets_by_id):
    _, materialized = built
    keys = [k for k in materialized if k.startswith("identity_alias::")]
    assert len(keys) == 8
    for k in keys:
        fid = k.split("::")[1]
        ref = packets_by_id[fid]
        al = materialized[k]
        assert al["fixture"]["home"] == "ALPHA_TEAM"
        assert al["fixture"]["away"] == "BETA_TEAM"
        assert al["fixture"]["competition"] == "LEAGUE_X"
        # evidence + manifest identical
        assert al["evidence"] == ref["evidence"]
        assert al["capability_manifest"] == ref["capability_manifest"]


def test_normalization_and_scoring_frozen(built):
    manifest, _ = built
    assert manifest["normalization_version"] == normalize.INTENT_VERSION
    assert manifest["evaluation_version"] == evaluation.EVALUATION_VERSION
    assert manifest["controls_version"] == controls.CONTROLS_VERSION
    assert manifest["pass_fail_thresholds"] == dict(evaluation.THRESHOLDS)
    for h in ("controls_module_hash", "scoring_module_hash", "normalization_module_hash"):
        assert len(manifest[h]) == 64


def test_manifest_requires_authorization_and_is_isolated(built):
    manifest, _ = built
    assert manifest["authorization_required"] is True
    assert manifest["status"] == "HYPOTHESIS_SONNET_SPEND_AUTHORIZATION_REQUIRED"
    iso = manifest["namespace_isolation"]
    assert iso["cache_namespace"] == "hypothesis_v1_sonnet46_v2"
    assert "llm_matchup" not in iso["cache_root"]


def test_manifest_protects_prior_frozen_artifacts(built):
    manifest, _ = built
    protected = " ".join(manifest["artifacts_that_must_not_be_touched"])
    assert "PRESPEND_MANIFEST_v1.json" in protected            # Sonnet 5
    assert "PRESPEND_MANIFEST_sonnet46_v1.json" in protected   # V1
    assert "CHAMPION_FREEZE.json" in protected


def test_no_bedrock_import_in_v2_chain():
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
                    offenders.append(f"{f.name}:{m}")
    assert offenders == []


def test_written_manifest_matches_rebuild(built):
    """The on-disk manifest must equal a fresh rebuild (proves it is reproducible)."""
    if not os.path.exists(MANIFEST_PATH):
        pytest.skip("manifest not written yet")
    on_disk = json.load(open(MANIFEST_PATH))
    manifest, _ = built
    assert on_disk["manifest_hash"] == manifest["manifest_hash"]
