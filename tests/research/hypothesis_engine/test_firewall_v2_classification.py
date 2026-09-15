"""Numerical-authority firewall v2: the A / B / C classification. ZERO SPEND.

The task's requirement, restated as tests:

    A. a GENERATED effect / probability / advantage estimate  -> violation (blocking)
    B. a SUPPLIED evidence value copied into prose            -> tracked separately,
                                                                 STILL blocking
    C. metric names containing numerical-looking lexical material ("big_chances",
       "chances at")                                          -> must NOT trigger

The prohibition is not weakened anywhere: probabilities, estimated percentage effects,
odds, EV/edge, stakes and latent advantage grades must all still be caught.
"""
from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")

from research.hypothesis_engine import capability, firewall, firewall_v2

STATES = ("/home/ubuntu/research/hypothesis_engine/out/hypothesis_v1_sonnet46_v2/"
          "hypothesis_states.jsonl")
PACKETS = ("/home/ubuntu/research/hypothesis_engine/out/"
           "MATERIALIZED_PACKETS_sonnet46_v2.json")


def q(text):
    return {"fixture_id": "mt_test", "packet_hash": "0" * 64, "hypotheses": [{
        "hypothesis_id": "H1", "research_family": "ATTACK_VOLUME",
        "subject": "HOME_TEAM", "question": text, "target_metrics": ["corners"],
        "side": "FOR", "window": "ALL_PRIOR", "conditions": [],
        "comparison": "SUBJECT_OVERALL_BASELINE", "evidence_refs": [],
        "candidate_confounders": [], "required_capabilities": [],
        "sufficiency": "SUFFICIENT", "priority": "MEDIUM"}]}


def packet_with(*values):
    return {"evidence": [{"id": f"E{i}", "value": v, "sample_n": 40}
                         for i, v in enumerate(values)]}


# --------------------------------------------------------------------------------------
# Class C -- must NOT trigger
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Does the home team generate more big chances at home compared to its overall baseline?",
    "Does the away team concede fewer big chances at a rate below its overall baseline?",
    "Does the subject generate more big chances than its baseline across all prior matches?",
    "Does the subject's shots on target rate differ from its overall baseline?",
])
def test_class_c_metric_lexical_material_is_suppressed_not_violated(text):
    v1 = firewall.scan(q(text))
    got = firewall_v2.scan(q(text))
    assert firewall_v2.blocking(got) == [], f"v2 wrongly blocked: {[str(x) for x in got]}"
    if v1:
        # v1 false-positived; v2 must record it as suppressed instrumentation error.
        assert [x.cls for x in got] == [firewall_v2.CLASS_C] * len(got)


def test_big_chances_is_an_approved_metric_so_the_collision_is_instrumentation_error():
    assert "big_chances" in capability.metric_names()
    assert "big chances" in firewall_v2.metric_lexical_phrases()


def test_masking_is_generic_over_the_inventory_not_a_chances_at_special_case():
    """Any approved metric name is masked, so a future colliding metric is covered too."""
    for name in capability.metric_names():
        masked = firewall_v2.mask_metric_lexicon(f"Does the subject's {name} differ?")
        assert name.replace("_", " ") not in masked and name not in masked


# --------------------------------------------------------------------------------------
# Class B -- supplied value reproduced; separately tracked, STILL blocking
# --------------------------------------------------------------------------------------
def test_class_b_is_tracked_separately_and_still_blocks():
    text = ("Does the home team record lower possession per match compared to their "
            "opponents across all prior fixtures, given their possession-for average "
            "of 44.6% versus possession-against of 55.4%?")
    got = firewall_v2.scan(q(text), packet=packet_with(44.6103, 55.3897))
    assert len(got) == 1
    assert got[0].cls == firewall_v2.CLASS_B
    assert got[0].blocking is True
    assert got[0].evidence_resolved is True
    assert firewall_v2.CLASS_B in firewall_v2.BLOCKING_CLASSES


def test_class_b_requires_the_value_to_actually_be_in_the_packet():
    text = "Does the subject's possession share of 44.6% differ from its baseline?"
    got = firewall_v2.scan(q(text), packet=packet_with(12.0, 3.5))
    assert got[0].cls == firewall_v2.CLASS_A
    assert got[0].evidence_resolved is False


def test_a_bare_integer_does_not_resolve_against_a_rounded_evidence_value():
    """A round number is a domain constant, not a reproduced observation.

    "below 50%" must not be labelled a supplied-value copy merely because some unrelated
    evidence item happens to be 50.4552. It blocks either way; only the LABEL is at stake,
    and mislabelling a generated number as a copied one would understate class A.
    """
    got = firewall_v2.scan(
        q("Does the subject's possession share sit below 50% against its own baseline?"),
        packet=packet_with(50.4552))
    assert got[0].cls == firewall_v2.CLASS_A
    assert got[0].blocking is True


def test_no_packet_means_conservative_class_a():
    got = firewall_v2.scan(q("Does the subject's rate of 44.6% differ from baseline?"))
    assert got[0].cls == firewall_v2.CLASS_A


