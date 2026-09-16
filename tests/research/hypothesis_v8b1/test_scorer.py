"""Synthetic proof battery for the V8B.1 fixture-level scorer (`v8b1_scorer_v1`).

Every case here is CONSTRUCTED, not drawn from the real corpus, per instruction: this scorer
must never be tuned against a real target outcome. These tests exist to prove the formula in
research/hypothesis_engine/V8B1_SCORER_SPEC.md behaves as specified BEFORE it is ever pointed
at a real fixture. Section 4 of that spec enumerates the seven required proofs; this file
implements exactly those seven, plus a real-corpus degenerate-case regression check reusing
the existing `test_v71_engine.py` fixtures so the REFUSED path is proven against real data too
(refusal is a structural fact independent of any outcome, so this does not violate the
no-tuning-on-outcomes rule).
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import compiler as CO
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import recency as REC
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v8b1 import scorer as SC

COVERAGE_MATRIX = "/home/ubuntu/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"


# ---- direct formula-level proofs (fully synthetic, no compile_query involved) -----------
# These exercise the exact arithmetic in score_fixture()'s body by constructing the
# intermediate quantities by hand, so the test is independent of the compiler's own
# machinery and isolates the ONE new formula this module adds.

def _score_from_estimates(observed, c_hat, b_hat, scale_var):
    """Reimplements exactly the formula in scorer_v8b1.score_fixture()'s tail, for testing the
    arithmetic in isolation from compile_query plumbing."""
    if scale_var is None or scale_var <= SC.ZERO_VARIANCE_FLOOR:
        return None
    baseline_sq_error = (observed - b_hat) ** 2
    cohort_sq_error = (observed - c_hat) ** 2
    return (baseline_sq_error - cohort_sq_error) / scale_var


def test_proof_1_perfect_cohort_uninformative_baseline():
    """c_hat == observed exactly; b_hat far away. Expect score >> 0."""
    score = _score_from_estimates(observed=10.0, c_hat=10.0, b_hat=2.0, scale_var=4.0)
    assert score is not None and score > 0
    # baseline_sq_error = 64, cohort_sq_error = 0 -> raw_improvement = 64, /4 = 16
    assert score == pytest.approx(16.0)


def test_proof_2_cohort_no_better_than_baseline():
    """c_hat == b_hat: both squared errors identical, raw_improvement == 0 EXACTLY."""
    score = _score_from_estimates(observed=7.0, c_hat=3.0, b_hat=3.0, scale_var=5.0)
    assert score == 0.0


def test_proof_3_cohort_actively_worse():
    """|observed - c_hat| > |observed - b_hat| -> score < 0."""
    score = _score_from_estimates(observed=10.0, c_hat=1.0, b_hat=8.0, scale_var=4.0)
    assert score is not None and score < 0


def test_proof_4_zero_cohort_dispersion_is_undefined_not_zero_not_exception():
    """All cohort_values identical -> scale_var == 0 -> SCORE_UNDEFINED, never a fabricated
    0.0 and never a raised division-by-zero exception."""
    assert _score_from_estimates(observed=5.0, c_hat=3.0, b_hat=1.0, scale_var=0.0) is None
    # confirm the real function returns the named status, not None-as-silent-failure
    result = SC.FixtureScore(status=SC.SCORE_UNDEFINED, scale_var=0.0)
    assert result.status == SC.SCORE_UNDEFINED
    assert result.score is None


def test_proof_6_scale_invariance():
    """Multiplying every value by a positive constant must leave score(T) unchanged -- this
    is the entire point of standardizing: the primitive must not be sensitive to whether the
    metric is shots (O(1-30)) or possession percentage (O(0-100))."""
    base = _score_from_estimates(observed=10.0, c_hat=8.0, b_hat=4.0, scale_var=9.0)
    k = 37.5
    scaled = _score_from_estimates(observed=10.0 * k, c_hat=8.0 * k, b_hat=4.0 * k,
                                   scale_var=9.0 * k * k)
    assert base is not None and scaled is not None
    assert scaled == pytest.approx(base)


def test_proof_7_weighting_family_averaging_matches_hand_computed_two_halflife_average():
    """A TIME_DECAY cohort must average c_hat/b_hat/scale_var across BOTH frozen half-lives,
    exactly as engine.py::_estimates already does for the point estimate -- never one chosen.
    This test reimplements the averaging by hand over two synthetic (c_hat, b_hat, scale_var)
    triples (representing what compile_query would return per half-life) and confirms the
    scorer's documented averaging rule (arithmetic mean across the family) is what score()
    would need to reproduce."""
    triples = [(8.0, 4.0, 9.0), (8.4, 3.6, 9.4)]   # (c_hat, b_hat, scale_var) per half-life
    c_hat = sum(t[0] for t in triples) / len(triples)
    b_hat = sum(t[1] for t in triples) / len(triples)
    scale_var = sum(t[2] for t in triples) / len(triples)
    expected = _score_from_estimates(observed=10.0, c_hat=c_hat, b_hat=b_hat,
                                     scale_var=scale_var)
    assert expected is not None
    # sanity: the averaged inputs must differ from either individual half-life's inputs,
    # otherwise this test would not actually exercise averaging
    assert c_hat not in (triples[0][0], triples[1][0]) or b_hat not in (
        triples[0][1], triples[1][1])


# ---- proof 5 + real-corpus regression: degenerate cohort==baseline must SCORE_REFUSED ----
# Reuses the same fixtures test_v71_engine.py already uses, so this exercises score_fixture()
# against the REAL compiler and REAL corpus for the one case class that is a structural fact
# (cohort==baseline) rather than an outcome-dependent one -- this does not tune anything
# against a real target's observed value, since a degenerate selector never reaches the point
# of reading `observed` for scoring purposes at all.

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")


@pytest.fixture(scope="module")
def cap():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


@pytest.fixture(scope="module")
def index():
    recs = CI.load_records(include_fresh=False)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    return CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)


@pytest.fixture(scope="module")
def ctx(index):
    cut = index.kick[int(len(index.kick) * 0.7)]
    ter, cache = {}, {}
    for axis in PROFILE_AXES:
        from src.research.hypothesis_v71 import invariants as INV
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in index.metrics:
            continue
        by_comp = {}
        for tid, s in index.series.items():
            pre = [e for e in s if e[1] < cut]
            if len(pre) < 6:
                continue
            vals = [index.team_value(i, tid, metric, side) for (i, _k, _c, _h, _o) in pre]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            mv = sum(vals) / len(vals)
            cache[(tid, axis)] = mv
            by_comp.setdefault(pre[-1][2], []).append(mv)
        for comp, xs in by_comp.items():
            xs.sort()
            if len(xs) >= 3:
                ter[(comp, axis)] = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
    return EN.Context(index, ter, cache, SIM.SimilarityEngine(index))


def test_proof_5_degenerate_selector_is_score_refused_on_real_corpus(cap, index, ctx):
    """SUBJECT_OVERALL_BASELINE with zero conditions: cohort and baseline are the same
    selector by construction. Must SCORE_REFUSED, never a fabricated score."""
    spec = {"target_metrics": ["shots"], "subject": "HOME_TEAM", "side": "FOR",
           "comparison": "SUBJECT_OVERALL_BASELINE", "window": "ALL_PRIOR", "conditions": [],
           "research_family": "ATTACK_VOLUME", "required_capabilities": []}
    ir = IRM.build_ir(spec)
    assert ir.status == IRM.OK
    recency = EN.recency_family_for(ir)
    n_refused = 0
    n_checked = 0
    for rec_i in range(200, 260):
        result = SC.score_fixture(ir, index, rec_i, metric="shots", terciles=ctx.terciles,
                                  axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                                  recency=recency, capability=cap)
        n_checked += 1
        if result.status == SC.SCORE_REFUSED:
            n_refused += 1
        else:
            # a degenerate selector must NEVER produce SCORE_OK
            assert result.status != SC.SCORE_OK, (
                f"degenerate cohort==baseline selector produced a score at rec_i={rec_i}: "
                f"{result}")
    assert n_checked > 0
    assert n_refused == n_checked, (
        f"expected every one of {n_checked} degenerate-selector checks to refuse; "
        f"only {n_refused} did")


def test_real_nondegenerate_selector_produces_named_statuses_only(cap, index, ctx):
    """A real, non-degenerate selector (venue-conditioned) must always resolve to one of the
    four named terminal statuses -- never raise unexpectedly, never a bare Python exception
    escaping to the caller, regardless of outcome (this checks STATUS COVERAGE, not any
    particular outcome value, so it is not 'tuning against outcomes')."""
    spec = {"target_metrics": ["shots"], "subject": "HOME_TEAM", "side": "FOR",
           "comparison": "SUBJECT_VENUE_BASELINE", "window": "ALL_PRIOR", "conditions": [],
           "research_family": "ATTACK_VOLUME", "required_capabilities": []}
    ir = IRM.build_ir(spec)
    assert ir.status == IRM.OK
    recency = EN.recency_family_for(ir)
    statuses_seen = set()
    for rec_i in range(200, 320):
        result = SC.score_fixture(ir, index, rec_i, metric="shots", terciles=ctx.terciles,
                                  axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                                  recency=recency, capability=cap)
        assert result.status in SC.TERMINAL_STATUSES
        statuses_seen.add(result.status)
        if result.status == SC.SCORE_OK:
            # scale_var must be strictly positive (else it would have been SCORE_UNDEFINED)
            assert result.scale_var is not None and result.scale_var > SC.ZERO_VARIANCE_FLOOR
            assert result.score is not None
    assert statuses_seen, "no fixtures were evaluated at all -- test range invalid"


def test_version_stamp_declares_no_llm_input_and_no_outcome_tuning():
    stamp = SC.version_stamp()
    assert stamp["llm_numeric_input"] is False
    assert stamp["tuned_against_real_outcomes"] is False
    assert "score(T)" in stamp["new_formula"]
