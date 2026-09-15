"""The frozen meaningful-multi-condition classifier, and the axis-metric gate. ZERO SPEND.

Both are preregistration artifacts: they are frozen BEFORE inference, so every one of the
ways a padded hypothesis could fake depth is pinned here as a test rather than decided
after seeing V3's output.
"""
from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import (availability, capability, condition_contract,
                                        lifecycle, multicondition, query_plan, schema_v2,
                                        validator, validator_v2, vocabulary)

PACKETS = ("/home/ubuntu/research/hypothesis_engine/out/"
           "MATERIALIZED_PACKETS_sonnet46_v2.json")
CUTOFF = 1776711600


@pytest.fixture(scope="module")
def packets():
    return json.load(open(PACKETS))


@pytest.fixture(scope="module")
def ontology(packets):
    """A real frozen fixture ontology: venue / competition / opponent_profile AVAILABLE,
    formation LOW_CONTRAST, score-state WITHHELD."""
    return availability.build_ontology(packets["reference::mt_010243938"])


def hyp(conditions, *, comparison="SUBJECT_OVERALL_BASELINE", metrics=("corners",),
        hid="H1", evidence_refs=()):
    return {
        "hypothesis_id": hid, "research_family": "OPPONENT_PROFILE_INTERACTION",
        "subject": "HOME_TEAM",
        "question": "Does the subject's rate in this cohort differ from its baseline?",
        "target_metrics": list(metrics), "side": "FOR", "window": "ALL_PRIOR",
        "conditions": list(conditions), "comparison": comparison,
        "evidence_refs": list(evidence_refs),
        "candidate_confounders": [], "required_capabilities": [],
        "sufficiency": "SUFFICIENT", "priority": "MEDIUM",
    }


def compiled_for(h, packet):
    cm = packet["capability_manifest"]
    manifest = capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        coverage=dict(cm.get("coverage") or {}))
    return [r.to_dict() for r in query_plan.compile_hypothesis(
        h, fixture_id=cm["fixture_id"], cutoff_unix=CUTOFF, manifest=manifest)]


# ======================================================================================
# The axis -> metric hole
# ======================================================================================
def test_the_axis_metric_hole_is_exactly_two_known_entries():
    """`PROFILE_AXES` claims every axis is a supported metric. Two entries are not.

    Pinned at LENGTH 2 so adding an axis to the vocabulary without adding its metric
    breaks this test instead of silently widening the hole.
    """
    assert condition_contract.unresolvable_axes() == ("shots_for", "shots_against")
    assert len(condition_contract.unresolvable_axes()) == 2
    assert len(condition_contract.resolvable_axes()) == len(vocabulary.PROFILE_AXES) - 2
    for axis in condition_contract.resolvable_axes():
        base = condition_contract.axis_base_metric(axis)
        assert base is not None and capability.metric(base) is not None, axis


def test_axis_base_metric_is_a_suffix_strip_not_a_last_underscore_split():
    assert condition_contract.axis_base_metric("total_bookings_for") == "total_bookings"
    assert condition_contract.axis_base_metric("shots_on_target_against") == "shots_on_target"
    assert condition_contract.axis_base_metric("accurate_crosses_for") == "accurate_crosses"
    # not well-formed: no orientation suffix at all
    assert condition_contract.axis_base_metric("possession") is None


def test_the_broken_axes_still_pass_the_frozen_compiler_which_is_why_gating_is_needed():
    """The compiler only checks membership in PROFILE_AXES, so it cannot catch this."""
    h = hyp([{"dimension": "opponent_profile", "value": "HIGH", "axis": "shots_for"}])
    results = query_plan.compile_hypothesis(h, fixture_id="mt_test", cutoff_unix=CUTOFF)
    assert all(r.ok for r in results), (
        "premise of the gate: the frozen compiler accepts an axis with no backing metric")


def test_gate_one_broken_axes_are_absent_from_the_exposed_condition_space(ontology):
    space = availability.fixture_condition_space(ontology)
    exposed = space["dimensions"]["opponent_profile"]["axes"]
    for axis in condition_contract.unresolvable_axes():
        assert axis not in exposed
    assert exposed, "gating must not empty the axis list"


def test_gate_two_a_broken_axis_is_rejected_at_validation_if_emitted_anyway(packets):
    """Exposure alone is not a contract."""
    packet = packets["reference::mt_010243938"]
    payload = {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
               "hypotheses": [hyp([{"dimension": "opponent_profile", "value": "HIGH",
                                    "axis": "shots_for"}],
                                  evidence_refs=[packet["evidence"][0]["id"]])]}
    res = validator_v2.validate(payload, packet=packet)
    assert res.accepted, "the response as a whole is structurally fine"
    assert res.n_accepted == 0, "but the hypothesis naming an unresolvable axis is rejected"
    assert res.verdicts[0].failure == lifecycle.UNSUPPORTED_CONTEXT_SOURCE
    assert any("shots_for" in r for r in res.verdicts[0].reasons)


