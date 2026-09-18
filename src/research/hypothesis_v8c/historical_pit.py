"""V8C historical-time (H-time) profile index (`v8c_historical_pit_v1`) -- repairs P1-K.

THE DEFECT (scientific methodology blocker)
-------------------------------------------
V8C's earlier repair fixed leakage relative to the TARGET fixture T: every profile is built
from data strictly before T. But when the compiler filters a HISTORICAL match H, it classified
H's opponent using a profile built as of T -- which includes

    * matches played AFTER H but before T, and
    * H ITSELF.

Audited empirically: for a historical match H against opponent X, X's profile as of T included
H and every post-H match. So when the cohort asks "how did the subject do against HIGH
shots-against opponents", the very observation being measured contributed to deciding whether
its own opponent counted as HIGH. That is retrospective self-inclusion: the outcome influences
the conditioning variable.

In the mission's taxonomy this was case (C) -- "information available any time before target
T". The scientifically correct semantic is case (A).

THE REPAIR
----------
For every historical match H used in a cohort:

    opponent profile for H = built from information strictly BEFORE H
    tercile bounds for H   = built from the profiles of that competition's teams,
                             each ALSO as of strictly before H

Both halves are required. If the profile were as-of-H but the thresholds as-of-T, appending
extreme post-H matches would still move the bounds and could flip H's band -- the adversarial
test would fail.

IMPLEMENTATION
--------------
A cumulative-prefix representation keyed `(team, competition, axis)`, holding that cell's
kickoffs with running sums and counts. A profile as of any instant is then a `bisect` plus O(1)
arithmetic, so "as of H" costs the same as "as of T" and no per-H recomputation is needed.

Measured on the real corpus: the whole structure builds in ~0.1s, one target fixture needs
174-948 distinct `(competition, axis, H_kickoff)` tercile triples, and computing all of them
uncached costs under 0.02s. The triple count is bounded by (prior matches x axes), NOT by the
candidate count, so it does not scale with the ~200k-candidate universe.

Floors are UNCHANGED from `pit_context`: `MIN_PRIOR_MATCHES_FOR_PROFILE = 6`,
`MIN_TEAMS_FOR_TERCILES = 3`. A cell below the floor yields NO profile and a match against an
unprofiled opponent is EXCLUDED -- never imputed to MID. NULL is not ZERO and NULL is not MID.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import bisect
import hashlib
import json

from src.research.hypothesis_v71 import invariants as INV

HISTORICAL_PIT_VERSION = "v8c_historical_pit_v1"

PROFILE_SEMANTIC = "(team, competition, axis, strictly-before-H)"

#: Unchanged from `pit_context`. Imported as literals here so this module has no dependency
#: on a target-relative context object.
MIN_PRIOR_MATCHES_FOR_PROFILE = 6
MIN_TEAMS_FOR_TERCILES = 3

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")


class HistoricalProfileIndex:
    """Profiles and tercile bounds as of ANY instant, over one corpus index.

    Built ONCE per corpus and shared across every target fixture: the keys are real historical
    timestamps, not target-relative offsets, so a tercile computed while evaluating fixture T1
    is reusable verbatim while evaluating T2.
    """

    def __init__(self, index, axes=PROFILE_AXES):
        self.index = index
        self.axes = tuple(axes)
        self._pref = {}            # (team, comp, axis) -> (kickoffs, cum_sum, cum_count)
        self._teams_by_comp = {}   # comp -> sorted tuple of team ids
        self._tercile_memo = {}    # (comp, axis, before_unix) -> (lo, hi) | None
        self._build()

    def _build(self):
        by_cell = {}
        for tid, series in self.index.series.items():
            bycomp = {}
            for e in series:
                bycomp.setdefault(e[2], []).append(e)
            for comp, es in bycomp.items():
                es.sort(key=lambda e: (int(e[1]), int(e[0])))
                by_cell[(tid, comp)] = es
                self._teams_by_comp.setdefault(comp, set()).add(tid)

        for axis in self.axes:
            metric, side = INV.axis_metric_perspective(axis)
            if metric not in self.index.metrics:
                continue
            for (tid, comp), es in by_cell.items():
                ks, cs, cn = [], [], []
                tot, cnt = 0.0, 0
                for (i, k, _c, _h, _o) in es:
                    v = self.index.team_value(i, tid, metric, side)
                    if v is not None:
                        tot += v
                        cnt += 1
                    ks.append(int(k))
                    cs.append(tot)
                    cn.append(cnt)
                self._pref[(str(tid), comp, axis)] = (ks, cs, cn)
        self._teams_by_comp = {c: tuple(sorted(t)) for c, t in self._teams_by_comp.items()}

    # ---- profiles ------------------------------------------------------------------------
    def profile_before(self, team_id, competition, axis, before_unix):
        """The team's mean on `axis` in `competition`, over matches STRICTLY BEFORE
        `before_unix`. None when the cell is below the frozen prior-match floor."""
        got = self._pref.get((str(team_id), competition, axis))
        if not got:
            return None
        ks, cs, cn = got
        j = bisect.bisect_left(ks, int(before_unix))     # strictly-before
        if j == 0:
            return None
        n = cn[j - 1]
        if n < MIN_PRIOR_MATCHES_FOR_PROFILE:
            return None
        return cs[j - 1] / n

    # ---- terciles ------------------------------------------------------------------------
    def terciles_before(self, competition, axis, before_unix):
        """Tercile bounds for `competition`/`axis`, over team profiles that are THEMSELVES as
        of strictly before `before_unix`. Memoised on real historical timestamps, so the cache
        is shared across every target fixture."""
        key = (competition, axis, int(before_unix))
        if key in self._tercile_memo:
            return self._tercile_memo[key]
        xs = []
        for tid in self._teams_by_comp.get(competition, ()):
            v = self.profile_before(tid, competition, axis, before_unix)
            if v is not None:
                xs.append(v)
        out = None
        if len(xs) >= MIN_TEAMS_FOR_TERCILES:
            xs.sort()
            out = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
        self._tercile_memo[key] = out
        return out

    # ---- the band, as of H ----------------------------------------------------------------
    def band_before(self, team_id, competition, axis, before_unix):
        """`LOW` / `MID` / `HIGH`, or None when the match cannot be classified from
        strictly-prior information. None means EXCLUDE, never MID."""
        mv = self.profile_before(team_id, competition, axis, before_unix)
        if mv is None:
            return None
        bounds = self.terciles_before(competition, axis, before_unix)
        if not bounds:
            return None
        lo, hi = bounds
        return "LOW" if mv < lo else ("HIGH" if mv > hi else "MID")

    # ---- evidence -------------------------------------------------------------------------
    def stats(self) -> dict:
        return {"historical_pit_version": HISTORICAL_PIT_VERSION,
                "n_cells": len(self._pref),
                "n_competitions": len(self._teams_by_comp),
                "n_tercile_memo_entries": len(self._tercile_memo),
                "profile_semantic": PROFILE_SEMANTIC}

    def identity_hash_before(self, before_unix) -> str:
        """Content hash of the prefix structure RESTRICTED to data strictly before
        `before_unix` -- the data vintage that can actually affect a measurement at that time.

        Target-bounded deliberately. A corpus-wide hash would change whenever ANY later match
        was appended, even though `band_before` provably cannot read one, so it would make the
        PIT adversarial battery fail for a reason that is not a leak. Binding a measurement to
        the vintage of the data it is allowed to see is both the tighter and the more honest
        statement.
        """
        t = int(before_unix)
        payload = []
        for key in sorted(self._pref):
            ks, cs, cn = self._pref[key]
            j = bisect.bisect_left(ks, t)
            if j == 0:
                continue
            payload.append([list(key), j, round(cs[j - 1], 6), cn[j - 1], ks[j - 1]])
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def identity_hash(self) -> str:
        """Corpus-wide content hash. Used for diagnostics only -- measurement binding uses
        `identity_hash_before`, which is target-bounded."""
        payload = []
        for key in sorted(self._pref):
            ks, cs, cn = self._pref[key]
            payload.append([list(key), ks[-5:], [round(x, 6) for x in cs[-5:]], cn[-5:],
                            len(ks)])
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def version_stamp() -> dict:
    return {"historical_pit_version": HISTORICAL_PIT_VERSION,
            "repairs": ["P1-K"],
            "was": ("historical match H classified using the opponent's profile as of T, "
                    "which included post-H matches AND H itself (case C)"),
            "now": PROFILE_SEMANTIC + " for the profile AND for the tercile bounds (case A)",
            "both_halves_required": ("as-of-H profile with as-of-T thresholds would still let "
                                     "post-H matches move the bounds and flip H's band"),
            "min_prior_matches_for_profile": MIN_PRIOR_MATCHES_FOR_PROFILE,
            "min_teams_for_terciles": MIN_TEAMS_FOR_TERCILES,
            "floors_unchanged": True,
            "unclassifiable_match": "EXCLUDED from the cohort, never imputed to MID",
            "memo_keyed_on_real_timestamps_so_shared_across_targets": True,
            "reads_target_outcome": False}
