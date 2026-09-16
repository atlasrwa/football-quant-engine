"""Required tests for the V8B.1 hypothesis search interface, per
research/hypothesis_engine/V8B1_HYPOTHESIS_SEARCH_SPEC.md section 5. Run against the REAL
capability contract (structural only -- no outcome is read by doing so).
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v8b1 import search as SE

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"


@pytest.fixture(scope="module")
def cap():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


def test_1_no_outcome_field_ever_appears(cap):
    """Structural denylist test, not a manual review: scan every candidate's keys (and its
    nested dicts) for anything on the forbidden list."""
    q = SE.SearchQuery(target_metric="shots", max_results=50)
    results = SE.search(q, cap)
    assert results, "expected at least one candidate for an unrestricted 'shots' query"
    for candidate in results:
        keys = set(candidate.keys()) | set(candidate.get("complexity", {}).keys())
        forbidden_hit = keys & SE.FORBIDDEN_OUTCOME_FIELDS
        assert not forbidden_hit, f"forbidden field(s) {forbidden_hit} leaked into {candidate}"


def test_2_determinism_same_query_same_result():
    cap1 = CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))
    cap2 = CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))
    q = SE.SearchQuery(comparator="SIMILAR_OPPONENT_COHORT", max_results=10)
    r1 = SE.search(q, cap1)
    r2 = SE.search(q, cap2)
    assert r1 == r2
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_3a_comparator_filter_is_exact(cap):
    q = SE.SearchQuery(comparator="SIMILAR_OPPONENT_COHORT", max_results=20)
    results = SE.search(q, cap)
    assert results
    assert all(r["comparator"] == "SIMILAR_OPPONENT_COHORT" for r in results)


def test_3b_max_conditions_zero_returns_only_unconditional(cap):
    q = SE.SearchQuery(max_conditions=0, max_results=20)
    results = SE.search(q, cap)
    assert results
    assert all(len(r["conditions"]) == 0 for r in results)


def test_3c_subject_filter_is_exact(cap):
    q = SE.SearchQuery(subject="AWAY_TEAM", max_results=20)
    results = SE.search(q, cap)
    assert results
    assert all(r["subject"] == "AWAY_TEAM" for r in results)


def test_3d_side_filter_is_exact(cap):
    q = SE.SearchQuery(side="AGAINST", max_results=20)
    results = SE.search(q, cap)
    assert results
    assert all(r["side"] == "AGAINST" for r in results)


def test_3e_venue_filter_is_exact(cap):
    q = SE.SearchQuery(venue="HOME", max_results=20)
    results = SE.search(q, cap)
    assert results
    for r in results:
        assert any(c.get("dimension") == "historical_venue_conditioning"
                   and c.get("value") == "HOME" for c in r["conditions"])


def test_3f_mechanism_type_filter_maps_to_expected_comparator(cap):
    q = SE.SearchQuery(mechanism_type="similar_opponent", max_results=20)
    results = SE.search(q, cap)
    assert results
    assert all(r["comparator"] == "SIMILAR_OPPONENT_COHORT" for r in results)


def test_3g_opponent_profile_dimension_filter_is_exact(cap):
    q = SE.SearchQuery(opponent_profile_dimension="shots_against", max_results=20)
    results = SE.search(q, cap)
    assert results
    for r in results:
        assert any(c.get("dimension") == "opponent_profile"
                   and c.get("axis") == "shots_against" for c in r["conditions"])


def test_4_canonical_id_round_trips_to_same_ir_id(cap):
    q = SE.SearchQuery(target_metric="shots_on_target", max_results=5)
    results = SE.search(q, cap)
    assert results
    for r in results:
        resolved = SE.resolve(r["hypothesis_id"], cap)
        assert resolved is not None, f"hypothesis_id {r['hypothesis_id']} did not resolve"
        assert resolved.ir_id() == r["hypothesis_id"]


def test_max_results_hard_cap_enforced(cap):
    q = SE.SearchQuery(max_results=10_000)
    results = SE.search(q, cap)
    assert len(results) <= SE.MAX_RESULTS_HARD_CAP


def test_unresolvable_id_returns_none(cap):
    assert SE.resolve("not_a_real_hypothesis_id", cap) is None


def test_version_stamp_declares_no_outcomes():
    stamp = SE.version_stamp()
    assert stamp["reads_outcomes"] is False
    assert stamp["deterministic"] is True
