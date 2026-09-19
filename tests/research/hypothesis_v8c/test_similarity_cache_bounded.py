"""REPAIR 6: bounded historical-similarity memory, with membership semantics untouched.

THE DIAGNOSIS, which was not what the previous session reported.
A `gc` census showed the accumulating objects were `traceback` (358k -> 643k over two
fixtures) and `frame` (262k -> 482k) -- not caches. `similar_ids_before` stored the
SimilarityRefused EXCEPTION OBJECT in its memo and re-raised it; every `raise exc` appends a
frame to that same object's `__traceback__`, and each frame pins its locals. One cached
refusal therefore grew an unbounded traceback chain. The memo itself holds a few hundred small
frozensets and was never the cost.

Measured: RSS 238 -> 429 -> 642 MB over three fixtures before; 28 MB flat after.
"""
from __future__ import annotations

import gc

import pytest

from src.research.hypothesis_v8c import historical_similarity as HSIM
from src.research.hypothesis_v71.similarity import SimilarityRefused

from .test_similarity_self_inclusion import _build, _index, TOPP, COMP, H_FIXTURE, H_OPPONENT


def _hs(recs, **kw):
    return HSIM.HistoricalSimilarityIndex(_index(recs), **kw)


def test_refusals_are_not_cached_as_exception_objects():
    """THE leak: a cached exception retains its traceback, frames and their locals."""
    import inspect
    src = inspect.getsource(HSIM)
    assert "self._cohort_memo[key] = exc" not in src
    assert "raise memo" not in src, "re-raising a cached exception regrows its traceback"


def test_repeated_refusal_does_not_accumulate_tracebacks():
    hs = _hs(_build())
    before = sum(1 for o in gc.get_objects() if type(o).__name__ == "traceback")
    raised = 0
    for _ in range(300):
        try:
            hs.similar_ids_before("tm_NO_SUCH_TEAM", COMP, 1_600_000_000)
        except SimilarityRefused:
            raised += 1
    gc.collect()
    after = sum(1 for o in gc.get_objects() if type(o).__name__ == "traceback")
    assert raised == 300
    assert after - before < 300, (
        f"tracebacks grew by {after - before} across 300 refusals -- the refusal is still "
        f"retaining frames")


def test_refusal_message_is_preserved_across_the_memo():
    hs = _hs(_build())
    msgs = []
    for _ in range(2):
        try:
            hs.similar_ids_before("tm_NO_SUCH_TEAM", COMP, 1_600_000_000)
        except SimilarityRefused as e:
            msgs.append(str(e))
    assert len(msgs) == 2 and msgs[0] == msgs[1], "the cached refusal changed its reason"


# ---------------------------------------------------------------- semantics preserved
def _membership(recs, **kw):
    idx = _index(recs)
    hs = HSIM.HistoricalSimilarityIndex(idx, **kw)
    h_kick = int(idx.recs[idx.pos_of_fixture[H_FIXTURE]].kickoff_unix)
    return H_OPPONENT in hs.similar_ids_before(TOPP, COMP, h_kick)


@pytest.mark.parametrize("limit", [None, 1, 4])
def test_membership_identical_with_cache_enabled_disabled_and_evicting(limit):
    """Caching may change SPEED only. `limit=1` forces eviction on essentially every call."""
    kw = {} if limit is None else {"max_cohort_entries": limit}
    assert _membership(_build(), **kw) is _membership(_build())


def test_eviction_actually_happens_and_is_bounded():
    idx = _index(_build())
    hs = HSIM.HistoricalSimilarityIndex(idx, max_cohort_entries=3)
    ks = sorted({int(r.kickoff_unix) for r in idx.recs})[:25]
    for k in ks:
        try:
            hs.similar_ids_before(TOPP, COMP, k)
        except SimilarityRefused:
            pass
    st = hs.cache_stats()
    assert st["cohort_memo_entries"] <= 3, "the bound was not enforced"
    assert st["evictions"] > 0, "nothing was ever evicted despite exceeding the bound"
    assert st["caches_exception_objects"] is False


def test_adversarial_witnesses_still_hold_under_eviction():
    """The P0-SIMSELF invariants must survive the cache change, including with eviction on."""
    from .test_similarity_self_inclusion import MUTATED_H
    for kw in ({}, {"max_cohort_entries": 1}):
        base = _membership(_build(), **kw)
        assert _membership(_build(h_values=MUTATED_H), **kw) == base, (
            "H's own observation changed its own membership")
        assert _membership(_build(extreme_post_h=6), **kw) == base, (
            "post-H data changed H's membership")


def test_frozen_similarity_spec_is_untouched():
    from src.research.hypothesis_v7 import similarity as V7S
    assert HSIM.K_NEIGHBORS == V7S.K_NEIGHBORS
    assert HSIM.DIMENSIONS == tuple(V7S.SIMILARITY_DIMENSIONS)
    assert HSIM.PROFILE_SHRINKAGE_K == V7S.PROFILE_SHRINKAGE_K
    assert HSIM.PRIMARY_DISTANCE == V7S.PRIMARY_DISTANCE
    assert HSIM.MIN_PROFILE_HISTORY_MATCHES == V7S.MIN_PROFILE_HISTORY_MATCHES
    assert HSIM.MAX_MISSING_DIMS == V7S.MAX_MISSING_DIMS
