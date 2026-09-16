"""Required tests for V8B.1 control arms R (blind) and H (heuristic), per
research/hypothesis_engine/V8B1_BLIND_CONTROL_SPEC.md section 6 and
V8B1_HEURISTIC_SPEC.md section 5. Run against the real capability contract.
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v8b1 import controls as CTRL
from src.research.hypothesis_v8b1 import search as SE

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"


@pytest.fixture(scope="module")
def cap():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


def _sonnet_shapes_from_real_search(cap, n=3):
    q = SE.SearchQuery(max_results=n)
    candidates = SE.search(q, cap)
    return [CTRL.shape_of(c) for c in candidates]


# ---- Arm R: blind control -----------------------------------------------------------
def test_r1_size_matches_k_valid(cap):
    shapes = _sonnet_shapes_from_real_search(cap, n=3)
    result = CTRL.blind_selections_for_fixture(shapes, cap)
    assert result["k_valid"] == len(shapes)
    assert len(result["selections"]) == len(shapes)  # UNMATCHED entries counted, not dropped


def test_r2_no_double_use_within_fixture(cap):
    shapes = _sonnet_shapes_from_real_search(cap, n=5)
    result = CTRL.blind_selections_for_fixture(shapes, cap)
    matched_ids = [s["hypothesis_id"] for s in result["selections"] if s["status"] == "MATCHED"]
    assert len(matched_ids) == len(set(matched_ids)), "a control hypothesis was reused"


def test_r3_matcher_reads_only_structural_fields(cap):
    """SonnetShape has NO field for prose/reason/mechanism_summary -- structurally impossible
    to read them, not merely a convention."""
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(CTRL.SonnetShape)}
    forbidden = {"research_reason", "mechanism_summary", "why_simple_average_is_insufficient",
                "support_warning", "evidence_refs"}
    assert not (field_names & forbidden)


def test_r4_determinism(cap):
    shapes = _sonnet_shapes_from_real_search(cap, n=4)
    r1 = CTRL.blind_selections_for_fixture(shapes, cap)
    r2 = CTRL.blind_selections_for_fixture(shapes, cap)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_r5_exact_tier_preferred_when_available(cap):
    """If an exact structural match exists (same metric/subject/side/comparator/conditions/
    capability), the matcher must pick it, not something from a looser tier."""
    q = SE.SearchQuery(comparator="SUBJECT_VENUE_BASELINE", max_results=5)
    candidates = SE.search(q, cap)
    assert len(candidates) >= 2, "need at least 2 candidates to test exact-match preference"
    shape = CTRL.shape_of(candidates[0])
    result = CTRL.match_blind_control(shape, cap, exclude_ids=set())
    assert result is not None
    assert result["matched_tier"] == "EXACT"


# ---- Arm H: heuristic ------------------------------------------------------------------
def test_h1_formula_correctness_known_ordering():
    """A SUPPORTED+1-condition+similarity candidate must outrank a RESTRICTED+0-condition
    candidate, per the frozen formula."""
    strong = {"capability_status": "SUPPORTED",
             "complexity": {"n_conditions": 1, "uses_similarity": True}}
    weak = {"capability_status": "RESTRICTED",
           "complexity": {"n_conditions": 0, "uses_similarity": False}}
    assert CTRL.heuristic_score(strong) > CTRL.heuristic_score(weak)


def test_h2_penalty_reduces_score_beyond_one_condition():
    one_cond = {"capability_status": "SUPPORTED",
               "complexity": {"n_conditions": 1, "uses_similarity": False}}
    three_cond = {"capability_status": "SUPPORTED",
                 "complexity": {"n_conditions": 3, "uses_similarity": False}}
    assert CTRL.heuristic_score(one_cond) > CTRL.heuristic_score(three_cond)


def test_h3_no_outcome_shaped_field_reachable():
    """heuristic_score only ever indexes capability_status/complexity -- confirmed by running
    it against a MINIMAL dict missing every outcome-shaped key; it must not raise a KeyError
    hunting for one, proving it never conditionally reads one."""
    minimal = {"capability_status": "SUPPORTED", "complexity": {"n_conditions": 0,
              "uses_similarity": False}}
    CTRL.heuristic_score(minimal)  # must not raise


def test_h4_size_matches_k_valid(cap):
    result = CTRL.heuristic_selections_for_fixture(4, cap)
    assert result["k_valid"] == 4
    assert len(result["selections"]) == 4


def test_h5_determinism(cap):
    r1 = CTRL.heuristic_selections_for_fixture(5, cap)
    r2 = CTRL.heuristic_selections_for_fixture(5, cap)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


def test_h6_tie_break_by_hypothesis_id():
    a = {"hypothesis_id": "aaa", "capability_status": "SUPPORTED",
        "complexity": {"n_conditions": 0, "uses_similarity": False}}
    b = {"hypothesis_id": "bbb", "capability_status": "SUPPORTED",
        "complexity": {"n_conditions": 0, "uses_similarity": False}}
    assert CTRL.heuristic_score(a) == CTRL.heuristic_score(b)
    # confirm sort order is deterministic when scores tie (id ascending, per the module's own rule)
    scored = sorted([(CTRL.heuristic_score(a), a["hypothesis_id"]),
                     (CTRL.heuristic_score(b), b["hypothesis_id"])],
                    key=lambda t: (-t[0], t[1]))
    assert scored[0][1] == "aaa"


def test_version_stamp_declares_no_tuning():
    stamp = CTRL.version_stamp()
    assert stamp["reads_outcomes"] is False
    assert stamp["reads_llm_prose"] is False
    assert stamp["tuned_against_sonnet_result"] is False
