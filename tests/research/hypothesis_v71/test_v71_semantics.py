"""V7.1 sections 7 and 8: golden semantic round-trip + adversarial property/mutation tests.

These are the load-bearing regression suite for the defect class that invalidated most of V7:
a structured hypothesis whose compiled query did not test the football question it stated.

Every assertion is structural. Nothing here reads an effect, a p-value or an OOS outcome.
Negative controls prove each check can actually fail.
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import golden as G
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import ontology as ONT

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"


@pytest.fixture(scope="module")
def cap():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


def _ir(case):
    return IRM.build_ir(case["spec"],
                        temporal_resolution=case.get("temporal_resolution", "MATCH"))


def _spec(**kw):
    base = {"target_metrics": ["total_shots"], "subject": "HOME_TEAM", "side": "FOR",
            "comparison": "SUBJECT_OVERALL_BASELINE", "conditions": [],
            "window": "ALL_PRIOR", "research_family": "ATTACK_VOLUME",
            "required_capabilities": []}
    base.update(kw)
    return base


PROFILE = {"dimension": "opponent_profile", "axis": "goals_against", "value": "HIGH"}


# =======================================================================================
# Section 7 -- golden semantic round trip
# =======================================================================================
@pytest.mark.parametrize("case", G.GOLDEN_CASES, ids=[c["name"] for c in G.GOLDEN_CASES])
def test_07_golden_round_trip(case, cap):
    """meaning -> spec -> IR -> compiled selectors -> reconstructed meaning."""
    ir = _ir(case)
    assert ir.status == case["expect_status"], (case["name"], ir.status, ir.reasons)
    res = INV.check(ir, capability=cap)
    assert set(res["codes"]) == set(case["expect_codes"]), (case["name"], res["codes"])
    desc = ir.describe()
    for must in case["must_say"]:
        assert must in desc, (case["name"], must, desc)
    for forbidden in case["must_not_say"]:
        assert forbidden not in desc, (case["name"], forbidden, desc)
    if case.get("expect_capability"):
        status, _adm, _d = cap.classify_metrics(ir.target_metrics)
        assert status == case["expect_capability"], (case["name"], status)


def test_07_golden_corpus_covers_the_grammar():
    """The corpus must exercise the whole football grammar, not just the easy half."""
    blob = json.dumps(G.GOLDEN_CASES).lower()
    for token in ("shots", "shots_on_target", "blocked_shots", "corners", "crosses",
                  "possession", "cards", "tackles", "fouls", "xg",
                  "historical_venue_conditioning", "opponent_formation_family",
                  "subject_recent_vs_long_baseline", "similar_opponent_cohort",
                  "opponent_profile", "cards_2h", "competition"):
        assert token in blob, f"golden corpus never exercises {token}"


def test_07_golden_has_live_negative_controls():
    """At least one case per structural failure family, so the suite can fail."""
    codes = {c for case in G.GOLDEN_CASES for c in case["expect_codes"]}
    for required in (INV.IDENTICAL_COHORT_BASELINE, INV.SELF_COMPARISON,
                     INV.BASELINE_ABSORPTION, INV.UNSUPPORTED_FILTER_DIMENSION,
                     INV.TEMPORAL_RESOLUTION_UNSUPPORTED, INV.UNSUPPORTED_METRIC,
                     INV.UNKNOWN_PROVIDER_SEMANTICS):
        assert required in codes, f"no golden negative control for {required}"


def test_07_the_v7_bug_class_reconstructs_as_a_non_question(cap):
    """The exact V7 failure: a subject-vs-opponent question arriving with no structural
    field able to express the opponent side reconstructs as subject-vs-itself and is
    REJECTED, rather than silently measured as a zero-valued feature."""
    ir = IRM.build_ir(_spec(target_metrics=["total_shots"], side="AGAINST"))
    assert ir.cohort.key() == ir.baseline.key()
    res = INV.check(ir, capability=cap)
    assert INV.IDENTICAL_COHORT_BASELINE in res["codes"]
    with pytest.raises(INV.InvariantViolation):
        INV.assert_valid(ir, capability=cap)


def test_07_cross_entity_comparator_is_expressible_now(cap):
    """The same football question, expressed with the comparator V7.1 adds, is measurable
    and reconstructs as a genuine cross-entity contrast."""
    ir = IRM.build_ir(_spec(side="AGAINST", comparison="SUBJECT_VS_FIXTURE_OPPONENT"))
    assert INV.check(ir, capability=cap)["ok"]
    assert ir.cohort.entity_role == "SUBJECT"
    assert ir.baseline.entity_role == "FIXTURE_OPPONENT"
    assert "the fixture opponent's concession" in ir.describe()


# =======================================================================================
# Section 8 -- property and mutation tests
# =======================================================================================
def test_08_swap_subject_opponent_changes_the_question():
    a = IRM.build_ir(_spec(subject="HOME_TEAM", comparison="SUBJECT_VS_FIXTURE_OPPONENT"))
    b = IRM.build_ir(_spec(subject="AWAY_TEAM", comparison="SUBJECT_VS_FIXTURE_OPPONENT"))
    assert a.ir_id() != b.ir_id()


def test_08_swap_for_against_changes_the_question():
    a = IRM.build_ir(_spec(side="FOR", conditions=[PROFILE]))
    b = IRM.build_ir(_spec(side="AGAINST", conditions=[PROFILE]))
    assert a.ir_id() != b.ir_id()
    assert a.cohort.perspective != b.cohort.perspective
    assert "production" in a.describe() and "concession" in b.describe()


def test_08_changing_the_opponent_profile_changes_the_cohort():
    hi = IRM.build_ir(_spec(conditions=[PROFILE]))
    lo = IRM.build_ir(_spec(conditions=[dict(PROFILE, value="LOW")]))
    assert hi.cohort.key() != lo.cohort.key()
    ax = IRM.build_ir(_spec(conditions=[dict(PROFILE, axis="goals_for")]))
    assert hi.cohort.key() != ax.cohort.key()


def test_08_duplicate_condition_canonicalises_deterministically():
    once = IRM.build_ir(_spec(conditions=[PROFILE]))
    twice = IRM.build_ir(_spec(conditions=[PROFILE, dict(PROFILE)]))
    assert once.ir_id() == twice.ir_id()
    assert "duplicate:opponent_profile=HIGH" in twice.dropped_non_restrictive


def test_08_a_hand_built_duplicate_selector_is_still_rejected(cap):
    """Defense in depth: normalisation canonicalises duplicates away, but a caller that
    constructs a Selector directly must still be caught rather than trusted."""
    good = IRM.build_ir(_spec(conditions=[PROFILE]))
    f = good.cohort.filters[0]
    broken = IRM.IR(good.target_metrics, good.subject, good.perspective, good.comparator,
                    IRM.Selector(good.cohort.entity_role, good.cohort.perspective,
                                 (f, f), good.cohort.window, good.cohort.weighting),
                    good.baseline, good.temporal_resolution, good.provider_requirements,
                    good.research_family, IRM.OK)
    assert INV.DUPLICATED_CONDITION in INV.check(broken, capability=cap)["codes"]


def test_08_condition_order_does_not_change_identity():
    venue = {"dimension": "historical_venue_conditioning", "value": "HOME"}
    a = IRM.build_ir(_spec(conditions=[PROFILE, venue]))
    b = IRM.build_ir(_spec(conditions=[venue, PROFILE]))
    assert a.ir_id() == b.ir_id()


def test_08_removing_the_condition_changes_the_comparator_semantics(cap):
    with_cond = IRM.build_ir(_spec(conditions=[PROFILE]))
    without = IRM.build_ir(_spec(conditions=[]))
    assert with_cond.ir_id() != without.ir_id()
    assert INV.check(with_cond, capability=cap)["ok"]
    assert INV.IDENTICAL_COHORT_BASELINE in INV.check(without, capability=cap)["codes"]


def test_08_non_restrictive_value_is_not_a_condition(cap):
    """`ANY` must never make a degenerate comparator look conditioned. This is the defect
    that let 25 raw V6.1 hypotheses bypass V7's degeneracy fast path."""
    ir = IRM.build_ir(_spec(conditions=[{"dimension": "competition", "value": "ANY"},
                                        {"dimension": "historical_venue_conditioning",
                                         "value": "ANY"}]))
    assert ir.cohort.filters == ()
    assert set(ir.dropped_non_restrictive) == {"competition=ANY",
                                               "historical_venue_conditioning=ANY"}
    assert INV.IDENTICAL_COHORT_BASELINE in INV.check(ir, capability=cap)["codes"]


