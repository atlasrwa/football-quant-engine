"""Mandate §17, §19, §29 -- query-plan compilation, the research funnel, and provenance."""
from __future__ import annotations

import copy
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import (
    capability, lifecycle as L, query_plan as QP, vocabulary)


@pytest.fixture()
def packet():
    return F.real_identity_packet()


@pytest.fixture()
def response(packet):
    return F.valid_response(packet)


# ==================================================================== compiler behaviour
def test_every_hypothesis_in_the_golden_response_compiles(packet, response):
    out = QP.compile_set(response, cutoff_unix=F.CUTOFF)
    assert out["n_hypotheses"] == 4
    assert out["n_fully_compilable"] == 4
    assert out["compile_rate"] == 1.0


def test_cutoff_is_injected_by_the_engine_and_cannot_be_supplied(packet, response):
    """There is no cutoff field on the hypothesis schema, and the compiler stamps its own."""
    from src.research.hypothesis_engine import schema as S
    hyp_props = S.build_schema()["properties"]["hypotheses"]["items"]["properties"]
    assert not any("cutoff" in k or "as_of" in k or "unix" in k for k in hyp_props)

    res = QP.compile_hypothesis(response["hypotheses"][0], fixture_id="fx_0001",
                                cutoff_unix=12345)
    assert all(r.plan.cutoff_unix == 12345 for r in res if r.ok)


def test_one_plan_per_target_metric(response):
    h = response["hypotheses"][3]
    assert len(h["target_metrics"]) == 3
    res = QP.compile_hypothesis(h, fixture_id="fx_0001", cutoff_unix=F.CUTOFF)
    assert len(res) == 3
    assert {r.plan.metric for r in res} == set(h["target_metrics"])


def test_plan_hash_is_stable_and_content_addressed(response):
    a = QP.compile_hypothesis(response["hypotheses"][0], fixture_id="fx_0001",
                              cutoff_unix=F.CUTOFF)[0].plan
    b = QP.compile_hypothesis(response["hypotheses"][0], fixture_id="fx_0001",
                              cutoff_unix=F.CUTOFF)[0].plan
    assert a.plan_hash() == b.plan_hash()

    c = QP.compile_hypothesis(response["hypotheses"][0], fixture_id="fx_0001",
                              cutoff_unix=F.CUTOFF + 1)[0].plan
    assert c.plan_hash() != a.plan_hash(), "a different cutoff is a different measurement"


@pytest.mark.parametrize("dimension", ["weather", "referee_mood", "crowd_noise",
                                       "minute_window", "player_form"])
def test_unknown_dimension_is_unsupported_dimension(response, dimension):
    bad = copy.deepcopy(response["hypotheses"][0])
    bad["conditions"] = [{"dimension": dimension, "value": "ANY"}]
    res = QP.compile_hypothesis(bad, fixture_id="fx_0001", cutoff_unix=F.CUTOFF)
    assert res[0].failure == L.UNSUPPORTED_DIMENSION


def test_illegal_value_for_a_legal_dimension_is_rejected(response):
    bad = copy.deepcopy(response["hypotheses"][0])
    bad["conditions"] = [{"dimension": "venue", "value": "NEUTRAL_GROUND"}]
    res = QP.compile_hypothesis(bad, fixture_id="fx_0001", cutoff_unix=F.CUTOFF)
    assert res[0].failure == L.UNSUPPORTED_DIMENSION


def test_axis_is_rejected_on_a_dimension_that_does_not_take_one(response):
    bad = copy.deepcopy(response["hypotheses"][0])
    bad["conditions"] = [{"dimension": "venue", "value": "HOME", "axis": "corners_for"}]
    res = QP.compile_hypothesis(bad, fixture_id="fx_0001", cutoff_unix=F.CUTOFF)
    assert res[0].failure == L.QUERY_INVALID


def test_empty_target_metrics_is_query_invalid(response):
    bad = copy.deepcopy(response["hypotheses"][0])
    bad["target_metrics"] = []
    res = QP.compile_hypothesis(bad, fixture_id="fx_0001", cutoff_unix=F.CUTOFF)
    assert res[0].failure == L.QUERY_INVALID


def test_one_bad_hypothesis_does_not_discard_the_others(response):
    """Per-hypothesis compilation, unlike the whole-response firewall gate."""
    bad = copy.deepcopy(response)
    bad["hypotheses"][0]["conditions"] = [{"dimension": "nonsense", "value": "X"}]
    out = QP.compile_set(bad, cutoff_unix=F.CUTOFF)
    assert out["n_fully_compilable"] == 3
    assert out["n_hypotheses"] == 4


def test_plan_contains_no_free_text_field(response):
    """Nothing the LLM wrote in prose may reach a data-access path."""
    plan = QP.compile_hypothesis(response["hypotheses"][0], fixture_id="fx_0001",
                                 cutoff_unix=F.CUTOFF)[0].plan.to_dict()
    enumerated = {
        "subject": vocabulary.SUBJECTS,
        "side": vocabulary.SIDES,
        "window": vocabulary.WINDOWS,
        "period": vocabulary.PERIOD_VALUES,
        "comparison": vocabulary.COMPARISONS,
        "provider": capability.PROVIDERS,
    }
    for field, allowed in enumerated.items():
        assert plan[field] in allowed, f"{field}={plan[field]!r} escaped its enum"
    assert plan["metric"] in capability.metric_names()
    for c in plan["conditions"]:
        assert c["dimension"] in vocabulary.dimension_names()
        assert c["value"] in vocabulary.dimension(c["dimension"])["values"]


