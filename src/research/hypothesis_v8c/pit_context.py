"""V8C per-target PIT context (`v8c_pit_context_v1`) -- repairs P0 `D-V8C-P0-CTXCUT`.

THE DEFECT
----------
`hypothesis_v71.execution.build_context(index)` fits the opponent-profile axis cache and the
per-competition terciles on every match before ONE GLOBAL CUT:

    cut = index.kick[int(len(index.kick) * 0.7)]        # 2025-12-12 on this corpus

That was PIT-safe for V7.1, whose confirmatory sample was the 2026/27 fresh season -- entirely
AFTER the cut. It is NOT PIT-safe for V8B/V8C, whose 1000-fixture manifest spans the historical
corpus: 643/1000 manifest fixtures and 50/50 exposed pilot fixtures kick off BEFORE that cut.

For such a target T:
  * the opponent's tercile band is a function of matches played in [T, cut) -- future
    information at T;
  * the target fixture's OWN row is inside the fitting window, so the band -- and therefore
    which prior matches enter the cohort -- is partly a function of the target's own observed
    values;
  * appending future rows to the corpus moves the 70% cut and changes band assignments, so the
    §29 adversarial battery cannot pass while this stands.

181/249 exposed Sonnet selections used an `opponent_profile` condition.

THE REPAIR
----------
Rebuild the context at EACH TARGET's own prior frontier: `cut = index.kick[rec_i]`, strict
`<`. Everything else -- the axis list, the >=6 prior-match floor, the >=3 per-competition
floor, the tercile index arithmetic -- is copied verbatim from `execution.build_context` so
this is a PIT correction and nothing else. `execution.py` is NOT modified (§4).

Measured cost: ~0.04s per target; ~40s across 997 fixtures. Not optimised, because a cheaper
cache keyed on anything coarser than the target position is how this defect arose.

ZERO SPEND. No network. No CHAMPION. Reads no target outcome.
"""
from __future__ import annotations

from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import execution as EX
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import similarity as SIM

PIT_CONTEXT_VERSION = "v8c_pit_context_v1"

#: Identical to `execution.PROFILE_AXES` and `search.PROFILE_AXES`; imported, not restated.
PROFILE_AXES = tuple(EX.PROFILE_AXES)

MIN_PRIOR_MATCHES_FOR_PROFILE = 6      # execution.build_context: `if len(pre) < 6: continue`
MIN_TEAMS_FOR_TERCILES = 3             # execution.build_context: `if len(xs) >= 3`


def build_pit_context(index, rec_i, *, similarity_engine=None):
    """The V7.1 context, fitted STRICTLY BEFORE `index.kick[rec_i]`.

    `similarity_engine` may be shared across targets: `SimilarityEngine` caches on
    `(competition, rec_i)` and rebuilds every profile at that reference position, so a cache
    hit can never serve a profile fitted at a later time (see its own docstring). The axis
    cache and terciles, which do NOT have that property upstream, are rebuilt here per target.
    """
    cut = int(index.kick[rec_i])
    ter, cache = {}, {}
    for axis in PROFILE_AXES:
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in index.metrics:
            continue
        by_comp = {}
        for tid, s in index.series.items():
            pre = [e for e in s if e[1] < cut]          # STRICT: target's own row excluded
            if len(pre) < MIN_PRIOR_MATCHES_FOR_PROFILE:
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
            if len(xs) >= MIN_TEAMS_FOR_TERCILES:
                ter[(comp, axis)] = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
    sim = similarity_engine if similarity_engine is not None else SIM.SimilarityEngine(index)
    return EN.Context(index, ter, cache, sim)


def version_stamp() -> dict:
    return {"pit_context_version": PIT_CONTEXT_VERSION,
            "repairs": "D-V8C-P0-CTXCUT",
            "was": "single global cut at index.kick[int(len(index.kick)*0.7)] -- future "
                   "information for every target before that cut, including the target's own "
                   "row",
            "now": "cut = index.kick[rec_i], strictly-before, rebuilt per target fixture",
            "profile_axes": list(PROFILE_AXES),
            "min_prior_matches_for_profile": MIN_PRIOR_MATCHES_FOR_PROFILE,
            "min_teams_for_terciles": MIN_TEAMS_FOR_TERCILES,
            "similarity_engine_already_pit_safe_upstream": True,
            "modifies_v71_execution": False,
            "reads_target_outcome": False}