def test_a_resolvable_axis_is_still_accepted(packets):
    packet = packets["reference::mt_010243938"]
    payload = {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
               "hypotheses": [hyp([{"dimension": "opponent_profile", "value": "HIGH",
                                    "axis": "corners_against"}],
                                  evidence_refs=[packet["evidence"][0]["id"]])]}
    res = validator_v2.validate(payload, packet=packet)
    assert res.n_accepted == 1, res.verdicts[0].reasons


def test_a_dimension_whose_every_axis_is_unresolvable_is_withheld_not_offered():
    """An axis-bearing dimension with no usable axis cannot express a cohort at all."""
    packet = {"fixture_id": "mt_x", "evidence": [],
              "capability_manifest": {"fixture_id": "mt_x",
                                      "available_metrics": ["corners"],
                                      "available_dimensions": ["opponent_profile", "venue"]}}
    ont = availability.build_ontology(packet)
    assert ont.dimensions["opponent_profile"].status == availability.AVAILABLE
    packet["capability_manifest"]["available_metrics"] = ["npxg"]   # no axis metric
    ont = availability.build_ontology(packet)
    assert ont.dimensions["opponent_profile"].status == availability.WITHHELD
    assert "opponent_profile" not in availability.fixture_condition_space(ont)["dimensions"]


# ======================================================================================
# The classifier: what must NOT qualify
# ======================================================================================
def test_len_two_is_not_the_definition_any_padding_does_not_qualify(ontology):
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "competition", "value": "ANY"}]), ontology)
    assert v.meaningful is False
    assert v.n_raw_conditions == 2 and v.n_restricting == 1
    assert any(multicondition.FEWER_THAN_TWO_LEGS in r for r in v.reasons)


def test_an_exact_duplicate_leg_does_not_qualify(ontology):
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "venue", "value": "HOME"}]), ontology)
    assert v.meaningful is False
    assert any(multicondition.DUPLICATE_LEG in r for r in v.reasons)


def test_an_aliased_duplicate_leg_does_not_qualify(ontology):
    """`home` and `HOME` canonicalize to one leg; the pair is not an interaction."""
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "home"},
             {"dimension": "venue", "value": "HOME"}]), ontology)
    assert v.meaningful is False
    assert v.n_restricting == 1


def test_contradictory_legs_on_one_dimension_do_not_qualify(ontology):
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "venue", "value": "AWAY"}]), ontology)
    assert v.meaningful is False
    assert any(multicondition.CONTRADICTORY_LEG in r for r in v.reasons)


def test_two_profile_conditions_on_the_same_axis_are_one_leg(ontology):
    v = multicondition.classify(
        hyp([{"dimension": "opponent_profile", "value": "HIGH", "axis": "corners_against"},
             {"dimension": "opponent_profile", "value": "LOW", "axis": "corners_against"}]),
        ontology)
    assert v.meaningful is False


def test_a_leg_on_a_withheld_dimension_does_not_qualify(ontology):
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "half_score_state", "value": "TRAILING_AT_HT"}]), ontology)
    assert v.meaningful is False
    assert any(multicondition.LEG_NOT_AVAILABLE in r for r in v.reasons)


def test_a_leg_on_a_low_contrast_dimension_does_not_qualify(ontology):
    """Formation with one observed family measures a cohort against itself."""
    assert ontology.dimensions["own_formation_family"].status == availability.LOW_CONTRAST
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "own_formation_family", "value": "BACK_FOUR"}]), ontology)
    assert v.meaningful is False
    assert any(multicondition.LEG_NOT_AVAILABLE in r for r in v.reasons)


def test_a_cohort_that_is_the_comparison_baseline_does_not_qualify(ontology):
    """venue=HOME compared against the subject's OWN VENUE baseline compares a cohort
    with itself -- the compiler accepts it happily, which is exactly why this check
    exists."""
    v = multicondition.classify(
        hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "competition", "value": "SAME"}],
            comparison="SUBJECT_VENUE_BASELINE"), ontology)
    assert v.meaningful is False
    assert any(multicondition.DEGENERATE_VS_COMPARISON in r for r in v.reasons)


