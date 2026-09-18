"""V8C per-target PIT context (`v8c_pit_context_v2`).

Repairs TWO defects:

  P0 `D-V8C-P0-CTXCUT`  -- future information in the profile fit
  P1 `PROFILE-COMP`     -- incoherent competition semantics in the profile comparison

P0: THE CUT
-----------
`hypothesis_v71.execution.build_context(index)` fits the axis cache and terciles on every match
before ONE GLOBAL CUT:

    cut = index.kick[int(len(index.kick) * 0.7)]        # 2025-12-12 on this corpus

PIT-safe for V7.1, whose confirmatory sample was the 2026/27 fresh season -- entirely after the
cut. NOT PIT-safe for V8B/V8C: 643/1000 manifest and 50/50 exposed pilot fixtures kick off
BEFORE it, so their band assignments are a function of matches that had not happened at T, and
the target fixture's OWN row sits inside the fitting window. V8C rebuilds at each target's own
prior frontier: `cut = index.kick[rec_i]`, strict `<`.

P1: THE KEY
-----------
The inherited construction used three different notions of competition in one predicate:

    cache[(tid, axis)]                     the team's mean across EVERY competition
    by_comp.setdefault(pre[-1][2], ...)    filed under its most recent competition
    terciles.get((entry[2], axis))         tested against the PRIOR MATCH's competition

13.4% of teams here have prior matches in more than one competition, so for those teams the
band compared incommensurable quantities. V8C adopts `(team, competition, axis, T)`:

    axis_cache[(team_id, competition, axis)]   mean over that team's prior matches IN that
                                               competition, strictly before T
    terciles[(competition, axis)]              over the profile values of teams IN that
                                               competition

Verified structurally before adoption (V8C_HYPOTHESIS_GRAMMAR_SPEC.md section 3.2): 98.7-100%
of `(team, competition)` cells clear the >=6 floor and all six competitions clear the >=3-team
floor, so the strict semantic is coherent AND does not empty the universe.

Both floors are UNCHANGED from `execution.build_context`; only the KEY changes. A cell below
the floor yields NO profile, and a match against an unprofiled opponent is EXCLUDED from the
cohort -- never imputed to MID. NULL is not ZERO and NULL is not MID.

`execution.py` is NOT modified. ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v71 import execution as EX
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import similarity as SIM

PIT_CONTEXT_VERSION = "v8c_pit_context_v2"

PROFILE_AXES = tuple(EX.PROFILE_AXES)

MIN_PRIOR_MATCHES_FOR_PROFILE = 6      # execution.build_context: `if len(pre) < 6: continue`
MIN_TEAMS_FOR_TERCILES = 3             # execution.build_context: `if len(xs) >= 3`

PROFILE_SEMANTIC = "(team, competition, axis, T)"


@dataclass(frozen=True)
class PitContext:
    """The V8C context. Deliberately NOT `engine.Context`: the axis cache has a different key
    arity, so a V8C context handed to the frozen compiler would silently miss every profile
    lookup. A distinct type makes that a TypeError-shaped mistake rather than a silent one.
    """
    index: object
    terciles: dict          # (competition, axis) -> (lo, hi)
    axis_cache: dict        # (team_id, competition, axis) -> mean
    similarity: object
    cut_unix: int
    rec_i: int

    def profile_cells(self) -> int:
        return len(self.axis_cache)

    def tercile_cells(self) -> int:
        return len(self.terciles)


def build_pit_context(index, rec_i, *, similarity_engine=None) -> PitContext:
    """The context fitted STRICTLY BEFORE `index.kick[rec_i]`, keyed per competition.

    `similarity_engine` may be shared across targets: `SimilarityEngine` caches on
    `(competition, rec_i)` and rebuilds every profile at that reference position, so a cache
    hit can never serve a profile fitted at a later time (see its own docstring).
    """
    cut = int(index.kick[rec_i])
    ter, cache = {}, {}
    for axis in PROFILE_AXES:
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in index.metrics:
            continue
        by_comp = {}
        for tid, series in index.series.items():
            # Partition the team's STRICTLY-PRIOR matches by competition, then profile each
            # (team, competition) cell independently. This is the whole P1 repair.
            per_comp = {}
            for e in series:
                if e[1] >= cut:                 # STRICT: target's own row excluded
                    continue
                per_comp.setdefault(e[2], []).append(e)
            for comp, pre in per_comp.items():
                if len(pre) < MIN_PRIOR_MATCHES_FOR_PROFILE:
                    continue                    # no profile -- never imputed
                vals = [index.team_value(i, tid, metric, side)
                        for (i, _k, _c, _h, _o) in pre]
                vals = [v for v in vals if v is not None]
                if not vals:
                    continue
                mv = sum(vals) / len(vals)
                cache[(tid, comp, axis)] = mv
                by_comp.setdefault(comp, []).append(mv)
        for comp, xs in by_comp.items():
            xs.sort()
            if len(xs) >= MIN_TEAMS_FOR_TERCILES:
                ter[(comp, axis)] = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
    sim = similarity_engine if similarity_engine is not None else SIM.SimilarityEngine(index)
    return PitContext(index=index, terciles=ter, axis_cache=cache, similarity=sim,
                      cut_unix=cut, rec_i=int(rec_i))


def context_hash(ctx: PitContext) -> str:
    """A deterministic hash of the fitted context, for cache identity and freeze binding.
    Iteration is over SORTED keys so the hash cannot depend on dict insertion order."""
    import hashlib
    import json
    payload = {
        "pit_context_version": PIT_CONTEXT_VERSION,
        "cut_unix": ctx.cut_unix,
        "profile_semantic": PROFILE_SEMANTIC,
        "terciles": [[list(k), list(v)] for k, v in sorted(ctx.terciles.items())],
        "axis_cache": [[list(k), round(v, 10)] for k, v in sorted(ctx.axis_cache.items())],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def version_stamp() -> dict:
    return {"pit_context_version": PIT_CONTEXT_VERSION,
            "repairs": ["D-V8C-P0-CTXCUT", "P1-PROFILE-COMP"],
            "cut": "index.kick[rec_i], strictly-before, rebuilt per target fixture",
            "was_cut": "single global index.kick[int(len(index.kick)*0.7)]",
            "profile_semantic": PROFILE_SEMANTIC,
            "axis_cache_key": "(team_id, competition, axis)",
            "was_axis_cache_key": "(team_id, axis) -- cross-competition mean",
            "tercile_key": "(competition, axis)",
            "profile_axes": list(PROFILE_AXES),
            "min_prior_matches_for_profile": MIN_PRIOR_MATCHES_FOR_PROFILE,
            "min_teams_for_terciles": MIN_TEAMS_FOR_TERCILES,
            "floors_unchanged_from_v71": True,
            "unprofiled_cell": "no profile; match EXCLUDED from cohort, never imputed to MID",
            "similarity_engine_already_pit_safe_upstream": True,
            "modifies_v71_execution": False,
            "reads_target_outcome": False}
