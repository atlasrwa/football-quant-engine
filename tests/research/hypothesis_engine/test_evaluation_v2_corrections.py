"""Evaluation-battery v2: the two corrected scoring DEFINITIONS. ZERO SPEND.

Neither correction lowers a bar. `evaluation_v2.THRESHOLDS` is `evaluation.THRESHOLDS`
verbatim; what changes is that two metrics now measure what they claim to measure.
"""
from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import (availability, capability, evaluation,
                                        evaluation_v2, firewall_v2, lifecycle)

PACKETS = ("/home/ubuntu/research/hypothesis_engine/out/"
           "MATERIALIZED_PACKETS_sonnet46_v2.json")


def test_no_threshold_is_moved():
    assert evaluation_v2.THRESHOLDS == evaluation.THRESHOLDS


# --------------------------------------------------------------------------------------
# Correction 1 -- an empty hypothesis set is FULL abstention
# --------------------------------------------------------------------------------------
def test_empty_hypothesis_set_is_full_abstention_not_zero():
    """V2 mapped the single most correct answer to a starved packet to the worst score."""
    empty = {"fixture_id": "f", "packet_hash": "0" * 64, "hypotheses": []}
    assert evaluation_v2.abstention_quality(empty) == 1.0
    assert evaluation_v2.abstained(empty) is True

    # the v1 definition, reproduced here to pin exactly what was wrong
    hyps = empty["hypotheses"]
    v1_rate = (sum(1 for h in hyps if h.get("sufficiency") == "INSUFFICIENT_EVIDENCE")
               / len(hyps)) if hyps else 0.0
    assert v1_rate == 0.0


def test_explicit_abstentions_still_count_normally():
    payload = {"hypotheses": [
        {"sufficiency": "INSUFFICIENT_EVIDENCE"},
        {"sufficiency": "INSUFFICIENT_EVIDENCE"},
        {"sufficiency": "SUFFICIENT"},
    ]}
    assert evaluation_v2.abstention_quality(payload) == pytest.approx(2 / 3)
    assert evaluation_v2.abstained(payload) is True


def test_inventing_on_a_starved_packet_still_fails_abstention():
    """The correction must not let a genuinely bad response through."""
    payload = {"hypotheses": [{"sufficiency": "SUFFICIENT"} for _ in range(12)]}
    assert evaluation_v2.abstention_quality(payload) == 0.0
    assert evaluation_v2.abstained(payload) is False


def test_a_missing_hypotheses_key_is_not_silently_full_abstention():
    assert evaluation_v2.abstention_quality({}) == 0.0
    assert evaluation_v2.abstention_quality("not a dict") == 0.0


# --------------------------------------------------------------------------------------
# Correction 2 -- invariance is relative to the measured same-input noise floor
# --------------------------------------------------------------------------------------
def test_invariance_is_judged_against_the_generators_own_repeatability_floor():
    """V2 required Jaccard >= 0.80 while the same-input floor measured 0.333.

    A gate above the noise floor measures sampling noise, not identity sensitivity.
    """
    absolute_bar = evaluation.THRESHOLDS["min_identity_intent_jaccard"]
    measured_floor = 0.333
    assert measured_floor < absolute_bar, "the premise of the correction"

    # identity swap moves intent no more than a same-input rerun does -> passes
    rel = evaluation_v2.relative_invariance(0.46, measured_floor)
    assert rel["passed"] is True
    assert rel["ratio"] > 1.0

    # identity swap collapses intent far below the floor -> still fails
    rel = evaluation_v2.relative_invariance(0.10, measured_floor)
    assert rel["passed"] is False


def test_an_unmeasured_floor_is_none_not_a_pass():
    assert evaluation_v2.relative_invariance(0.9, None)["passed"] is None
    assert evaluation_v2.relative_invariance(None, 0.5)["passed"] is None


def test_a_generator_that_cannot_reproduce_itself_yields_no_invariance_claim():
    rel = evaluation_v2.relative_invariance(0.0, 0.0)
    assert rel["passed"] is None
    assert "above noise" in rel["note"]


def test_an_unmeasured_gate_is_not_a_pass():
    report = evaluation_v2.aggregate([evaluation_v2.FixtureScoreV2("f", True)])
    assert report.discipline_gates["I_identity_robustness_relative"] is None
    assert report.passed is False, "fail closed: an unmeasured gate is NOT a pass"