def test_08_unsupported_dimension_fails_closed_not_empty(cap):
    """An unsupported restriction must be NAMED, never compiled to an empty cohort that is
    downstream indistinguishable from a no-support hypothesis (V7's `_apply_conditions`)."""
    ir = IRM.build_ir(_spec(conditions=[{"dimension": "own_formation_family",
                                         "value": "BACK_FOUR"}]))
    assert ir.status == IRM.UNSUPPORTED_FILTER_DIMENSION
    assert ir.cohort is None and ir.baseline is None
    assert "own_formation_family" in " ".join(ir.reasons)


def test_08_cohort_equal_to_baseline_is_rejected(cap):
    for comparator in ("SUBJECT_OVERALL_BASELINE", "SUBJECT_COMPETITION_BASELINE"):
        spec = _spec(comparison=comparator,
                     conditions=([{"dimension": "competition", "value": "SAME"}]
                                 if comparator == "SUBJECT_COMPETITION_BASELINE" else []))
        ir = IRM.build_ir(spec)
        if ir.status != IRM.OK:
            continue
        if ir.cohort.key() == ir.baseline.key():
            assert INV.IDENTICAL_COHORT_BASELINE in INV.check(ir, capability=cap)["codes"]


def test_08_every_declared_comparator_binds_two_selectors():
    """V7 declared nine comparator semantics and its executor branched on two, falling through
    to a generic subject-vs-subject contrast for the rest. Every declared comparator must now
    bind an explicit selector PAIR."""
    for name, binding in ONT.COMPARATOR_BINDINGS.items():
        assert "cohort" in binding and "baseline" in binding, name
        for side in ("cohort", "baseline"):
            sel = binding[side]
            assert sel["role"] in ONT.ENTITY_ROLES, (name, side)
            assert sel["window"] in ONT.WINDOWS + ("SPEC_WINDOW",), (name, side)
            assert sel["weighting"] in ONT.WEIGHTINGS, (name, side)


