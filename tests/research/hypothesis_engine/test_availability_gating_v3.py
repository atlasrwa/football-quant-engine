"""Availability-gated research ontology. ZERO SPEND.

The rule under test, in both directions:

    A dimension may be REWARDED only where the packet genuinely offers it, and may NEVER
    be PENALISED where it does not. An unavailable dimension is EXCLUDED from the
    denominator, never scored as a zero.

The concrete V2 failure this prevents: `half_score_state` and `period` were withheld by
ALL TWELVE fixture manifests, yet v1's system prompt asserted in static text that half-time
score state "is available", and the evaluation had no notion of exclusion. Sonnet's
(correct) zero use of score-state was then readable as shallowness.
"""
from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import (availability, capability, normalize, prompt,
                                        prompt_v2, vocabulary)

PACKETS = ("/home/ubuntu/research/hypothesis_engine/out/"
           "MATERIALIZED_PACKETS_sonnet46_v2.json")


@pytest.fixture(scope="module")
def packets():
    return json.load(open(PACKETS))


@pytest.fixture(scope="module")
def reference_ontologies(packets):
    return {k: availability.build_ontology(p)
            for k, p in packets.items() if k.startswith("reference::")}


# --------------------------------------------------------------------------------------
# 1. Withheld dimensions are withheld -- and excluded, not zeroed
# --------------------------------------------------------------------------------------
def test_score_state_and_period_are_withheld_in_every_frozen_fixture(reference_ontologies):
    assert len(reference_ontologies) == 12
    for key, ont in reference_ontologies.items():
        for dim in ("half_score_state", "period"):
            assert ont.dimensions[dim].status == availability.WITHHELD, key
            assert not ont.dimensions[dim].selectable
            assert not ont.dimensions[dim].expectable


def test_a_withheld_dimension_is_excluded_from_the_denominator_not_scored_zero(
        reference_ontologies):
    """The whole point: `utilization` is None (excluded), never 0.0 (a failing score)."""
    ont = next(iter(reference_ontologies.values()))
    intents = [{"conditions": [{"dimension": "venue", "value": "HOME"}],
                "comparison": "SUBJECT_OVERALL_BASELINE"}]
    util = availability.depth_utilization(intents, ont)
    assert util["half_score_state"]["counted_in_denominator"] is False
    assert util["half_score_state"]["utilization"] is None
    assert util["venue"]["counted_in_denominator"] is True
    assert util["venue"]["utilization"] == 1.0


def test_abstaining_from_an_unavailable_dimension_costs_nothing(reference_ontologies):
    """Two responses identical except that one never mentions score-state must score the
    same on every gated depth reading."""
    ont = next(iter(reference_ontologies.values()))
    base = [{"conditions": [{"dimension": "venue", "value": "HOME"}],
             "comparison": "SUBJECT_OVERALL_BASELINE"}]
    a = availability.depth_utilization(base, ont)
    b = availability.depth_utilization(base, ont)
    assert a == b
    assert all(v["utilization"] is None
               for k, v in a.items() if not ont.dimensions[k].expectable)


def test_mentioning_an_unavailable_dimension_earns_no_depth_credit(reference_ontologies):
    ont = next(iter(reference_ontologies.values()))
    with_score_state = [{"conditions": [
        {"dimension": "venue", "value": "HOME"},
        {"dimension": "half_score_state", "value": "TRAILING_AT_HT"}],
        "comparison": "SUBJECT_OVERALL_BASELINE"}]
    util = availability.depth_utilization(with_score_state, ont)
    assert util["half_score_state"]["n_intents_using"] == 1
    assert util["half_score_state"]["utilization"] is None, (
        "using a withheld dimension must not become a depth score")


# --------------------------------------------------------------------------------------
# 2. Formation: coverage AND contrast
# --------------------------------------------------------------------------------------
def test_formation_is_gated_by_manifest_coverage(reference_ontologies):
    withheld = {k for k, o in reference_ontologies.items()
                if o.dimensions["own_formation_family"].status == availability.WITHHELD}
    assert len(withheld) == 3, sorted(withheld)


