"""Mandate §10, §18, §23 -- similarity and deterministic measurement.

Two invariants:
  * the LLM may NAME a similarity dimension but may never supply a similarity value;
  * every number in a research result is computed by the engine, from history strictly
    before the fixture.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/tests/research/hypothesis_engine")

import pytest

import fixtures as F
from src.research.hypothesis_engine import (
    lifecycle, measurement as M, query_plan, similarity as S, vocabulary)
from src.research.hypothesis_engine.query_plan import Condition, QueryPlan


# ================================================================== similarity interface
def test_llm_may_request_a_similar_opponent_cohort(packet_free=None):
    """Naming the dimension and band is legitimate and compiles."""
    p = F.real_identity_packet()
    r = F.valid_response(p)
    h = next(x for x in r["hypotheses"] if x["hypothesis_id"] == "H2")
    cond = h["conditions"][0]
    assert cond["dimension"] == "opponent_profile"
    assert cond["value"] in vocabulary.PROFILE_BANDS
    assert cond["axis"] in vocabulary.PROFILE_AXES
    res = query_plan.compile_hypothesis(h, fixture_id=p["fixture_id"],
                                        cutoff_unix=F.CUTOFF)
    assert all(x.ok for x in res)


def test_opponent_profile_without_an_axis_is_invalid():
    p = F.real_identity_packet()
    h = dict(F.valid_response(p)["hypotheses"][1])
    h["conditions"] = [{"dimension": "opponent_profile", "value": "HIGH"}]
    res = query_plan.compile_hypothesis(h, fixture_id=p["fixture_id"],
                                        cutoff_unix=F.CUTOFF)
    assert any(x.failure == lifecycle.QUERY_INVALID for x in res)


@pytest.mark.parametrize("key", ["similarity", "similarity_score", "distance",
                                 "closeness", "resemblance", "match_score"])
def test_llm_supplied_similarity_value_is_refused(key):
    reasons = S.reject_llm_supplied_similarity({"conditions": [{key: 0.83}]})
    assert reasons and "may not" in reasons[0]


def test_unvalidated_distance_methods_raise_rather_than_silently_falling_back():
    for method in ("EUCLIDEAN_DISTANCE", "MAHALANOBIS_DISTANCE", "LEARNED_EMBEDDING",
                   "CLUSTER_ASSIGNMENT"):
        assert S.METHOD_STATUS[method] == S.PENDING_VALIDATION
        with pytest.raises(S.SimilarityMethodPending):
            S.resolve_band(axis="corners_against", requested_band="HIGH",
                           cutoff_unix=F.CUTOFF, candidates=["a", "b", "c"],
                           axis_value_fn=lambda o, c: (5.0, 10), method=method)


def _values(mapping):
    def fn(opponent, cutoff_unix):
        v = mapping.get(opponent)
        return None if v is None else (v, 10)
    return fn


def test_band_resolution_is_deterministic_and_engine_owned():
    vals = {"o1": 2.0, "o2": 4.0, "o3": 6.0, "o4": 8.0, "o5": 10.0, "o6": 12.0}
    res = S.resolve_band(axis="corners_against", requested_band="HIGH",
                         cutoff_unix=F.CUTOFF, candidates=list(vals),
                         axis_value_fn=_values(vals))
    assert res.usable_n == 6 and res.missing_n == 0
    assert res.members, "a HIGH band must select someone from a spread of six"
    assert all(vals[m] >= 8.0 for m in res.members)
    again = S.resolve_band(axis="corners_against", requested_band="HIGH",
                           cutoff_unix=F.CUTOFF, candidates=list(vals),
                           axis_value_fn=_values(vals))
    assert res.members == again.members, "banding must be deterministic"


def test_opponents_with_too_little_history_are_missing_not_guessed():
    res = S.resolve_band(axis="corners_against", requested_band="LOW",
                         cutoff_unix=F.CUTOFF,
                         candidates=["o1", "o2", "o3", "o4"],
                         axis_value_fn=lambda o, c: (3.0, 1) if o == "o4" else (5.0, 10))
    assert res.missing_n == 1
    assert "o4" not in res.members


def test_too_few_bandable_opponents_refuses_to_form_terciles():
    res = S.resolve_band(axis="corners_against", requested_band="HIGH",
                         cutoff_unix=F.CUTOFF, candidates=["o1", "o2"],
                         axis_value_fn=_values({"o1": 3.0, "o2": 9.0}))
    assert res.members == ()
    assert any("cannot form terciles" in n for n in res.notes)


def test_similarity_status_is_visibly_pending_in_every_result():
    res = S.resolve_band(axis="possession_for", requested_band="ANY",
                         cutoff_unix=F.CUTOFF, candidates=["o1"],
                         axis_value_fn=_values({"o1": 50.0}))
    assert res.to_dict()["similarity_version"] == "opponent_similarity_v1_pending"


def test_cutoff_is_passed_through_to_every_assignment():
    res = S.resolve_band(axis="corners_against", requested_band="ANY",
                         cutoff_unix=F.CUTOFF, candidates=["o1", "o2"],
                         axis_value_fn=_values({"o1": 4.0, "o2": 7.0}))
    assert all(a.cutoff_unix == F.CUTOFF for a in res.assignments)


# ==================================================================== measurement engine
def _plan(conditions=(), window="ALL_PRIOR", period="ALL", metric="corners"):
    return QueryPlan(
        plan_version="query_plan_v1", hypothesis_id="H1", fixture_id="fx_0001",
        subject="HOME_TEAM", metric=metric, side="FOR", window=window, period=period,
        conditions=tuple(conditions), comparison="SUBJECT_OVERALL_BASELINE",
        provider="thestatsapi", cutoff_unix=F.CUTOFF,
        required_granularity="FULL_MATCH")


class _History:
    def __init__(self, obs):
        self._obs = obs

    def observations(self, **kw):
        return self._obs


def _obs(n, value, *, dims=None, end=F.CUTOFF - 86_400, step=86_400):
    """n observations ending strictly before the cutoff, oldest first.

    Anchored at the END rather than the start so growing `n` extends further into the
    past instead of pushing observations past the cutoff -- which the measurement layer
    correctly refuses to measure.
    """
    start = end - (n - 1) * step
    return [M.Observation(f"m{i}", start + i * step, value, dict(dims or {}))
            for i in range(n)]


def test_measurement_computes_difference_and_shrinkage_itself():
    conditional = _obs(10, 7.0, dims={"venue": "HOME"})
    other = _obs(20, 5.0, dims={"venue": "AWAY"}, end=F.CUTOFF - 30 * 86_400)
    hist = _History(conditional + other)
    res = M.execute(_plan([Condition("venue", "HOME")]),
                    subject_team="T", history=hist)
    assert res.status == lifecycle.HISTORICAL_RESULT
    assert res.conditional.usable_n == 10
    assert res.baseline.usable_n == 30
    assert res.difference == pytest.approx(7.0 - (10 * 7.0 + 20 * 5.0) / 30)
    w = 10 / (10 + M.SHRINK_K)
    assert res.shrinkage_weight == pytest.approx(w, abs=1e-6)
    assert res.shrunk_difference == pytest.approx(w * res.difference)
    assert abs(res.shrunk_difference) < abs(res.difference), "shrinkage pulls toward zero"


def test_thin_cohort_is_insufficient_data_not_a_null_effect():
    hist = _History(_obs(2, 7.0, dims={"venue": "HOME"})
                    + _obs(20, 5.0, dims={"venue": "AWAY"}, end=F.CUTOFF - 30 * 86_400))
    res = M.execute(_plan([Condition("venue", "HOME")]), subject_team="T", history=hist)
    assert res.status == lifecycle.INSUFFICIENT_DATA
    assert res.difference is None
    assert any("INSUFFICIENT_DATA rather than as a null effect" in n for n in res.notes)


def test_missing_dimension_is_not_counted_as_a_non_member():
    """A match with no recorded formation must not be treated as 'a different formation'."""
    recorded = _obs(8, 7.0, dims={"own_formation_family": "BACK_THREE"})
    unrecorded = _obs(12, 5.0, dims={}, end=F.CUTOFF - 30 * 86_400)
    res = M.execute(_plan([Condition("own_formation_family", "BACK_THREE")]),
                    subject_team="T", history=_History(recorded + unrecorded))
    assert res.conditional.usable_n == 8
    assert any("missing data is not evidence of difference" in n for n in res.notes)
    cov = res.dimension_coverage["own_formation_family"]
    assert cov == {"candidate_n": 20, "usable_n": 8, "missing_n": 12, "coverage_rate": 0.4}


def test_leaked_observation_refuses_to_measure():
    leaked = [M.Observation("future", F.CUTOFF + 1, 9.0, {})]
    res = M.execute(_plan(), subject_team="T",
                    history=_History(_obs(20, 5.0) + leaked))
    assert res.status == lifecycle.LEAKAGE_REJECTED
    assert res.difference is None


def test_window_slicing_respects_w5_and_w10():
    hist = _History(_obs(30, 5.0))
    assert M.execute(_plan(window="W5"), subject_team="T",
                     history=hist).baseline.usable_n == 5
    assert M.execute(_plan(window="W10"), subject_team="T",
                     history=hist).baseline.usable_n == 10


def test_measurement_result_contains_no_probability_or_market_field():
    hist = _History(_obs(10, 7.0, dims={"venue": "HOME"})
                    + _obs(20, 5.0, dims={"venue": "AWAY"}, end=F.CUTOFF - 30 * 86_400))
    d = M.execute(_plan([Condition("venue", "HOME")]),
                  subject_team="T", history=hist).to_dict()
    flat = str(d).lower()
    for banned in ("probability", "p_model", "odds", "edge", "expected_value",
                   "implied", "stake"):
        assert banned not in flat
