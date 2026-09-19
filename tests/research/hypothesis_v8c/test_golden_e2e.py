"""The positive synthetic end-to-end case and the one-failure-at-a-time negative battery.

NO CONDITIONAL ASSERTIONS. A known-good case asserts the exact expected state; a mutated case
asserts the exact expected failure, at the expected stage, for the expected reason.
"""
from __future__ import annotations

import pathlib

import pytest

from src.research.hypothesis_v8c import aggregate as AG
from src.research.hypothesis_v8c import cohort_stats as CS
from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import pre_t as PT
from src.research.hypothesis_v8c import score_frozen as SFZ
from src.research.hypothesis_v8c import select_freeze as SF
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GOLDEN_METRICS, GRAMMAR_KW


def _run(env, k=3):
    """The whole composed experiment over one synthetic environment."""
    freeze = SF.select_cohort(env.index, env.target_positions or [env.target_pos],
                              capability=env.capability, k=k,
                              fixture_ids=env.target_fixture_ids or [env.target_fixture_id],
                              grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    import json
    import tempfile

    from ._anchor_support import anchor_freeze
    d = tempfile.mkdtemp()
    path = f"{d}/freeze.json"
    with open(path, "w") as f:
        json.dump(freeze, f, indent=1, default=str, sort_keys=True)
    # The composed run goes through the REAL process-2 gate, external anchor included.
    akw = anchor_freeze(pathlib.Path(d), path,
                        fixture_ids=freeze["fixture_ids_ordered"])
    res = SFZ.score_frozen(path, env.index, capability=env.capability,
                           grammar_kwargs=GRAMMAR_KW, **akw)
    return freeze, res


# ================================ the positive case ======================================
def test_synthetic_end_to_end_positive(multi_env):
    """Every stage reachable in ONE composed run, on a 15-fixture cohort."""
    freeze, res = _run(multi_env)

    assert freeze["n_fixtures"] == 15
    assert freeze["totals"]["target_outcomes_viewed"] is False
    assert freeze["totals"]["R_identity_count"] == 0
    assert freeze["totals"]["R_cross_treatment_overlap_count"] == 0
    assert freeze["totals"]["unreachable_candidate_count"] == 0

    for row in freeze["selections"]:
        assert row["universe_ledger"]["n_pre_t_evaluable"] > 0
        assert row["k_valid"] > 0
        assert row["H"], "H produced no selection at a known-good fixture"

    ok = lambda arm: [r for r in res["records"]
                      if r["arm"] == arm and r["status"] == CS.SCORE_OK]
    assert len(ok("S")) > 0
    assert len(ok("R")) > 0
    assert len(ok("H")) > 0

    sr, sh = res["endpoint_S_vs_R"], res["endpoint_S_vs_H"]
    assert sr["paired_n_all"] > 0, "no S-v-R paired difference exists"
    assert sh["paired_n_all"] > 0, "no S-v-H paired difference exists"
    assert res["blocks"]["n_blocks_actual"] == 3
    assert sr["inference"]["inference_status"] in ("EXACT", AG.INSUFFICIENT_CLUSTERS)
    assert sh["inference"]["inference_status"] in ("EXACT", AG.INSUFFICIENT_CLUSTERS)


def test_pre_t_evaluable_implies_permitted_post_t_status(multi_env):
    """The consistency invariant, asserted unconditionally over every scored selection."""
    _freeze, res = _run(multi_env)
    checked = 0
    for r in res["records"]:
        assert r["status"] in PT.PERMITTED_POST_T_STATUSES, (
            f"{r['hypothesis_id']} was PRE_T_EVALUABLE but scored {r['status']}: "
            f"{r.get('reason')}")
        if r["status"] == CS.SCORE_REFUSED:
            assert PT.PERMITTED_REFUSAL_REASON in r["reason"], (
                f"unexpected refusal reason: {r['reason']}")
        checked += 1
    assert checked > 0


# ================================ the negative battery ====================================
def _universe(env, metrics=GOLDEN_METRICS):
    ctx = PC.build_pit_context(env.index, env.target_pos)
    return UNI.build_fixture_universe(env.index, env.target_pos, ctx=ctx,
                                      capability=env.capability,
                                      fixture_id=env.target_fixture_id,
                                      grammar_kwargs={"metrics": list(metrics)})


def _statuses(fu):
    return fu.status_counts


def test_negative_insufficient_raw_n():
    """ONE dimension mutated: too few prior matches."""
    fu = _universe(G.build_environment(n_prior_blocks=4, metrics=GOLDEN_METRICS))
    assert fu.n_evaluable == 0
    assert _statuses(fu).get(PT.PRE_T_INSUFFICIENT_RAW_N, 0) > 0


def test_negative_insufficient_unique_opponents():
    """Plenty of matches, but against too few distinct opponents."""
    fu = _universe(G.build_environment(n_prior_blocks=40, n_opponents=2,
                                       metrics=GOLDEN_METRICS))
    s = _statuses(fu)
    assert s.get(PT.PRE_T_INSUFFICIENT_OPPONENTS, 0) > 0, s


def test_negative_degenerate_scale():
    """A cohort with no dispersion cannot be standardized -- and it is knowable PRE-T."""
    fu = _universe(G.build_environment(metrics=("goals",), constant_metric="goals"),
                   metrics=("goals",))
    s = _statuses(fu)
    assert s.get(PT.PRE_T_NO_SCALE, 0) > 0, s


def test_negative_provider_unsupported_metric_absent_from_index():
    fu = _universe(G.build_environment(metrics=("goals",), drop_metric="goals"),
                   metrics=("goals",))
    assert fu.n_evaluable == 0


def test_negative_null_target_is_not_zero(multi_env):
    """A NULL target observation must REFUSE, never score 0.0."""
    env = G.build_environment(metrics=GOLDEN_METRICS, target_metric_null=True)
    freeze, res = _run(env, k=2)
    scored = [r for r in res["records"] if r["status"] != "UNRESOLVED"]
    assert scored, "nothing was scored"
    for r in scored:
        assert r["status"] != CS.SCORE_OK
        assert r["score"] is None, "a NULL target produced a numeric score"
        assert r["status"] == CS.SCORE_REFUSED


def test_negative_mutations_are_one_dimension_at_a_time():
    """The golden knob must change exactly the metric it names (P1 GOLDEN)."""
    env = G.build_environment(metrics=("goals", "yellow_cards"), constant_metric="goals")
    g = {v[0] for v in env.index.vals["goals"][:20] if v}
    y = {v[0] for v in env.index.vals["yellow_cards"][:20] if v}
    assert len(g) == 1, "the named metric was not collapsed"
    assert len(y) > 1, "an unnamed metric was collapsed too -- mutation is not isolated"


def test_negative_future_injection_does_not_change_the_outcome_of_the_battery():
    a = _universe(G.build_environment(metrics=GOLDEN_METRICS))
    b = _universe(G.build_environment(metrics=GOLDEN_METRICS, inject_future_rows=10))
    assert a.evaluable_ids() == b.evaluable_ids()
    assert a.ledger() == b.ledger()