# --------------------------------------------------------------------------------------
# Class A -- the prohibition is NOT weakened
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Is there a 12.5% probability the subject exceeds its baseline corner rate?",
    "Does the subject hold an edge against the market baseline for corners?",
    "Should we back the over on the subject's corner count this fixture?",
    "Does the subject's rate justify a stake against its overall baseline?",
    "Is the fair odds of 1.85 justified by the subject's baseline corner rate?",
    "Does the subject produce +0.6 corners more than its overall baseline?",
    "Does the subject exceed over 2.5 relative to its own baseline?",
    "Does the expected value of this cohort exceed the subject's overall baseline?",
    "Is the subject's baseline shifted by 4 percentage points at home?",
])
def test_class_a_predictive_authority_is_still_blocked(text):
    got = firewall_v2.scan(q(text), packet=packet_with(1.85, 12.5, 0.6, 2.5, 4.0, 44.6))
    blocking = firewall_v2.blocking(got)
    assert blocking, f"v2 failed to block: {text!r}"
    assert firewall.scan(q(text)), "v1 must also have caught it -- v2 adds no leniency"


def test_structural_layers_are_reused_verbatim_and_always_class_a():
    payload = q("Does the subject's corner rate differ from its overall baseline?")
    payload["hypotheses"][0]["priority"] = "HIGH"
    payload["hypotheses"][0]["research_family"] = "ATTACK_VOLUME"
    # a number smuggled into a structural field
    bad = json.loads(json.dumps(payload))
    bad["hypotheses"][0]["question"] = "Does the subject's corner rate differ from baseline?"
    bad["schema_version_int"] = 2            # allow-listed, must NOT trip
    assert firewall_v2.blocking(firewall_v2.scan(bad)) == []

    bad2 = json.loads(json.dumps(payload))
    bad2["hypotheses"][0]["candidate_confounders"] = ["possession"]
    bad2["confidence"] = 0.82                # not allow-listed
    got = firewall_v2.blocking(firewall_v2.scan(bad2))
    assert got and all(v.cls == firewall_v2.CLASS_A for v in got)


def test_latent_advantage_grades_are_still_class_a_blocking():
    payload = q("Does the subject's corner rate differ from its overall baseline?")
    payload["hypotheses"][0]["research_family"] = "ATTACK_VOLUME"
    payload["matchup"] = "STRONG_A_ADVANTAGE"
    got = firewall_v2.blocking(firewall_v2.scan(payload))
    assert got and got[0].cls == firewall_v2.CLASS_A


# --------------------------------------------------------------------------------------
# Against the FROZEN V2 corpus -- the numbers the replay will report
# --------------------------------------------------------------------------------------
def test_frozen_v2_corpus_classification_is_exactly_as_diagnosed():
    packets = json.load(open(PACKETS))
    counts = {firewall_v2.CLASS_A: 0, firewall_v2.CLASS_B: 0, firewall_v2.CLASS_C: 0}
    v1_total = 0
    for line in open(STATES):
        if not line.strip():
            continue
        row = json.loads(line)
        raw = row.get("raw_response")
        if raw is None:
            continue
        v1_total += len(firewall.scan(raw))
        for v in firewall_v2.scan(raw, packet=packets.get(row["packet_key"])):
            counts[v.cls] += 1

    assert sum(counts.values()) == v1_total, (
        "v2 must find the same matches as v1 and differ only in classification")
    # every "chances at" hit is metric-lexical
    assert counts[firewall_v2.CLASS_C] == 24
    # the genuine Gate-E breach and its repeats survive as blocking
    assert counts[firewall_v2.CLASS_B] == 4
    assert counts[firewall_v2.CLASS_A] == 2
    assert counts[firewall_v2.CLASS_B] + counts[firewall_v2.CLASS_A] > 0, (
        "over-correction check: V2's genuine violation must NOT disappear")


def test_the_genuine_v2_gate_e_breach_still_blocks_under_v2():
    """seq03 reference mt_010243938 was the one true Gate-E failure. It must stay one."""
    packets = json.load(open(PACKETS))
    row = next(json.loads(l) for l in open(STATES)
               if l.strip() and json.loads(l)["seq"] == 3)
    got = firewall_v2.scan(row["raw_response"], packet=packets[row["packet_key"]])
    blocking = firewall_v2.blocking(got)
    assert len(blocking) == 1
    assert blocking[0].cls == firewall_v2.CLASS_B
    assert blocking[0].matched == "44.6%"


def test_a_match_containing_a_number_is_never_suppressed_as_metric_lexical():
    """Regression guard for an over-correction found while building this.

    `corners` is an approved metric name, so masking alone removed the
    `numeric_effect_size` match in "+0.6 corners" and the firewall stopped blocking a
    genuine effect-size claim. Class C is now defined as PURELY LEXICAL: a match carrying
    any numeric literal is classified A/B on the raw match, whatever the mask does to it.
    """
    for text in ("Does the subject produce +0.6 corners more than its overall baseline?",
                 "Does the subject take 1.3 more shots than its overall baseline?",
                 "Does the subject concede 2.4 fewer goals than its overall baseline?"):
        got = firewall_v2.scan(q(text))
        blocking = firewall_v2.blocking(got)
        assert blocking, f"suppressed a numeric effect claim: {text!r}"
        assert all(v.cls != firewall_v2.CLASS_C for v in got)
