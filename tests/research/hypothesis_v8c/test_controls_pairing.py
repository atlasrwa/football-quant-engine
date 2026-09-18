"""Arm R distinctness and pairing, arm H universe parity, invalid-ID handling."""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import controls as CTL
from src.research.hypothesis_v8c import select_freeze as SF
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GRAMMAR_KW


def _shapes(fu, k):
    return [CTL.shape_of(c) for c in fu.evaluable[:k]]


def test_r_is_never_the_paired_sonnet_hypothesis(golden_universe):
    out = CTL.blind_selections_for_fixture(_shapes(golden_universe, 8), golden_universe)
    assert out["identity_count"] == 0
    for p in out["pairs"]:
        if p["r_id"] is not None:
            assert p["r_id"] != p["s_id"]


def test_r_never_selects_any_sonnet_treated_hypothesis(golden_universe):
    """The V8C-v1 hole: excluding only the PAIRED id let R return a DIFFERENT Sonnet pick."""
    shapes = _shapes(golden_universe, 8)
    sonnet_ids = {s.hypothesis_id for s in shapes}
    out = CTL.blind_selections_for_fixture(shapes, golden_universe)
    assert out["cross_treatment_overlap_count"] == 0
    for p in out["pairs"]:
        assert p["r_id"] not in sonnet_ids


def test_r_controls_are_mutually_distinct(golden_universe):
    out = CTL.blind_selections_for_fixture(_shapes(golden_universe, 8), golden_universe)
    rids = [p["r_id"] for p in out["pairs"] if p["r_id"]]
    assert len(rids) == len(set(rids)), "the same control was reused within a fixture"


def test_r_emits_the_pair_triple_with_a_tier(golden_universe):
    out = CTL.blind_selections_for_fixture(_shapes(golden_universe, 5), golden_universe)
    for p in out["pairs"]:
        assert set(p) >= {"s_id", "r_id", "tier", "status"}
        assert p["tier"] in CTL.RELAXATION_TIERS


def test_r_fails_unmatched_rather_than_fabricating():
    """With a universe of ONE candidate there is no distinct control; R must say so."""
    class _Tiny:
        evaluable = ()
    only = CTL.SonnetShape(hypothesis_id="x", target_metric="goals", subject="HOME_TEAM",
                           perspective="FOR", comparator="SUBJECT_OVERALL_BASELINE",
                           window="ALL_PRIOR", n_conditions=0, condition_family="NONE",
                           uses_similarity=False, capability_status="SUPPORTED")
    out = CTL.blind_selections_for_fixture([only], _Tiny())
    assert out["n_matched"] == 0
    assert out["n_unmatched"] == 1
    assert out["pairs"][0]["status"] == CTL.UNMATCHED_DISTINCT_CONTROL
    assert out["pairs"][0]["r_id"] is None


def test_r_matches_the_declared_nuisance_dimensions(golden_universe):
    """An EXACT-tier match must agree on every never-relaxed dimension."""
    shapes = _shapes(golden_universe, 12)
    out = CTL.blind_selections_for_fixture(shapes, golden_universe)
    by_id = {c["hypothesis_id"]: c for c in golden_universe.evaluable}
    for s, p in zip(shapes, out["pairs"]):
        if p["r_id"] is None:
            continue
        r = by_id[p["r_id"]]
        assert r["target_metrics"][0] == s.target_metric
        assert r["subject"] == s.subject
        assert r["comparator"] == s.comparator
        assert bool(r["complexity"]["uses_similarity"]) == s.uses_similarity


def test_h_ranks_over_the_whole_evaluable_universe(golden_universe):
    out = CTL.heuristic_selections_for_fixture(3, golden_universe)
    assert out["n_ranked_over"] == golden_universe.n_evaluable
    assert out["n_selected"] == 3


def test_h_picks_the_true_argmax_not_the_first_page(golden_universe):
    """The V8B.1 defect: H ranked over search(max_results=50), i.e. the 50 lowest ir_ids."""
    out = CTL.heuristic_selections_for_fixture(1, golden_universe)
    best = max(CTL.heuristic_score(c) for c in golden_universe.evaluable)
    assert out["selections"][0]["heuristic_score"] == best


def test_h_selections_are_all_in_the_shared_universe(golden_universe):
    ids = set(golden_universe.evaluable_ids())
    out = CTL.heuristic_selections_for_fixture(5, golden_universe)
    for c in out["selections"]:
        assert c["hypothesis_id"] in ids


def test_h_formula_is_the_frozen_one():
    from src.research.hypothesis_v8b1 import controls as V8B1C
    assert CTL.heuristic_score is V8B1C.heuristic_score
    assert CTL.version_stamp()["h_formula_changed"] is False


def test_invalid_sonnet_id_is_an_explicit_terminal_state(golden_env):
    """P1 INVALID-S: no silent `continue`."""
    def selector(fu):
        return [fu.evaluable[0]["hypothesis_id"], "mt_NOT_A_REAL_ID"]

    payload = SF.select_cohort(golden_env.index, [golden_env.target_pos],
                               capability=golden_env.capability, s_selector=selector,
                               fixture_ids=[golden_env.target_fixture_id],
                               grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    row = payload["selections"][0]
    assert row["n_submitted"] == 2
    assert row["k_valid"] == 1
    assert len(row["S_invalid"]) == 1
    assert row["S_invalid"][0]["status"] == SF.INVALID_UNKNOWN_HYPOTHESIS_ID
    assert payload["totals"]["S_invalid_count"] == 1


def test_pair_identities_survive_into_the_freeze(golden_env):
    payload = SF.select_cohort(golden_env.index, [golden_env.target_pos],
                               capability=golden_env.capability, k=4,
                               fixture_ids=[golden_env.target_fixture_id],
                               grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    row = payload["selections"][0]
    assert row["R_pairs"], "the freeze lost the pair triples"
    for p in row["R_pairs"]:
        assert set(p) == {"s_id", "r_id", "tier", "status"}
    assert [p["s_id"] for p in row["R_pairs"]] == row["S"]
    assert payload["totals"]["R_identity_count"] == 0
    assert payload["totals"]["R_cross_treatment_overlap_count"] == 0
