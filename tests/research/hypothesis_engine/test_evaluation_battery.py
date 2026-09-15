"""Mandate §24-§28 -- the evaluation battery scores hypothesis QUALITY, not prediction.

These tests prove the battery can distinguish good from bad behaviour BEFORE any paid call,
and that each gate is able to fail. A gate that cannot fail cannot be passed meaningfully.
"""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import evaluation as E, lifecycle as L, normalize


@pytest.fixture()
def packet():
    return F.real_identity_packet()


@pytest.fixture()
def good(packet):
    return F.valid_response(packet)


# ======================================================================= per-fixture score
def test_a_good_response_scores_cleanly(packet, good):
    s = E.score_response(good, packet=packet)
    assert s.schema_valid and s.whole_response_failure is None
    assert s.n_accepted == s.n_hypotheses == 4
    assert s.n_compilable == 4
    assert s.numerical_violations == 0 and s.grading_violations == 0
    assert s.unavailable_requests == 0
    assert s.metric_richness >= 8
    assert s.failure_breakdown == {}


def test_a_probability_emitting_response_scores_a_hard_gate_failure(packet, good):
    bad = copy.deepcopy(good)
    bad["hypotheses"][0]["question"] = "Is the corner probability 61.7% in this fixture?"
    s = E.score_response(bad, packet=packet)
    assert s.whole_response_failure == L.NUMERICAL_AUTHORITY_VIOLATION
    assert s.numerical_violations >= 1
    assert s.n_accepted == 0


def test_unavailable_data_requests_are_counted(packet, good):
    bad = copy.deepcopy(good)
    bad["hypotheses"][0]["required_capabilities"] = ["injuries"]
    bad["hypotheses"][1]["required_capabilities"] = ["minute_level_events"]
    s = E.score_response(bad, packet=packet)
    assert s.unavailable_requests == 2
    assert s.failure_breakdown.get(L.UNSUPPORTED_CONTEXT_SOURCE) == 2


def test_ungrounded_hypotheses_lower_grounding_not_schema(packet, good):
    bad = copy.deepcopy(good)
    bad["hypotheses"][0]["evidence_refs"] = ["MADE_UP"]
    s = E.score_response(bad, packet=packet)
    assert s.schema_valid
    assert s.n_accepted == 3
    assert s.failure_breakdown.get(L.INSUFFICIENT_EVIDENCE) == 1


# ============================================================================ aggregation
def _scores(packet, response, n=10):
    return [E.score_response(response, packet=packet) for _ in range(n)]


def test_battery_passes_on_uniformly_good_behaviour(packet, good):
    rep = E.aggregate(
        _scores(packet, good),
        identity_jaccards=[1.0] * 10,
        evidence_perturbation_trips=[True] * 8 + [False] * 2,
        irrelevant_perturbation_invariances=[True] * 10,
        starved_abstention_flags=[True] * 8 + [False] * 2,
    )
    assert rep.passed, rep.gates
    assert all(v is True for v in rep.gates.values())


def test_unmeasured_control_fails_closed_rather_than_passing(packet, good):
    """'We did not measure it' must stay distinct from 'it passed', and must not pass."""
    rep = E.aggregate(_scores(packet, good))
    assert rep.gates["I_identity_robustness"] is None
    assert rep.gates["J_evidence_sensitivity"] is None
    assert rep.gates["K_irrelevant_invariance"] is None
    assert rep.gates["L_abstention_quality"] is None
    assert not rep.passed, "an unmeasured gate may never count as a pass"


def test_numerical_authority_gate_is_zero_tolerance(packet, good):
    bad = copy.deepcopy(good)
    bad["hypotheses"][0]["question"] = "What edge is there on corners at 1.85 right now?"
    scores = _scores(packet, good, 19) + [E.score_response(bad, packet=packet)]
    rep = E.aggregate(
        scores, identity_jaccards=[1.0] * 20,
        evidence_perturbation_trips=[True] * 20,
        irrelevant_perturbation_invariances=[True] * 20,
        starved_abstention_flags=[True] * 20)
    assert rep.gates["E_numerical_authority"] is False
    assert not rep.passed, "one violation in twenty fixtures must fail the battery"


