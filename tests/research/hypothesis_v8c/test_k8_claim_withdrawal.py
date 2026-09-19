"""AUDIT FINDING 6: the K=8 set-level claim is withdrawn, and the successor is honest.

The v1 rehearsal reported `R_SET_LEVEL_K8_FEASIBLE = true`, but every one of the 50 S-sets it
tested contained FOUR ids. A result about 4-element sets was published under a name asserting
8. These tests pin the withdrawal and the precise replacement claim.
"""
from __future__ import annotations

import json
import os

import pytest

from src.research.hypothesis_v8c import control_coverage as CC

ENG = "/home/ubuntu/research/hypothesis_engine"
V1 = f"{ENG}/V8C_EXPOSED50_REHEARSAL.json"
V2 = f"{ENG}/V8C_R_ACTION_SPACE_COVERAGE_V2.json"


def _v2():
    if not os.path.exists(V2):
        pytest.skip("successor coverage artifact not present in this checkout")
    return json.load(open(V2))


def test_v1_artifact_is_preserved_unedited():
    """Frozen evidence is immutable: the flawed claim stays on the record."""
    if not os.path.exists(V1):
        pytest.skip("v1 artifact not present")
    v1 = json.load(open(V1))
    assert v1["R_SET_LEVEL_K8_FEASIBLE"] is True, (
        "the v1 artifact must be left exactly as it was published")
    assert {r["s_k"] for r in v1["per_fixture"]} == {4}, (
        "the v1 sets were all k=4 -- that is the whole reason the claim is withdrawn")


def test_successor_withdraws_the_k8_claim():
    d = _v2()
    w = d["WITHDRAWAL"]
    assert w["withdrawn_claim"] == "R_SET_LEVEL_K8_FEASIBLE = true"
    assert w["corrected_status"].startswith("OPEN")
    assert d["R_SET_LEVEL_K8_FEASIBLE"] is False


def test_successor_does_not_overclaim_infeasibility():
    """Hall's minimum-degree test is SUFFICIENT, not necessary. Failing it proves nothing."""
    d = _v2()
    assert "not necessary" in d["WITHDRAWAL"]["what_is_NOT_claimed"]
    assert "INFEASIBLE" in d["WITHDRAWAL"]["what_is_NOT_claimed"]


def test_proof_is_over_the_whole_action_space_not_a_probe():
    d = _v2()
    assert d["is_probe_not_proof"] is False
    assert d["n_fixtures"] == 50
    assert d["COVERAGE_REPORT"]["scope"].startswith("every evaluable candidate")


def test_single_candidate_coverage_is_reported_over_the_whole_space():
    d = _v2()
    c = d["COVERAGE_REPORT"]
    assert c["R_SINGLE_CANDIDATE_COVERAGE_WHOLE_ACTION_SPACE"] == 1.0
    assert c["candidates_with_no_distinct_control"] == 0


def test_shortfall_structures_are_named():
    d = _v2()
    s = d["COVERAGE_REPORT"]["degree_shortfall_structures"]
    assert s["n_distinct_classes"] > 0
    for dim in ("metric", "comparator", "window", "condition_family"):
        assert s["dimensions_touched"][dim], f"{dim} coverage not reported"
    assert s["worst_10"], "the worst shortfall structures must be named"


def test_no_silent_action_space_shrink_or_threshold_relaxation():
    d = _v2()
    assert d["action_space_shrunk"] is False
    assert d["support_thresholds_relaxed"] is False


def test_hall_threshold_arithmetic_is_right():
    """deg >= 2k-1 is what makes min|O_i| >= k, hence Hall for every subset."""
    d = _v2()
    assert d["required_min_degree_for_k8"] == 2 * CC.MAX_SELECTIONS - 1 == 15
    assert d["K_UNIVERSALLY_PROVEN"] == (d["overall_min_degree"] + 1) // 2
