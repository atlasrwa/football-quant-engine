"""V8C successor compiler (`v8c_compiler_v1`) -- repairs P1 PROFILE-COMP.

NARROWLY-SCOPED successor to the frozen `hypothesis_v71.compiler`, which is NOT modified.
The ONE behavioural change is the `opponent_profile` predicate.

THE DEFECT
----------
The frozen predicate mixes three different notions of competition in a single comparison:

    mv     = axis_cache.get((opponent_id, f.axis))     # (1) the team's CROSS-COMPETITION mean
    bounds = terciles.get((entry[2], f.axis))          # (3) the PRIOR MATCH's competition
    band   = axis_tercile_band(mv, bounds)

and the cache itself was filed under (2) `by_comp.setdefault(pre[-1][2], ...)` -- whichever
competition the team most recently played in. 13.4% of teams in this corpus have prior matches
in more than one competition, so for those teams the band is a comparison between
incommensurable quantities: a mean pooled over (say) Ligue 2 and Ligue 1, tested against Ligue
1's thresholds.

THE REPAIR (two rounds)
-----------------------
Round 1 made the comparison competition-coherent. Round 2 (P1-K) made it HISTORICAL-TIME
coherent: a historical match H is classified from information strictly BEFORE H, rather than
from a profile as of T that contained post-H matches and H itself.

    band = axis_cache.band_before(opponent_id, entry_competition, f.axis, entry_kickoff)

A `(team, competition)` cell below the frozen `MIN_PRIOR_MATCHES_FOR_PROFILE` floor yields NO
profile, and a match against an unprofiled opponent is EXCLUDED from the cohort -- never
imputed to MID. NULL is not ZERO and NULL is not MID.

WHY A SUCCESSOR MODULE RATHER THAN A PATCH
------------------------------------------
The frozen `_passes_filters` receives no competition context at its profile branch -- its
`axis_cache` lookup is a 2-tuple `(team, axis)` -- so the corrected semantic cannot be
expressed through its interface. Everything else is copied verbatim and the frozen helpers
(`CompiledQuery`, `is_plain`, `_entity_id`, `axis_tercile_band`,
`assert_profile_reads_opponent`) are IMPORTED, not restated.

`tests/research/hypothesis_v8c/test_compiler_equivalence.py` asserts that for every hypothesis
WITHOUT an `opponent_profile` condition this module is byte-identical to the frozen compiler,
which bounds the blast radius of the copy to exactly the predicate that had to change.

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

from src.research.hypothesis_v71 import compiler as CO
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71.similarity import SimilarityRefused

COMPILER_VERSION = "v8c_compiler_v1"

# Frozen primitives, imported so they cannot drift.
CompiledQuery = CO.CompiledQuery
CompileRefused = CO.CompileRefused
is_plain = CO.is_plain
axis_tercile_band = CO.axis_tercile_band
assert_profile_reads_opponent = CO.assert_profile_reads_opponent
_entity_id = CO._entity_id

PROFILE_SEMANTIC = "(team, competition, axis, strictly-before-H)"


def _passes_filters(entry, filters, *, entity_id, target_is_home, rec,
                    terciles, axis_cache, complement):
    """True iff the prior match satisfies EVERY filter (or, when `complement`, fails any).

    Copied from the frozen `compiler._passes_filters`; the ONLY change is the
    `opponent_profile` branch, which now resolves the profile in the SAME competition whose
    terciles it is tested against.
    """
    if not filters:
        return not complement
    ok = True
    for f in filters:
        if f.dimension == "historical_venue_conditioning":
            want = f.value
            if want == "TARGET_VENUE":
                got = entry[3] == target_is_home
            elif want == "TARGET_VENUE_OPPONENT":
                got = entry[3] == (not target_is_home)
            else:
                got = entry[3] == (want == "HOME")
        elif f.dimension == "competition":
            got = entry[2] == rec.competition
        elif f.dimension == "opponent_profile":
            opponent_id = assert_profile_reads_opponent(entry, entity_id)
            entry_competition = entry[2]
            entry_kickoff = entry[1]
            # P1-K: classify this HISTORICAL match H from information strictly BEFORE H.
            # `axis_cache` is a HistoricalProfileIndex, so both the opponent's profile and the
            # tercile bounds are as of H -- H itself and every post-H match are excluded.
            band = axis_cache.band_before(opponent_id, entry_competition, f.axis,
                                          entry_kickoff)
            if band is None:
                return False          # cannot classify from prior info: exclude, never impute
            got = band == f.value
        else:                                          # unreachable: IR fails closed upstream
            raise INV.InvariantViolation(
                [INV.SEMANTICALLY_AMBIGUOUS],
                f"filter dimension {f.dimension!r} reached the compiler")
        ok = ok and got
    return (not ok) if complement else ok


def _select(index, sel, ir, rec, rec_i, subject_id, terciles, axis_cache, similarity,
            hist_similarity=None):
    """The observation set + weights named by one Selector. Strictly PIT.

    Copied from the frozen `compiler._select`; differs only in calling the corrected
    `_passes_filters` above.
    """
    if sel.entity_role == "COMPETITION_ENVIRONMENT":
        return None, None, frozenset()

    entity_id = _entity_id(sel.entity_role, rec, subject_id)
    target_is_home = (str(rec.home_id) == str(subject_id))
    entries = index.prior_entries(entity_id, rec_i)
    if not entries:
        return (), (), frozenset()

    if sel.similar_to_opponent:
        opponent_id = _entity_id("FIXTURE_OPPONENT", rec, subject_id)
        want = sel.similar_to_opponent == "SIMILAR"
        if hist_similarity is None:
            # Never fall back to the as-of-T set: that is the P0-SIMSELF defect, and a silent
            # fallback would make the leak depend on how the caller was wired.
            raise CompileRefused(
                "similar_to_opponent requires an H-time HistoricalSimilarityIndex "
                "(P0-SIMSELF); the as-of-T similar set lets H decide its own membership")
        kept = []
        for e in entries:
            # Membership is resolved from information strictly BEFORE this historical match,
            # so neither H's own observation nor any post-H match can move it.
            try:
                sim_h = hist_similarity.similar_ids_before(
                    opponent_id, rec.competition, int(e[1]))
            except SimilarityRefused:
                continue          # unclassifiable as of H -> EXCLUDED, never imputed
            if (assert_profile_reads_opponent(e, entity_id) in sim_h) == want:
                kept.append(e)
        entries = kept

    if sel.filters:
        entries = [e for e in entries
                   if _passes_filters(e, sel.filters, entity_id=entity_id,
                                      target_is_home=target_is_home, rec=rec,
                                      terciles=terciles, axis_cache=axis_cache,
                                      complement=sel.complement)]
    elif sel.complement:
        entries = []
    if sel.window == "W5":
        entries = entries[-5:]
    elif sel.window == "W10":
        entries = entries[-10:]
    return entries, entity_id, frozenset(str(index.recs[e[0]].fixture_id) for e in entries)


def compile_query(ir, index, rec_i, *, metric, terciles, axis_cache, similarity,
                  recency, capability=None, collect_fixtures=True,
                  hist_similarity=None) -> CompiledQuery:
    """Compile ONE metric of a validated IR at one target fixture.

    Copied from the frozen `compiler.compile_query`; differs only in calling the corrected
    `_select` above. Identical refusal semantics, identical degeneracy check, identical
    CompiledQuery shape.
    """
    INV.assert_valid(ir, capability=capability)

    rec = index.recs[rec_i]
    subject_id = str(rec.home_id) if ir.subject == "HOME_TEAM" else str(rec.away_id)
    observed = index.team_value(rec_i, subject_id, metric, ir.perspective)
    env = index.env_mean(rec.competition, metric, int(rec.kickoff_unix))

    def values_of(entries, entity_id, weighting):
        vals, wts = [], []
        ref = int(rec.kickoff_unix)
        if weighting != "TIME_DECAY":
            for e in entries:
                v = index.team_value(e[0], entity_id, metric, ir.perspective)
                if v is not None:
                    vals.append(v)
                    wts.append(1.0)
            return tuple(vals), tuple(wts)
        for e in entries:
            v = index.team_value(e[0], entity_id, metric, ir.perspective)
            if v is None:
                continue
            vals.append(v)
            wts.append(recency.weight(e[1], ref) if weighting == "TIME_DECAY" else 1.0)
        return tuple(vals), tuple(wts)

    out = {}
    for name, sel in (("cohort", ir.cohort), ("baseline", ir.baseline)):
        if sel.entity_role == "COMPETITION_ENVIRONMENT":
            if env is None:
                raise CompileRefused("competition environment mean is unavailable")
            out[name] = ((env,), (1.0,), frozenset(), 1)
            continue
        if is_plain(sel) and not collect_fixtures:
            entity_id = _entity_id(sel.entity_role, rec, subject_id)
            mean, n = index.pit_mean(entity_id, metric, sel.perspective, rec_i)
            if mean is None or n == 0:
                raise CompileRefused(f"{name} selector matched no OBSERVED value")
            out[name] = ((mean,), (1.0,), frozenset(), n)
            continue
        entries, entity_id, fixtures = _select(index, sel, ir, rec, rec_i, subject_id,
                                               terciles, axis_cache, similarity,
                                               hist_similarity=hist_similarity)
        if not entries:
            raise CompileRefused(f"{name} selector matched no prior observation")
        vals, wts = values_of(entries, entity_id, sel.weighting)
        if not vals:
            raise CompileRefused(f"{name} selector matched no OBSERVED value")
        out[name] = (vals, wts, fixtures, len(vals))

    cv, cw, cf, cn = out["cohort"]
    bv, bw, bf, bn = out["baseline"]
    q = CompiledQuery(cohort_values=cv, baseline_values=bv,
                      cohort_weights=cw, baseline_weights=bw,
                      environment_mean=env, observed=observed,
                      fixtures_read=cf | bf, cohort_fixtures=cf, baseline_fixtures=bf,
                      cohort_n=cn, baseline_n=bn, fixtures_collected=collect_fixtures)
    if q.is_degenerate():
        raise CompileRefused(
            "cohort and baseline coincide at this fixture: no contrast exists here")
    return q


def version_stamp() -> dict:
    return {"compiler_version": COMPILER_VERSION,
            "successor_to": CO.COMPILER_VERSION,
            "repairs": ["P1-PROFILE-COMP"],
            "only_behavioral_change": ("opponent_profile classifies each historical match H "
                                       "from information strictly before H, in H's own "
                                       "competition"),
            "profile_semantic": PROFILE_SEMANTIC,
            "axis_cache_type": "hypothesis_v8c.historical_pit.HistoricalProfileIndex",
            "profile_and_terciles_both_as_of_H": True,
            "repairs_round_2": ["P1-K"],
            "unprofiled_opponent": "EXCLUDED from the cohort, never imputed to MID",
            "reuses_frozen_unchanged": ["CompiledQuery", "is_plain", "_entity_id",
                                        "axis_tercile_band", "assert_profile_reads_opponent",
                                        "InvariantViolation semantics"],
            "byte_identical_to_frozen_without_opponent_profile": True}