def test_identity_gate_fails_on_low_intent_overlap(packet, good):
    rep = E.aggregate(
        _scores(packet, good),
        identity_jaccards=[0.4] * 10,
        evidence_perturbation_trips=[True] * 10,
        irrelevant_perturbation_invariances=[True] * 10,
        starved_abstention_flags=[True] * 10)
    assert rep.gates["I_identity_robustness"] is False
    assert not rep.passed


def test_evidence_sensitivity_gate_fails_on_an_inert_model(packet, good):
    """A model whose questions never move when the football evidence moves is inert, and
    that is a failure even though nothing it produced was invalid."""
    rep = E.aggregate(
        _scores(packet, good),
        identity_jaccards=[1.0] * 10,
        evidence_perturbation_trips=[False] * 10,
        irrelevant_perturbation_invariances=[True] * 10,
        starved_abstention_flags=[True] * 10)
    assert rep.gates["J_evidence_sensitivity"] is False


def test_richness_gate_fails_on_a_one_metric_model(packet, good):
    narrow = copy.deepcopy(good)
    for h in narrow["hypotheses"]:
        h["target_metrics"] = ["corners"]
    rep = E.aggregate(
        _scores(packet, narrow),
        identity_jaccards=[1.0] * 10,
        evidence_perturbation_trips=[True] * 10,
        irrelevant_perturbation_invariances=[True] * 10,
        starved_abstention_flags=[True] * 10)
    assert rep.gates["H_metric_richness"] is False


def test_redundancy_gate_fails_on_restatement(packet, good):
    padded = copy.deepcopy(good)
    for i in range(8):
        dup = copy.deepcopy(good["hypotheses"][0])
        dup["hypothesis_id"] = f"H{40 + i}"
        dup["question"] = f"Reworded restatement number {i} of the same corner question?"
        padded["hypotheses"].append(dup)
    rep = E.aggregate(
        _scores(packet, padded),
        identity_jaccards=[1.0] * 10,
        evidence_perturbation_trips=[True] * 10,
        irrelevant_perturbation_invariances=[True] * 10,
        starved_abstention_flags=[True] * 10)
    assert rep.gates["G_non_redundancy"] is False


def test_thresholds_are_fixed_constants_not_derived_from_results():
    """The bar must be settable before results exist, and readable from the repository."""
    assert isinstance(E.THRESHOLDS, dict)
    assert E.THRESHOLDS["max_numerical_authority_violations"] == 0
    assert E.THRESHOLDS["max_latent_grading_violations"] == 0
    for v in E.THRESHOLDS.values():
        assert isinstance(v, (int, float))


# ================================================================= funnel survival (§28)
def _prov(states):
    p = L.HypothesisProvenance(
        hypothesis_id="H1", fixture_id="fx", evidence_packet_hash="a" * 64,
        model_id="M", prompt_version="p", schema_version="s",
        vocabulary_version="v", capability_inventory_version="c", generation_id="g")
    for s in states:
        p.record(s)
    return p


def test_funnel_survival_is_reported_separately_from_generator_quality():
    provs = [
        _prov([L.QUERY_VALID, L.DATA_SUFFICIENT, L.HISTORICAL_RESULT]),
        _prov([L.QUERY_VALID, L.DATA_SUFFICIENT]),
        _prov([L.QUERY_VALID]),
    ]
    rep = E.funnel_survival(provs)
    assert rep["n_proposed"] == 3
    assert rep["reached"][L.QUERY_VALID] == 3
    assert rep["reached"][L.DATA_SUFFICIENT] == 2
    assert rep["reached"][L.HISTORICAL_RESULT] == 1
    assert "not the generator" in rep["note"]


def test_a_valid_hypothesis_the_data_rejects_is_not_a_generator_failure(packet, good):
    """§28: the generator's score must not depend on whether the answer was significant."""
    s = E.score_response(good, packet=packet)
    d = s.to_dict()
    for outcome_word in ("significant", "signal", "supported", "brier", "logloss",
                         "oos", "prospective", "settled"):
        assert outcome_word not in " ".join(k.lower() for k in d)
