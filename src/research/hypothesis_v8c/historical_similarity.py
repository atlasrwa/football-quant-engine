"""V8C historical-time (H-time) similarity index (`v8c_historical_similarity_v1`) -- repairs
P0-SIMSELF.

THE DEFECT (direct scientific blocker, stop-rule items 1 and 5)
---------------------------------------------------------------
`hypothesis_v71.similarity.SimilarityEngine.similar_opponent_ids(index, opp, rec, rec_i)`
resolves its profiles through `_profiles_at(competition, rec_i)`, where `rec_i` is the TARGET
fixture's position. Every profile is therefore built from matches strictly before T.

That is PIT-safe with respect to T, and the compiler then uses the resulting set to decide, for
each HISTORICAL match H, whether H enters the cohort:

    entries = [e for e in entries
               if (opponent_of(e) in similar_as_of_T) == want]

So H's membership in its own cohort is decided by a set whose profiles include

    * H ITSELF -- H is a match of H's opponent, played before T, so H's measured values are
      averaged into that opponent's profile; and
    * every match played AFTER H but before T.

The observation being measured helps decide whether it is measured. This is the same class of
defect as P1-K (`historical_pit`), which repaired the `opponent_profile` comparator but left
the `similar_to_opponent` comparator untouched.

DEMONSTRATED, NOT ARGUED
------------------------
`tests/research/hypothesis_v8c/test_similarity_self_inclusion.py` builds a synthetic index,
records H's opponent's membership, then (a) mutates H's OWN measured values and (b) appends
extreme post-H, pre-T rows. Against the unrepaired engine BOTH flip membership.

THE REPAIR
----------
For every historical match H, the similar-opponent set is resolved from information strictly
BEFORE H:

    profiles for H      = each team's dimension means over its matches strictly before H
    competition baseline= over those as-of-H profiles
    shrinkage, z-fit    = over those as-of-H profiles
    distance, k, tie-break = the FROZEN V7 rule, reused verbatim

Both halves matter, exactly as in `historical_pit`: as-of-H profiles scored against an as-of-T
z-fit would still let post-H matches move the scale and flip H's membership.

The frozen V7 similarity SPEC is not redesigned. `SIMILARITY_DIMENSIONS`, `DIMENSION_BINDING`,
`PROFILE_SHRINKAGE_K`, `PRIMARY_DISTANCE`, `K_NEIGHBORS`, `MIN_PROFILE_HISTORY_MATCHES`,
`MAX_MISSING_DIMS`, `RESTRICT_SAME_COMPETITION` and the tie-break are IMPORTED. Only the
reference INSTANT changes: T becomes H.

IMPLEMENTATION
--------------
Cumulative prefix sums keyed `(team, competition, dimension)` holding kickoffs with running
sums and counts, so a profile at any instant is a `bisect` plus O(1) arithmetic -- the same
representation `historical_pit.HistoricalProfileIndex` uses. The per-instant cohort assembly
(baseline, shrink, z-fit, k-NN) is memoised on `(competition, reference_team, before_unix)`,
real historical timestamps, so the memo is shared across every target fixture.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import bisect
from collections import OrderedDict

from src.research.hypothesis_v7 import similarity as V7S
from src.research.hypothesis_v71.similarity import SimilarityRefused

HISTORICAL_SIMILARITY_VERSION = "v8c_historical_similarity_v1"

MEMBERSHIP_SEMANTIC = "(reference_team, competition, strictly-before-H)"

#: Every one of these is the FROZEN V7 value, imported rather than restated.
DIMENSIONS = tuple(V7S.SIMILARITY_DIMENSIONS)
DIMENSION_BINDING = dict(V7S.DIMENSION_BINDING)
K_NEIGHBORS = V7S.K_NEIGHBORS
MIN_PROFILE_HISTORY_MATCHES = V7S.MIN_PROFILE_HISTORY_MATCHES
MAX_MISSING_DIMS = V7S.MAX_MISSING_DIMS
PROFILE_SHRINKAGE_K = V7S.PROFILE_SHRINKAGE_K
PRIMARY_DISTANCE = V7S.PRIMARY_DISTANCE
RESTRICT_SAME_COMPETITION = V7S.RESTRICT_SAME_COMPETITION


class _Refused:
    """A refusal, recorded as TEXT. Deliberately not an exception: storing the exception
    object retains its traceback, its frames and their locals."""

    __slots__ = ("message",)

    def __init__(self, message):
        self.message = message


class HistoricalSimilarityIndex:
    """Similar-opponent cohorts as of ANY instant, over one corpus index.

    Built ONCE per corpus and shared across every target fixture: keys are real historical
    timestamps, not target-relative offsets.
    """

    #: Deterministic bound on the cohort memo. Chosen against available capacity: each entry
    #: is a small frozenset of team ids, so 200k entries is well under a gigabyte, while the
    #: exposed-50 cohort needs only a few thousand. Eviction is LRU and affects speed only.
    DEFAULT_MAX_COHORT_ENTRIES = 200_000

    def __init__(self, index, *, max_cohort_entries=None):
        self.index = index
        self.max_cohort_entries = int(max_cohort_entries
                                      or self.DEFAULT_MAX_COHORT_ENTRIES)
        self._evictions = 0
        self._pref = {}             # (team, comp, dim) -> (kickoffs, cum_sum, cum_count)
        self._match_k = {}          # (team, comp) -> sorted kickoffs (for n_matches)
        self._teams_by_comp = {}
        self._first_seen = {}       # team -> earliest kickoff, for the frozen tie-break
        self._cohort_memo = OrderedDict()
        self._build()

    # ---- construction --------------------------------------------------------------------
    def _build(self):
        cells = {}
        for tid, series in self.index.series.items():
            for e in series:
                cells.setdefault((str(tid), e[2]), []).append(e)
                self._teams_by_comp.setdefault(e[2], set()).add(str(tid))
                k = int(e[1])
                cur = self._first_seen.get(str(tid))
                if cur is None or k < cur:
                    self._first_seen[str(tid)] = k

        for (tid, comp), es in cells.items():
            es.sort(key=lambda e: (int(e[1]), int(e[0])))
            self._match_k[(tid, comp)] = [int(e[1]) for e in es]
            acc = {d: (0.0, 0) for d in DIMENSIONS}
            cols = {d: ([], [], []) for d in DIMENSIONS}
            for (i, k, _c, _h, _o) in es:
                recd = self.index.recs[i]
                for d in DIMENSIONS:
                    block, field, persp = DIMENSION_BINDING[d]
                    v = V7S._side_value(recd, tid, block, field, persp)
                    tot, cnt = acc[d]
                    if v is not None:
                        tot, cnt = tot + float(v), cnt + 1
                        acc[d] = (tot, cnt)
                    ks, cs, cn = cols[d]
                    ks.append(int(k))
                    cs.append(tot)
                    cn.append(cnt)
            for d in DIMENSIONS:
                self._pref[(tid, comp, d)] = cols[d]

        self._teams_by_comp = {c: tuple(sorted(t)) for c, t in self._teams_by_comp.items()}

    # ---- profiles ------------------------------------------------------------------------
    def profile_before(self, team_id, competition, before_unix):
        """The team's V7-shaped profile over its matches in `competition` STRICTLY BEFORE
        `before_unix`. None when below the frozen history floor.

        NULL is never read as ZERO: a dimension with no observed values stays None and is
        counted as missing by `V7S.zvector`, exactly as in the frozen engine.
        """
        tid, t = str(team_id), int(before_unix)
        ks = self._match_k.get((tid, competition))
        if not ks:
            return None
        n = bisect.bisect_left(ks, t)                     # strictly-before
        if n < MIN_PROFILE_HISTORY_MATCHES:
            return None
        dims, dim_n = {}, {}
        for d in DIMENSIONS:
            col = self._pref.get((tid, competition, d))
            if not col:
                dims[d], dim_n[d] = None, 0
                continue
            kk, cs, cn = col
            j = bisect.bisect_left(kk, t)
            if j == 0 or cn[j - 1] == 0:
                dims[d], dim_n[d] = None, 0
            else:
                dims[d], dim_n[d] = cs[j - 1] / cn[j - 1], cn[j - 1]
        return {"team_id": tid, "n_matches": n, "dims": dims, "dim_n": dim_n}

    def _tie_key(self, team_id):
        """The FROZEN tie-break: earliest appearance, then id."""
        return (self._first_seen.get(str(team_id), 0), str(team_id))

    # ---- the cohort, as of H --------------------------------------------------------------
    def similar_ids_before(self, reference_team, competition, before_unix):
        """The k opponents most similar to `reference_team`, computed ENTIRELY from
        information strictly before `before_unix`.

        Raises `SimilarityRefused` on exactly the conditions the frozen engine refuses on, so
        a caller cannot tell the two apart by error behaviour.
        """
        key = (competition, str(reference_team), int(before_unix))
        memo = self._cohort_memo.get(key)
        if memo is not None:
            self._cohort_memo.move_to_end(key)
            if isinstance(memo, _Refused):
                # A FRESH exception every time. Caching the exception OBJECT and re-raising
                # it appended a new frame to that object's __traceback__ on every raise, and
                # each frame pinned its locals -- the profiles and z-fit dicts included. One
                # cached refusal therefore grew an unbounded traceback chain, which is what
                # actually consumed ~200 MB per fixture. The memo itself was never the cost:
                # it holds a few hundred small frozensets.
                raise SimilarityRefused(memo.message)
            return memo

        try:
            out = self._compute(reference_team, competition, before_unix)
        except SimilarityRefused as exc:
            # Store the REASON as text, never the exception (and never its traceback).
            self._store(key, _Refused(str(exc)))
            raise
        self._store(key, out)
        return out

    def _store(self, key, value) -> None:
        """Insert under a deterministic bound. Eviction is least-recently-used, so it can
        change only PERFORMANCE: an evicted key is recomputed from the same inputs and yields
        the same answer. Membership semantics are untouched."""
        self._cohort_memo[key] = value
        self._cohort_memo.move_to_end(key)
        while len(self._cohort_memo) > self.max_cohort_entries:
            self._cohort_memo.popitem(last=False)
            self._evictions += 1

    def cache_stats(self) -> dict:
        return {"cohort_memo_entries": len(self._cohort_memo),
                "cohort_memo_limit": self.max_cohort_entries,
                "evictions": self._evictions,
                "caches_exception_objects": False}

    def _compute(self, reference_team, competition, before_unix):
        ref = str(reference_team)
        profiles = {}
        for tid in self._teams_by_comp.get(competition, ()):
            p = self.profile_before(tid, competition, before_unix)
            if p is not None:
                profiles[tid] = p
        if not profiles or ref not in profiles:
            raise SimilarityRefused(
                f"no as-of-H profile for reference team {ref} at {int(before_unix)}")

        baseline = V7S.competition_baseline(list(profiles.values()))
        shrunk = {tid: V7S.shrink_profile(p, baseline, PROFILE_SHRINKAGE_K)
                  for tid, p in profiles.items()}
        fit = V7S.zscore_fit(list(shrunk.values()))

        target, target_missing = V7S.zvector(shrunk[ref], fit)
        if target_missing > MAX_MISSING_DIMS:
            raise SimilarityRefused(
                f"reference team {ref} profile is missing {target_missing} dimensions "
                f"(limit {MAX_MISSING_DIMS}); imputing them would distort every distance")

        rows = []
        for tid, p in shrunk.items():
            if tid == ref:
                continue
            vec, missing = V7S.zvector(p, fit)
            if missing > MAX_MISSING_DIMS:
                continue
            rows.append((V7S.distance(target, vec, PRIMARY_DISTANCE), self._tie_key(tid), tid))
        if len(rows) < K_NEIGHBORS:
            raise SimilarityRefused(
                f"only {len(rows)} comparable opponents with as-of-H profiles "
                f"(k={K_NEIGHBORS}) at {int(before_unix)}")
        rows.sort()
        return frozenset(tid for _d, _t, tid in rows[:K_NEIGHBORS])

    # ---- evidence -------------------------------------------------------------------------
    def stats(self) -> dict:
        return {"historical_similarity_version": HISTORICAL_SIMILARITY_VERSION,
                "n_cells": len(self._match_k),
                "n_competitions": len(self._teams_by_comp),
                "n_cohort_memo_entries": len(self._cohort_memo),
                "membership_semantic": MEMBERSHIP_SEMANTIC}


def version_stamp() -> dict:
    return {"historical_similarity_version": HISTORICAL_SIMILARITY_VERSION,
            "repairs": ["P0-SIMSELF"],
            "was": ("the similar-opponent set was resolved as of T, so a historical match H "
                    "contributed to the opponent profile that decided whether H entered its "
                    "own cohort, and post-H matches could flip it"),
            "now": MEMBERSHIP_SEMANTIC,
            "both_halves_required": ("as-of-H profiles scored against an as-of-T z-fit would "
                                     "still let post-H matches move the scale"),
            "frozen_v7_spec_reused_verbatim": True,
            "dimensions": list(DIMENSIONS),
            "k_neighbors": K_NEIGHBORS,
            "min_profile_history_matches": MIN_PROFILE_HISTORY_MATCHES,
            "max_missing_dims": MAX_MISSING_DIMS,
            "profile_shrinkage_k": PROFILE_SHRINKAGE_K,
            "primary_distance": PRIMARY_DISTANCE,
            "restrict_same_competition": RESTRICT_SAME_COMPETITION,
            "spec_redesigned": False,
            "memo_keyed_on_real_timestamps_so_shared_across_targets": True,
            "reads_target_outcome": False}