def test_formation_with_a_single_observed_family_is_low_contrast_not_available(
        reference_ontologies):
    """25% coverage of one single family is not a measurable interaction."""
    ont = reference_ontologies["reference::mt_013233190"]
    d = ont.dimensions["own_formation_family"]
    assert d.status == availability.LOW_CONTRAST
    assert d.selectable is True, "the model may still choose it"
    assert d.expectable is False, "but depth must not be scored on it"


def test_formation_is_genuinely_expectable_in_only_a_minority_of_fixtures(
        reference_ontologies):
    expectable = {k for k, o in reference_ontologies.items()
                  if o.is_expectable("own_formation_family")}
    assert len(expectable) == 3, sorted(expectable)


# --------------------------------------------------------------------------------------
# 3. Horizon comparison needs BOTH horizons in evidence
# --------------------------------------------------------------------------------------
def test_recent_vs_long_needs_two_horizons_and_the_packets_supply_one(
        reference_ontologies):
    for key, ont in reference_ontologies.items():
        assert ont.evidence_windows == ("ALL_PRIOR",), key
        c = ont.comparisons["SUBJECT_RECENT_VS_LONG_BASELINE"]
        assert c.status == availability.NO_EVIDENCE, key
        assert not c.expectable


def test_recent_vs_long_becomes_available_when_both_horizons_are_present(packets):
    packet = json.loads(json.dumps(packets["reference::mt_010243515"]))
    extra = json.loads(json.dumps(packet["evidence"][0]))
    extra["id"] = "W5_SYNTHETIC"
    extra["scope"]["window"] = "W5"
    packet["evidence"].append(extra)
    ont = availability.build_ontology(packet)
    assert ont.evidence_windows == ("ALL_PRIOR", "W5")
    assert ont.comparisons["SUBJECT_RECENT_VS_LONG_BASELINE"].status == availability.AVAILABLE


def test_league_environment_baseline_has_no_supporting_evidence_in_these_packets(
        reference_ontologies):
    for key, ont in reference_ontologies.items():
        assert ont.comparisons["LEAGUE_ENVIRONMENT_BASELINE"].status == availability.NO_EVIDENCE


# --------------------------------------------------------------------------------------
# 4. Exposure: withheld dimensions are ABSENT from what the model is shown
# --------------------------------------------------------------------------------------
def test_the_exposed_condition_space_omits_withheld_dimensions_entirely(
        reference_ontologies):
    for key, ont in reference_ontologies.items():
        space = availability.fixture_condition_space(ont)
        for dim in ont.withheld_dimensions():
            assert dim not in space["dimensions"], key


def test_the_exposed_space_values_are_the_canonical_uppercase_tokens(
        reference_ontologies):
    ont = next(iter(reference_ontologies.values()))
    space = availability.fixture_condition_space(ont)
    assert space["dimensions"]["venue"]["values"] == list(vocabulary.VENUE_VALUES)
    assert space["dimensions"]["opponent_profile"]["axis_required"] is True


def test_prompt_v2_user_message_never_names_a_withheld_dimension(packets,
                                                                reference_ontologies):
    for key, ont in reference_ontologies.items():
        msg = prompt_v2.build_user_message(packets[key], ont)
        for dim in ont.withheld_dimensions():
            if dim == "referee":
                continue                      # not in the manifest's vocabulary surface
            assert dim not in msg, f"{key}: {dim} named in the user message"


def test_prompt_v1_asserted_score_state_availability_and_prompt_v2_does_not():
    """The static-text availability lie, pinned as a regression."""
    v1 = prompt.system_prompt()
    assert "Half-time score state" in v1 and "is available" in v1
    v2 = prompt_v2.system_prompt()
    assert "half-time score state" not in v2.lower()
    for dim in vocabulary.DIMENSIONS:
        assert dim not in v2 or dim in ("venue", "competition", "opponent_profile"), dim
    # and no dimension is asserted AVAILABLE in static text
    assert "is available" not in v2