# --------------------------------------------------------------------------------------
# Gate E keeps zero tolerance; only class C is excluded
# --------------------------------------------------------------------------------------
def test_gate_e_zero_tolerance_is_preserved_for_class_a_and_class_b():
    assert evaluation_v2.THRESHOLDS["max_numerical_authority_violations"] == 0
    for cls in (firewall_v2.CLASS_A, firewall_v2.CLASS_B):
        s = evaluation_v2.FixtureScoreV2("f", True, n_blocking_violations=1,
                                         firewall_classes={cls: 1})
        report = evaluation_v2.aggregate([s])
        assert report.discipline_gates["E_numerical_authority"] is False, cls


def test_gate_e_is_not_tripped_by_a_suppressed_class_c_finding():
    s = evaluation_v2.FixtureScoreV2(
        "f", True, n_blocking_violations=0, n_suppressed_violations=3,
        firewall_classes={firewall_v2.CLASS_C: 3})
    report = evaluation_v2.aggregate([s])
    assert report.discipline_gates["E_numerical_authority"] is True


# --------------------------------------------------------------------------------------
# Depth and restraint are REPORTED, never gated
# --------------------------------------------------------------------------------------
def test_depth_and_restraint_are_not_gates():
    report = evaluation_v2.aggregate([evaluation_v2.FixtureScoreV2("f", True)])
    gate_names = set(report.discipline_gates)
    for forbidden in ("depth", "restraint", "interaction", "utilization"):
        assert not any(forbidden in g.lower() for g in gate_names)
    assert "availability_gated_dimension_utilization" in report.depth_report
    assert "mean_interaction_rate" in report.restraint_report


def test_scoring_a_frozen_v2_response_gates_depth_on_availability():
    """End-to-end on a real frozen packet + response: score, and check the gating."""
    packets = json.load(open(PACKETS))
    states = ("/home/ubuntu/research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/"
              "hypothesis_states.jsonl")
    # seq 1 (mt_012232295) carries the class-C "big chances at" collision that killed it
    # under firewall v1, and no contract-invalid condition, so it exercises the full path.
    row = next(json.loads(l) for l in open(states)
               if l.strip() and json.loads(l)["seq"] == 1)
    packet = packets[row["packet_key"]]
    cm = packet["capability_manifest"]
    manifest = capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()))

    score = evaluation_v2.score_response(row["raw_response"], packet=packet,
                                         manifest=manifest)
    util = score.depth["dimension_utilization"]
    assert util["half_score_state"]["counted_in_denominator"] is False
    assert util["half_score_state"]["utilization"] is None
    assert "half_score_state" in score.depth["excluded_dimensions"]
    # the class-C false positive that killed responses under v1 does not block here
    assert score.firewall_classes.get(firewall_v2.CLASS_C, 0) >= 1
    assert score.n_blocking_violations == 0
    assert score.whole_response_failure is None


def test_a_contract_invalid_condition_rejects_the_whole_response_under_schema_v2():
    """Documented, deliberate STRICTNESS -- and a live measurement risk.

    schema-v2 closes `conditions[].value` and requires `axis` for `opponent_profile`, and
    the package's no-salvage rule rejects a response WHOLE on any schema error. One
    malformed condition therefore costs the entire response.

    Recomputed over the frozen V2 reference set, 5 of 12 responses carry at least one
    contract-invalid condition (3 x opponent_profile with no axis, 1 x `high_possession`
    as a band, 1 x `competition = COMPETITION`), so under schema-v2 those 5 would have
    been rejected outright rather than losing one hypothesis each.

    This is pinned as a test because it is the main residual risk in the corrected
    apparatus, not because it is the desired outcome: in a real V3 run the model is SHOWN
    this schema in the tool spec, which V2's model never was.
    """
    packets = json.load(open(PACKETS))
    states = ("/home/ubuntu/research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/"
              "hypothesis_states.jsonl")
    row = next(json.loads(l) for l in open(states)
               if l.strip() and json.loads(l)["seq"] == 0)
    packet = packets[row["packet_key"]]
    score = evaluation_v2.score_response(row["raw_response"], packet=packet)
    assert score.whole_response_failure == lifecycle.SCHEMA_INVALID
    assert score.depth == {}
    # the contract said precisely why, before the schema ever ran
    reasons = {f["reason"]
               for fails in score.canonicalization["failures"].values()
               for f in fails}
    assert reasons <= {"MISSING_AXIS", "UNKNOWN_VALUE"}
    assert reasons
