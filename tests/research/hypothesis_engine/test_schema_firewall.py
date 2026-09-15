"""Mandate §23 -- schema + numerical-authority firewall gates.

Every rejection here must be WHOLE-RESPONSE (no salvage): a model that emitted predictive
authority anywhere is not trusted anywhere.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import firewall, lifecycle, validator, vocabulary


@pytest.fixture()
def packet():
    return F.real_identity_packet()


@pytest.fixture()
def response(packet):
    return F.valid_response(packet)


def _validate(resp, packet):
    return validator.validate(resp, packet=packet,
                              expected_packet_hash=packet["packet_hash"],
                              expected_fixture_id=packet["fixture_id"])


# --------------------------------------------------------------------------- happy path
def test_valid_question_accepted(packet, response):
    r = _validate(response, packet)
    assert r.accepted, r.reasons
    assert r.n_accepted == 4
    assert all(v.accepted for v in r.verdicts)


def test_no_firewall_violation_on_a_clean_response(response):
    assert firewall.scan(response) == []


def test_abstention_is_accepted_not_punished(packet):
    r = _validate(F.abstention_response(packet), packet)
    assert r.accepted
    assert r.n_accepted == 1, "an honest abstention is a valid output, not a failure"


# ------------------------------------------------------------------ numerical authority
@pytest.mark.parametrize("field_name,value", [
    ("probability", 0.617),
    ("model_probability", 0.61),
    ("expected_probability", 0.5),
    ("probability_adjustment", 0.042),
    ("edge", 6.5),
    ("expected_value", 1.08),
    ("ev", 0.03),
    ("fair_odds", 1.62),
    ("odds", 1.85),
    ("stake", 2.0),
    ("implied_probability", 0.55),
    ("delta_pp", 4.2),
    ("prediction", 11),
])
def test_forbidden_quantity_field_rejects_whole_response(packet, response, field_name, value):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0][field_name] = value
    r = _validate(bad, packet)
    assert not r.accepted
    # Caught by the closed schema (unknown field) or the firewall -- either is a
    # whole-response rejection, which is the invariant under test.
    assert r.failure in (lifecycle.SCHEMA_INVALID, lifecycle.NUMERICAL_AUTHORITY_VIOLATION)
    assert r.n_accepted == 0, "no salvage: nothing may be kept from a tainted response"


def test_bare_numeric_anywhere_is_rejected_even_with_an_innocent_name(packet, response):
    """The firewall is not a keyword list: an unforeseen field name carrying a magnitude
    must still fail."""
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["priority"] = 0.87        # enum field given a number
    r = _validate(bad, packet)
    assert not r.accepted
    assert r.n_accepted == 0


def test_numeric_scan_catches_unknown_field_names_directly():
    payload = {"hypotheses": [{"some_unforeseen_name": 4.2}]}
    v = firewall.scan_numerical_authority(payload)
    assert any(x.kind == "numeric_value_outside_allowlist" for x in v)


def test_unknown_field_rejected_by_closed_schema(packet, response):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["reasoning_trace"] = "I thought about it carefully"
    r = _validate(bad, packet)
    assert not r.accepted
    assert r.failure == lifecycle.SCHEMA_INVALID
    assert any("unknown field" in x for x in r.reasons)


# --------------------------------------------------------------------------- prose layer
@pytest.mark.parametrize("question,expected_kind", [
    ("Does the home side reach a 61.7% corner rate against back-three opponents here?",
     "percentage"),
    ("Is the home side worth +4.2 pp on corners against these opponents in this spot?",
     "percentage_points"),
    ("Should we take the corners market at 1.85 against this opponent profile now?",
     "decimal_odds"),
    ("Is there expected value in the corners market against this opponent profile?",
     "ev_or_edge_claim"),
    ("What stake is appropriate on corners against this opponent profile this week?",
     "stake_claim"),
    ("Would you back the over on corners against back-three opponents in this fixture?",
     "bet_recommendation"),
    ("We predict 11.5 corners against back-three opponents in this particular fixture.",
     "numeric_forecast"),
    ("Is over 8.5 corners the right side against this opponent profile in this match?",
     "market_line_position"),
    ("Does this opponent profile add +1.3 more corners relative to the home baseline?",
     "numeric_effect_size"),
])
def test_predictive_prose_is_rejected(packet, response, question, expected_kind):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["question"] = question
    r = _validate(bad, packet)
    assert not r.accepted, f"{expected_kind!r} prose was not caught: {question!r}"
    assert r.failure == lifecycle.NUMERICAL_AUTHORITY_VIOLATION
    assert r.n_accepted == 0


@pytest.mark.parametrize("question", [
    "Does the home side generate more corners against opponents recorded with a back "
    "three, compared with its own home baseline?",
    "When trailing at half time, does the home side's second-half shot volume differ "
    "from its baseline over the last 10 matches?",
    "Do the away side's tackles change against opponents in the high possession band?",
])
def test_legitimate_football_questions_are_not_false_positives(packet, response, question):
    """Football vocabulary that LOOKS numeric must survive: 'back three', 'back four',
    'last 10 matches', 'half time'. A firewall that rejects these is unusable."""
    ok = copy.deepcopy(response)
    ok["hypotheses"][0]["question"] = question
    r = _validate(ok, packet)
    assert r.accepted, r.reasons
    assert r.n_accepted == len(ok["hypotheses"])


# -------------------------------------------------------------------------- latent grades
@pytest.mark.parametrize("grade", sorted(vocabulary.BANNED_ADVANTAGE_GRADES))
def test_advantage_grade_rejected(packet, response, grade):
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["research_family"] = grade     # any field carrying the grade
    r = _validate(bad, packet)
    assert not r.accepted
    assert r.failure in (lifecycle.SCHEMA_INVALID, lifecycle.LATENT_GRADING_VIOLATION)


def test_advantage_grade_detected_by_firewall_directly():
    payload = {"hypotheses": [{"assessment": "STRONG_A_ADVANTAGE"}]}
    v = firewall.scan_latent_grading(payload)
    assert v and v[0].kind == "advantage_grade"


def test_level_grade_detected_by_firewall_directly():
    payload = {"hypotheses": [{"level": "VERY_HIGH"}]}
    v = firewall.scan_latent_grading(payload)
    assert v and v[0].kind == "level_grade"


def test_priority_may_use_ordered_tokens_without_being_a_grade(packet, response):
    """priority is a research-budget hint with no football meaning, so LOW/MEDIUM/HIGH is
    legitimate there and nowhere else."""
    for p in vocabulary.PRIORITY:
        ok = copy.deepcopy(response)
        ok["hypotheses"][0]["priority"] = p
        assert _validate(ok, packet).accepted


def test_cohort_band_is_not_a_strength_grade(packet, response):
    """'HIGH' as an opponent-profile BAND names which opponents to measure. It is not a
    claim about anyone's strength, and must not be confused with a latent grade."""
    r = _validate(response, packet)
    assert r.accepted
    bands = [c["value"] for h in response["hypotheses"] for c in h["conditions"]
             if c["dimension"] == "opponent_profile"]
    assert "HIGH" in bands, "fixture must actually exercise the band path"


# ------------------------------------------------------------------------ identity binding
def test_response_must_bind_to_the_packet_actually_sent(packet, response):
    bad = copy.deepcopy(response)
    bad["packet_hash"] = "0" * 64
    r = _validate(bad, packet)
    assert not r.accepted
    assert r.failure == lifecycle.SCHEMA_INVALID
    assert any("packet_hash" in x for x in r.reasons)


def test_response_must_name_the_right_fixture(packet, response):
    bad = copy.deepcopy(response)
    bad["fixture_id"] = "fx_not_this_one"
    assert not _validate(bad, packet).accepted


def test_schema_has_no_numeric_field_anywhere():
    """The structural layer of the firewall: a probability must have nowhere to live."""
    from src.research.hypothesis_engine import schema as S

    found: list[str] = []

    def walk(node, path):
        if isinstance(node, dict):
            if node.get("type") in ("number", "integer"):
                found.append(path)
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(S.build_schema(), "$")
    assert found == [], f"schema exposes numeric field(s) a magnitude could hide in: {found}"