# ======================================================================= lifecycle graph
def test_the_full_funnel_can_be_walked_in_order():
    state = L.LLM_PROPOSED
    for expected in (L.QUERY_VALID, L.DATA_SUFFICIENT, L.HISTORICAL_RESULT,
                     L.CONFOUNDER_REVIEW, L.WALK_FORWARD_CANDIDATE, L.OOS_SUPPORTED,
                     L.PROSPECTIVE_CANDIDATE, L.PROSPECTIVELY_SUPPORTED):
        state = L.advance(state, expected)
    assert state == L.PROSPECTIVELY_SUPPORTED
    assert L.is_terminal(state)


@pytest.mark.parametrize("failure", [
    L.QUERY_INVALID, L.UNSUPPORTED_METRIC, L.UNSUPPORTED_DIMENSION,
    L.UNSUPPORTED_CONTEXT_SOURCE, L.INSUFFICIENT_EVIDENCE, L.LEAKAGE_REJECTED,
    L.NUMERICAL_AUTHORITY_VIOLATION, L.LATENT_GRADING_VIOLATION, L.SCHEMA_INVALID,
    L.PROVIDER_SEMANTICS_CONFLICT, L.UNSUPPORTED_GRANULARITY,
])
def test_proposal_stage_failures_are_all_reachable(failure):
    assert L.advance(L.LLM_PROPOSED, failure) == failure


def test_a_failure_cannot_be_raised_from_the_wrong_stage():
    with pytest.raises(L.LifecycleError):
        L.advance(L.WALK_FORWARD_CANDIDATE, L.SCHEMA_INVALID)
    with pytest.raises(L.LifecycleError):
        L.advance(L.LLM_PROPOSED, L.OOS_FAILED)


def test_terminal_states_have_no_exit():
    for terminal in list(L.FAILURE_STATES) + [L.PROSPECTIVELY_SUPPORTED]:
        with pytest.raises(L.LifecycleError):
            L.advance(terminal, L.QUERY_VALID)


def test_all_mandated_failure_states_exist():
    for name in ("QUERY_INVALID", "UNSUPPORTED_METRIC", "UNSUPPORTED_DIMENSION",
                 "UNSUPPORTED_CONTEXT_SOURCE", "INSUFFICIENT_EVIDENCE",
                 "INSUFFICIENT_DATA", "PROVIDER_SEMANTICS_CONFLICT",
                 "LEAKAGE_REJECTED", "HISTORICALLY_UNSUPPORTED", "OOS_FAILED"):
        assert name in L.FAILURE_STATES


# ========================================================================== provenance
def _prov():
    return L.HypothesisProvenance(
        hypothesis_id="H1", fixture_id="fx_0001",
        evidence_packet_hash="a" * 64, model_id="MODEL_UNDER_TEST",
        prompt_version="hypothesis_analyst_prompt_v1",
        schema_version="hypothesis_set_schema_v1",
        vocabulary_version="hypothesis_vocabulary_v1",
        capability_inventory_version="capability_inventory_v1",
        generation_id="HYPOTHESIS_LAYER_V1")


def test_provenance_is_append_only_and_records_every_stage():
    p = _prov()
    assert p.state == L.LLM_PROPOSED and len(p.events) == 1
    p.record(L.QUERY_VALID, "compiled", artifact_hash="b" * 64)
    p.record(L.DATA_SUFFICIENT, "coverage ok")
    assert [e.state for e in p.events] == [
        L.LLM_PROPOSED, L.QUERY_VALID, L.DATA_SUFFICIENT]
    assert p.events[0].detail == "created", "earlier events are never mutated"


def test_provenance_refuses_an_illegal_jump():
    p = _prov()
    with pytest.raises(L.LifecycleError):
        p.record(L.OOS_SUPPORTED)
    assert p.state == L.LLM_PROPOSED, "a refused transition must not change state"


def test_provenance_carries_the_full_traceability_chain():
    d = _prov().to_dict()
    for key in ("fixture_id", "evidence_packet_hash", "model_id", "prompt_version",
                "schema_version", "vocabulary_version", "capability_inventory_version",
                "generation_id", "lifecycle_version"):
        assert key in d, f"provenance must carry {key}"


def test_stable_hash_is_order_independent_and_deterministic():
    a = L.stable_hash({"x": 1, "y": [1, 2]})
    b = L.stable_hash({"y": [1, 2], "x": 1})
    assert a == b
    assert a != L.stable_hash({"x": 1, "y": [2, 1]})


def test_fail_rejects_a_non_failure_state():
    with pytest.raises(L.LifecycleError):
        _prov().fail(L.QUERY_VALID)