def test_prompt_v2_states_the_casing_contract_and_the_axis_requirement():
    v2 = prompt_v2.system_prompt()
    assert "UPPERCASE TOKENS" in v2
    assert "HOME, not" in v2
    assert "`axis` is REQUIRED" in v2
    assert "ANY places no restriction" in v2


def test_prompt_v2_gives_a_structural_evidence_reference_channel():
    v2 = prompt_v2.system_prompt()
    assert "evidence_refs" in v2
    assert "never the figure" in v2


def test_prompt_v2_worked_examples_name_no_team_metric_or_football_story():
    """Anti-circularity: the grammar examples must not encode our preferred hypotheses."""
    v2 = prompt_v2.system_prompt()
    examples = v2.split("CONDITION GRAMMAR")[1]
    for metric in capability.metric_names():
        assert metric not in examples, f"grammar example names the metric {metric}"
    for family in vocabulary.RESEARCH_FAMILIES:
        assert family not in examples
    assert "conditions\": []" in examples, (
        "the unconditional shape must be shown as a first-class option")


def test_prompt_v2_permits_a_plain_baseline_answer():
    v2 = prompt_v2.system_prompt()
    assert "correct and complete answer" in v2
    assert "Returning an EMPTY set of hypotheses is the right answer" in v2


# --------------------------------------------------------------------------------------
# 5. Restraint: gratuitous complexity is measured, not rewarded
# --------------------------------------------------------------------------------------
def test_any_padded_conditions_count_as_gratuitous_not_as_depth(reference_ontologies):
    ont = next(iter(reference_ontologies.values()))
    payload = {"hypotheses": [{
        "hypothesis_id": "H1",
        "conditions": [{"dimension": "venue", "value": "HOME"},
                       {"dimension": "competition", "value": "ANY"}]}]}
    r = availability.restraint_profile(payload, ont)
    assert r["any_padding_conditions"] == 1
    assert r["interaction_rate"] == 0.0, "ANY padding must not read as an interaction"
    assert r["gratuitous_condition_rate"] == 0.5


def test_conditions_on_withheld_dimensions_count_as_gratuitous(reference_ontologies):
    ont = next(iter(reference_ontologies.values()))
    payload = {"hypotheses": [{
        "hypothesis_id": "H1",
        "conditions": [{"dimension": "venue", "value": "HOME"},
                       {"dimension": "half_score_state", "value": "TRAILING_AT_HT"}]}]}
    r = availability.restraint_profile(payload, ont)
    assert r["conditions_on_withheld_dimensions"] == 1
    assert r["interaction_rate"] == 1.0
    assert r["justified_interaction_rate"] == 0.0, (
        "an interaction with an impossible leg is not a justified interaction")


def test_a_justified_interaction_uses_two_expectable_dimensions(reference_ontologies):
    ont = next(iter(reference_ontologies.values()))
    payload = {"hypotheses": [{
        "hypothesis_id": "H1",
        "conditions": [{"dimension": "venue", "value": "AWAY"},
                       {"dimension": "opponent_profile", "value": "HIGH",
                        "axis": "corners_against"}]}]}
    r = availability.restraint_profile(payload, ont)
    assert r["justified_interaction_rate"] == 1.0
    assert r["gratuitous_condition_rate"] == 0.0


def test_restraint_reads_raw_hypotheses_because_normalization_drops_any(
        reference_ontologies):
    """`normalize` drops ANY conditions (correct for identity), which would hide padding."""
    payload = {"hypotheses": [{
        "hypothesis_id": "H1", "research_family": "VENUE_EFFECT", "subject": "HOME_TEAM",
        "target_metrics": ["corners"], "side": "FOR", "window": "ALL_PRIOR",
        "comparison": "SUBJECT_OVERALL_BASELINE", "sufficiency": "SUFFICIENT",
        "conditions": [{"dimension": "venue", "value": "ANY"}]}]}
    assert normalize.normalize_set(payload)[0].conditions == ()
    ont = next(iter(reference_ontologies.values()))
    assert availability.restraint_profile(payload, ont)["any_padding_conditions"] == 1