def test_08_comparators_produce_distinct_structures():
    """Two different comparators on the same hypothesis must not collapse to one query."""
    seen = {}
    for name in ONT.COMPARATOR_BINDINGS:
        spec = _spec(comparison=name, conditions=[PROFILE],
                     required_capabilities=["opponent_profile", "similar_opponents"])
        ir = IRM.build_ir(spec)
        if ir.status != IRM.OK:
            continue
        key = (ir.cohort.key(), ir.baseline.key())
        assert key not in seen, f"{name} compiles identically to {seen[key]}"
        seen[key] = name


# ---- provider provenance --------------------------------------------------------------
def test_08_storage_block_is_never_provider_identity(cap):
    cap.assert_block_is_not_provider()
    for metric in ("goals", "corner_kicks", "shots"):
        assert cap.provider_of(metric) == CAP.CORPUS_PROVIDER
        assert cap.storage_block_of(metric) in CAP.STORAGE_BLOCKS
    assert len({cap.provider_of(m) for m in ("goals", "corner_kicks", "shots")}) == 1


def test_08_renaming_storage_blocks_does_not_change_provenance(cap):
    """Mutation: the three storage blocks map to ONE provider however they are named."""
    providers = {cap.provider_of(m) for m in CAP.METRIC_SEMANTICS
                 if CAP.METRIC_SEMANTICS[m].get("block")}
    assert providers == {CAP.CORPUS_PROVIDER}


