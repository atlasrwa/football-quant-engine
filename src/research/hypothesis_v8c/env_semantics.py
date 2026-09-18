"""V8C environment-mean semantics (`v8c_env_semantics_v1`) -- resolves P1 ENV-SEASON.

THE INCONSISTENCY
-----------------
`corpus_index.PITIndex.env_mean` is documented as:

    "Competition-season environment mean strictly before `cutoff_unix`."

but `comp_idx` is keyed on `r.competition` ALONE -- `season_id` is never part of the key -- so
the returned mean pools EVERY prior season of that competition. Measured on this corpus:

    champ 4 seasons pooled | epl 3 | laliga 3 | laliga2 3 | ligue1 3 | ligue2 3

The name says season-specific; the implementation is multi-season. That is the defect.

THE RESOLUTION -- documented, not silently re-implemented
---------------------------------------------------------
The mission permits either making it truly season-specific or explicitly renaming and
documenting a multi-season competition environment. V8C takes the second option, for reasons
that are about correctness rather than convenience:

  * The quantity is PIT-SAFE. `bisect_left(ks, cutoff)` with `cutoff = target kickoff` admits
    only strictly-earlier records. Audited over 200 manifest fixtures: ZERO contributing
    records at or after the cutoff. There is no leak to repair.
  * The quantity is used ONLY as a SHRINKAGE PRIOR (`Recency.shrink(mean, n, environment_mean)`)
    -- the value a thin cohort is pulled toward. A multi-season competition mean is a
    legitimate, and more stable, prior than a partial current season, which early in a season
    is estimated from a handful of matches.
  * `corpus_index.py` is a FROZEN V7.1 module. Changing this accessor would silently change
    every V7.1, V8B.1, V8B.2 and V8C number that has ever been computed, including frozen
    historical evidence this mission must not mutate.

Measured magnitude of the distinction (ligue1, `goals`, mid-manifest fixture):

    pooled multi-season   1.4901
    same-season only      1.5104   (n=96)      -- a ~1.4% difference in the shrinkage target

So V8C does NOT change the number. It names it correctly everywhere and records the audit, so
no future reader infers season-specificity from the inherited docstring.

CORRECT NAME: `competition_environment_mean` -- the PIT-safe mean over ALL prior seasons of
that competition, strictly before the target kickoff. NOT season-specific.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import bisect

ENV_SEMANTICS_VERSION = "v8c_env_semantics_v1"

CANONICAL_NAME = "competition_environment_mean"
IS_SEASON_SPECIFIC = False
IS_PIT_SAFE = True


def competition_environment_mean(index, competition, metric, cutoff_unix):
    """The correctly-named accessor. Delegates to the frozen implementation unchanged -- the
    VALUE is identical; only the name and the documented semantic are corrected."""
    return index.env_mean(competition, metric, cutoff_unix)


def audit_pit_safety(index, fixture_positions) -> dict:
    """Prove no record at or after the cutoff contributes to the environment mean."""
    checked = violations = 0
    for pos in fixture_positions:
        rec = index.recs[pos]
        cutoff = int(rec.kickoff_unix)
        idxs = index.comp_idx.get(rec.competition) or []
        ks = [index.kick[i] for i in idxs]
        j = bisect.bisect_left(ks, cutoff)
        checked += 1
        if any(index.kick[idxs[k]] >= cutoff for k in range(j)):
            violations += 1
    return {"env_semantics_version": ENV_SEMANTICS_VERSION,
            "fixtures_checked": checked, "pit_violations": violations,
            "pit_safe": violations == 0}


def audit_season_pooling(index) -> dict:
    """How many seasons pool into each competition's environment mean."""
    seasons = {}
    for r in index.recs:
        seasons.setdefault(r.competition, set()).add(str(r.season_id))
    return {"canonical_name": CANONICAL_NAME,
            "is_season_specific": IS_SEASON_SPECIFIC,
            "seasons_pooled_per_competition":
                {c: len(s) for c, s in sorted(seasons.items())},
            "season_ids_per_competition":
                {c: sorted(s) for c, s in sorted(seasons.items())}}


def version_stamp() -> dict:
    return {"env_semantics_version": ENV_SEMANTICS_VERSION,
            "resolves": ["P1-ENV-SEASON"],
            "canonical_name": CANONICAL_NAME,
            "inherited_docstring_said": "Competition-season environment mean",
            "actual_semantic": ("PIT-safe mean over ALL prior seasons of that competition, "
                                "strictly before the target kickoff"),
            "is_season_specific": IS_SEASON_SPECIFIC,
            "is_pit_safe": IS_PIT_SAFE,
            "used_only_as": "shrinkage prior in Recency.shrink",
            "value_changed_by_v8c": False,
            "why_not_reimplemented": ("corpus_index is a frozen V7.1 module; changing this "
                                      "accessor would silently change every V7.1/V8B/V8C "
                                      "number including frozen historical evidence"),
            "resolution": "renamed and documented, not silently re-implemented"}
