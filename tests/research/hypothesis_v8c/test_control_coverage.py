"""Gate-A Phase 6: R action-space coverage, single-candidate AND set-level at K=8."""
from __future__ import annotations

from src.research.hypothesis_v8c import control_coverage as CC
from src.research.hypothesis_v8c import controls as CTL


def test_single_candidate_coverage_is_computed_over_every_candidate(golden_universe):
    rep = CC.single_candidate_coverage(golden_universe)
    assert rep["n_s_addressable_candidates"] == golden_universe.n_evaluable
    assert (rep["n_with_distinct_control"] + rep["n_without_distinct_control"]
            == rep["n_s_addressable_candidates"])
    assert 0.0 <= rep["coverage_rate"] <= 1.0
    assert rep["exact_tier_coverage"] + rep["relaxed_tier_coverage"] \
        == rep["n_with_distinct_control"]


def test_set_level_uses_maximum_matching_not_greedy(golden_universe):
    ids = list(golden_universe.evaluable_ids())[:8]
    rep = CC.set_level_feasibility(golden_universe, [ids])
    row = rep["sets"][0]
    assert row["k"] == len(ids)
    assert row["max_matching_size"] >= row["greedy_matched"], (
        "greedy beat the maximum matching, which is impossible")
    assert rep["method"].startswith("maximum bipartite matching")


def test_k8_feasibility_is_reported_and_controls_are_never_s_ids(golden_universe):
    rep = CC.audit_fixture(golden_universe)
    assert rep["R_SET_LEVEL_K8_FEASIBLE"] in (True, False)
    assert rep["uses_first_four_proxy"] is False
    assert rep["s_set_provenance"], "the tested S-sets must be stated"
    for row in rep["set_level"]["sets"]:
        assert row["greedy_identity_count"] == 0
        assert row["greedy_cross_treatment_overlap_count"] == 0


def test_admissible_controls_exclude_the_shape_itself(golden_universe):
    cand = golden_universe.evaluable[0]
    shape = CTL.shape_of(cand)
    adm = CC.admissible_controls(shape, golden_universe)
    assert all(hid != shape.hypothesis_id for hid, _t, _i in adm)


def test_max_matching_beats_greedy_on_a_constructed_conflict():
    """A hand-built bipartite case where greedy fails but a perfect matching exists.

    s1 can only take c1; s2 can take c1 or c2. Greedy in the order (s2, s1) takes c1 for s2
    and strands s1. Maximum matching pairs both.
    """
    options = {"s2": ["c1", "c2"], "s1": ["c1"]}
    best = CC._max_matching(["s2", "s1"], options)
    assert len(best) == 2, f"maximum matching missed a perfect matching: {best}"
    assert set(best.values()) == {"c1", "c2"}