def test_08_pooling_guard_fires_only_on_a_real_cross_provider_corpus(cap):
    assert cap.pooling_guard(["thestatsapi"])["fired"] is False
    fired = cap.pooling_guard(["thestatsapi", "footystats"])
    assert fired["fired"] is True and fired["hazards"], "negative control did not fire"


# ---- capability -----------------------------------------------------------------------
def test_08_unsupported_xg_league_is_restricted_not_silently_full(cap):
    status, detail = cap.classify_metric("xg")
    assert status == CAP.RESTRICTED
    adm = cap.admissible_competitions("xg")
    assert "ligue2" not in adm and "laliga2" not in adm
    assert len(adm) >= cap.policy["min_admissible_competitions"]


def test_08_supported_metric_is_accepted_everywhere(cap):
    status, _ = cap.classify_metric("shots")
    assert status == CAP.SUPPORTED
    assert set(cap.admissible_competitions("shots")) == set(cap.competitions)


def test_08_unknown_is_not_unsupported(cap):
    assert cap.classify_metric("progressive_carries")[0] == CAP.UNKNOWN
    assert cap.classify_metric("np_xg")[0] == CAP.UNSUPPORTED


def test_08_multi_metric_universe_is_the_intersection(cap):
    adm = cap.admissible_universe(["xg", "touches_in_penalty_area"])
    assert adm == cap.admissible_competitions("xg") & \
        cap.admissible_competitions("touches_in_penalty_area")


def test_08_half_level_request_on_match_metric_is_refused(cap):
    match_level = IRM.build_ir(_spec(comparison="SUBJECT_RECENT_VS_LONG_BASELINE"),
                               temporal_resolution="HALF")
    assert INV.TEMPORAL_RESOLUTION_UNSUPPORTED in INV.check(match_level,
                                                            capability=cap)["codes"]
    half_level = IRM.build_ir(_spec(target_metrics=["cards_2h"],
                                    comparison="SUBJECT_RECENT_VS_LONG_BASELINE"),
                              temporal_resolution="HALF")
    assert INV.TEMPORAL_RESOLUTION_UNSUPPORTED not in INV.check(half_level,
                                                                capability=cap)["codes"]


# ---- canonical identity ---------------------------------------------------------------
def test_08_same_semantics_different_prose_is_one_identity():
    a = _spec(target_metrics=["total_shots"])
    b = _spec(target_metrics=["shots"])
    a["question"] = "Does the home side shoot a lot?"
    b["question"] = "Is the home team's shot volume elevated?"
    assert IRM.build_ir(a).ir_id() == IRM.build_ir(b).ir_id()


def test_08_different_semantics_is_a_different_identity():
    base = IRM.build_ir(_spec())
    for mutation in (dict(side="AGAINST"), dict(window="W5"),
                     dict(comparison="SUBJECT_RECENT_VS_LONG_BASELINE"),
                     dict(subject="AWAY_TEAM"), dict(target_metrics=["corners"]),
                     dict(conditions=[PROFILE])):
        assert IRM.build_ir(_spec(**mutation)).ir_id() != base.ir_id(), mutation


def test_08_ir_identity_is_stable_across_processes():
    """The id is a SHA-256 of a sorted canonical dict, never Python's salted hash()."""
    ir = IRM.build_ir(_spec(conditions=[PROFILE]))
    assert ir.ir_id() == IRM.build_ir(_spec(conditions=[PROFILE])).ir_id()
    assert len(ir.ir_id()) == 64 and int(ir.ir_id(), 16) >= 0


def test_08_ir_never_reads_prose():
    """Two hypotheses with opposite prose but identical structure are ONE question. This is
    what stops a post-hoc prose reinterpretation from rescuing a degenerate comparator."""
    a = _spec(question="Does the subject score MORE than its baseline?")
    b = _spec(question="Does the subject score LESS than its baseline?")
    assert IRM.build_ir(a).ir_id() == IRM.build_ir(b).ir_id()
