"""Mandate §20, §23, §27 -- repurposed identity and perturbation controls.

OLD TARGET (legacy LLM_LATENT_STATE_EXPERIMENT):
    does the LLM produce the same ORDINAL STATE under an alias swap?

NEW TARGET:
    when the structured evidence is equivalent, does replacing a real identity with a
    neutral alias change the NORMALIZED SCIENTIFIC INTENT of the questions?

Prose is explicitly NOT the unit of comparison. Two differently-worded questions asking for
the same measurement are equivalent; two identically-worded questions asking for different
measurements are not.

These tests exercise the control MACHINERY against frozen/mocked responses. They prove the
controls can detect what they claim to detect -- every one of them is shown able to FAIL,
so a later live run cannot pass them vacuously. No Bedrock call is made.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import normalize, validator


# ============================================================== normalization properties
def test_wording_does_not_affect_intent():
    """The core claim: rewording a question changes nothing scientific."""
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    b["hypotheses"][0]["question"] = (
        "Is this side's corner generation at home elevated or suppressed when the "
        "opponent lined up with three at the back, versus its own home rate?")
    assert normalize.compare(a, b).equivalent


def test_priority_and_confounders_do_not_affect_intent():
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    b["hypotheses"][0]["priority"] = "LOW"
    b["hypotheses"][0]["candidate_confounders"] = ["SCORE_STATE", "MANAGER_REGIME"]
    assert normalize.compare(a, b).equivalent


def test_evidence_ref_choice_does_not_affect_intent():
    """Citing a different supporting item does not change WHAT is being measured."""
    p = F.real_identity_packet()
    ids = F.evidence_ids(p)
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    b["hypotheses"][0]["evidence_refs"] = [ids[2], ids[3]]
    assert normalize.compare(a, b).equivalent


def test_splitting_metrics_across_hypotheses_does_not_affect_intent():
    """Asking about two metrics in one hypothesis, or one each in two, is the same science."""
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    h = b["hypotheses"][0]
    h2 = copy.deepcopy(h)
    h["target_metrics"] = ["corners"]
    h2["hypothesis_id"] = "H99"
    h2["target_metrics"] = ["accurate_crosses"]
    b["hypotheses"].append(h2)
    assert normalize.compare(a, b).equivalent


def test_an_any_condition_carries_no_intent():
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    b["hypotheses"][0]["conditions"].append({"dimension": "competition", "value": "ANY"})
    assert normalize.compare(a, b).equivalent


# ================================================================ identity alias control
def test_identity_alias_swap_preserves_scientific_intent():
    """The headline control. Evidence is byte-identical; only display labels differ."""
    real = F.real_identity_packet()
    alias = F.alias_identity_packet()
    assert [e["id"] for e in real["evidence"]] == [e["id"] for e in alias["evidence"]], \
        "evidence ids must be identity-neutral or the control is confounded"

    cmp_ = normalize.compare(F.valid_response(real), F.valid_response(alias))
    assert cmp_.equivalent
    assert cmp_.jaccard == 1.0


def test_the_identity_control_can_actually_fail():
    """A control that cannot fail proves nothing. Change the MEASUREMENT under the alias
    and the comparison must detect it."""
    real = F.real_identity_packet()
    alias = F.alias_identity_packet()
    moved = F.valid_response(alias)
    moved["hypotheses"][0]["target_metrics"] = ["tackles"]     # different science
    cmp_ = normalize.compare(F.valid_response(real), moved)
    assert not cmp_.equivalent
    assert cmp_.jaccard < 1.0
    assert cmp_.only_a or cmp_.only_b


def test_subject_aliases_normalize_to_one_canonical_subject():
    """TEAM_A and HOME_TEAM name the same subject; a response using either must compare
    as identical."""
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    for h in b["hypotheses"]:
        h["subject"] = {"HOME_TEAM": "TEAM_A", "AWAY_TEAM": "TEAM_B"}[h["subject"]]
    assert normalize.compare(a, b).equivalent


# ========================================================== meaningful-evidence controls
def test_formation_evidence_removal_removes_formation_questions_only():
    """§27 evidence-removal control: formation-conditioned questions should disappear or
    abstain, while raw-profile questions remain."""
    p = F.real_identity_packet()
    full = F.valid_response(p)

    no_formation = copy.deepcopy(full)
    no_formation["hypotheses"] = [
        h for h in no_formation["hypotheses"]
        if not any(c["dimension"].endswith("formation_family") for c in h["conditions"])]

    assert normalize.conditions_mentioning(full, "opponent_formation_family")
    assert not normalize.conditions_mentioning(no_formation, "opponent_formation_family")

    # the non-formation science survives untouched
    surviving = {i.key() for i in normalize.normalize_set(no_formation)}
    original = {i.key() for i in normalize.normalize_set(full)}
    assert surviving < original
    assert len(surviving) >= 6


def test_venue_control_detects_a_venue_change():
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    for c in b["hypotheses"][0]["conditions"]:
        if c["dimension"] == "venue":
            c["value"] = "AWAY"
    assert not normalize.compare(a, b).equivalent


def test_profile_band_control_detects_a_band_change():
    """§27 raw-stat-profile control: moving the opponent from low to high corner
    concession must be able to change the questions."""
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    for c in b["hypotheses"][1]["conditions"]:
        if c["dimension"] == "opponent_profile":
            c["value"] = "LOW"
    assert not normalize.compare(a, b).equivalent


def test_irrelevant_field_change_does_not_move_intent():
    """§27 irrelevant-field control."""
    p = F.real_identity_packet()
    a = F.valid_response(p)
    b = copy.deepcopy(a)
    b["fixture_id"] = "fx_9999"
    b["hypotheses"][0]["priority"] = "HIGH"
    assert normalize.compare(a, b).equivalent


def test_unsupported_data_trap_is_caught_by_validation():
    """§27 unsupported-data trap: a hypothesis that invents injury context must not pass."""
    p = F.real_identity_packet()
    trap = F.valid_response(p)
    trap["hypotheses"][0]["required_capabilities"] = ["injuries"]
    r = validator.validate(trap, packet=p, expected_packet_hash=p["packet_hash"],
                           expected_fixture_id=p["fixture_id"])
    assert not r.verdicts[0].accepted


# ================================================================= diversity / richness
def test_intent_profile_rewards_distinct_ideas_not_quantity():
    p = F.real_identity_packet()
    good = F.valid_response(p)

    padded = copy.deepcopy(good)
    for i in range(4):                       # restate H1 four more times, reworded
        dup = copy.deepcopy(good["hypotheses"][0])
        dup["hypothesis_id"] = f"H{50 + i}"
        dup["question"] = f"Restated variant {i} of the same corner question about venue?"
        padded["hypotheses"].append(dup)

    pg, pp = normalize.intent_profile(good), normalize.intent_profile(padded)
    assert pp["n_hypotheses"] > pg["n_hypotheses"], "padding did add hypotheses"
    assert pp["n_distinct_intents"] == pg["n_distinct_intents"], \
        "but it must add no distinct science"
    assert pp["redundancy_rate"] > pg["redundancy_rate"]


def test_metric_richness_reflects_corpus_use():
    p = F.real_identity_packet()
    rich = F.valid_response(p)
    assert normalize.intent_profile(rich)["metric_richness"] >= 8

    narrow = copy.deepcopy(rich)
    for h in narrow["hypotheses"]:
        h["target_metrics"] = ["corners"]
    assert normalize.intent_profile(narrow)["metric_richness"] == 1


def test_abstentions_are_counted_but_contribute_no_intent():
    p = F.real_identity_packet()
    prof = normalize.intent_profile(F.abstention_response(p))
    assert prof["n_hypotheses"] == 1
    assert prof["n_abstentions"] == 1
    assert prof["n_distinct_intents"] == 0


def test_intent_keys_are_stable_across_runs():
    p = F.real_identity_packet()
    a, b = F.valid_response(p), F.valid_response(p)
    assert normalize.intent_key_set(a) == normalize.intent_key_set(b)