def test_a_hypothesis_that_does_not_fully_compile_does_not_qualify(ontology, packets):
    """ALL plans must be ok -- the same numerator as compile_set's n_fully_compilable."""
    h = hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "opponent_profile", "value": "HIGH", "axis": "corners_against"}],
            metrics=("corners", "npxg"))
    h["conditions"].append({"dimension": "period", "value": "FIRST_HALF"})
    results = compiled_for(h, packets["reference::mt_010243938"])
    assert not all(r["ok"] for r in results), "premise: npxg has no half split"
    v = multicondition.classify(h, ontology, compile_results=results)
    assert v.meaningful is False
    assert any(multicondition.DOES_NOT_COMPILE in r for r in v.reasons)


# ======================================================================================
# The classifier: what MUST qualify
# ======================================================================================
def test_venue_by_opponent_profile_qualifies_on_a_real_frozen_ontology(ontology, packets):
    """The canonical positive case, on a real packet, against the OVERALL baseline.

    Guards the dimension-vs-comparison distinction: `SUBJECT_VENUE_BASELINE` is
    COMPILE_AVAILABLE_NO_EVIDENCE here, but the `venue` DIMENSION is AVAILABLE, and the
    classifier must read the dimension.
    """
    assert (ontology.comparisons["SUBJECT_VENUE_BASELINE"].status
            == availability.NO_EVIDENCE)
    assert ontology.dimensions["venue"].status == availability.AVAILABLE

    h = hyp([{"dimension": "venue", "value": "AWAY"},
             {"dimension": "opponent_profile", "value": "HIGH",
              "axis": "corners_against"}])
    results = compiled_for(h, packets["reference::mt_010243938"])
    v = multicondition.classify(h, ontology, compile_results=results)
    assert v.meaningful is True, v.reasons
    assert v.interaction_family == ("opponent_profile", "venue")


def test_two_profile_legs_on_different_axes_qualify(ontology, packets):
    h = hyp([{"dimension": "opponent_profile", "value": "HIGH", "axis": "corners_against"},
             {"dimension": "opponent_profile", "value": "LOW", "axis": "possession_for"}])
    results = compiled_for(h, packets["reference::mt_010243938"])
    v = multicondition.classify(h, ontology, compile_results=results)
    assert v.meaningful is True, v.reasons


def test_venue_by_competition_qualifies_against_the_overall_baseline(ontology, packets):
    h = hyp([{"dimension": "venue", "value": "HOME"},
             {"dimension": "competition", "value": "SAME"}])
    results = compiled_for(h, packets["reference::mt_010243938"])
    v = multicondition.classify(h, ontology, compile_results=results)
    assert v.meaningful is True, v.reasons


def test_alias_spelling_does_not_change_the_verdict(ontology, packets):
    a = hyp([{"dimension": "venue", "value": "away"},
             {"dimension": "opponent_profile", "value": "high",
              "axis": "CORNERS_AGAINST"}])
    b = hyp([{"dimension": "venue", "value": "AWAY"},
             {"dimension": "opponent_profile", "value": "HIGH",
              "axis": "corners_against"}])
    pkt = packets["reference::mt_010243938"]
    va = multicondition.classify(a, ontology, compile_results=compiled_for(b, pkt))
    vb = multicondition.classify(b, ontology, compile_results=compiled_for(b, pkt))
    assert va.meaningful is vb.meaningful is True
    assert va.legs == vb.legs


# ======================================================================================
# Against the frozen V2 replay -- the preregistered baseline
# ======================================================================================
def test_the_classifier_scores_zero_on_the_frozen_v2_reference_responses(packets):
    """V2's replayed outputs contain no meaningful multi-condition hypothesis.

    This is the preregistered BASELINE the V3 depth threshold is set against, computed
    with the frozen classifier before any V3 inference exists.
    """
    states = ("/home/ubuntu/research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/"
              "hypothesis_states.jsonl")
    total = 0
    meaningful = 0
    for line in open(states):
        if not line.strip():
            continue
        row = json.loads(line)
        if row["control"] != "reference":
            continue
        packet = packets[row["packet_key"]]
        cm = packet["capability_manifest"]
        manifest = capability.FixtureCapabilityManifest(
            fixture_id=cm["fixture_id"],
            available_metrics=tuple(cm["available_metrics"]),
            available_dimensions=tuple(cm["available_dimensions"]),
            coverage=dict(cm.get("coverage") or {}))
        ont = availability.build_ontology(packet, manifest)
        canon, _ = condition_contract.canonicalize_payload(row["raw_response"])
        for h in canon.get("hypotheses") or []:
            total += 1
            if multicondition.classify(h, ont).meaningful:
                meaningful += 1
    assert total > 100, total
    assert meaningful == 0, (
        f"V2 baseline must be zero meaningful multi-condition hypotheses, got {meaningful}")
