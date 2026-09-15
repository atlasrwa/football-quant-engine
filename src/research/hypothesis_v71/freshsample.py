"""V7.1 fresh confirmatory sample (`v71_fresh_v1`). Section 18.

V7's confirmatory window consumed 2025-01-01 -> 2026-05-31, which is the entire tail of the
historical corpus. No untouched chronological sample remained in it, so V7.1 acquired the
2026/27 season for the same six competitions from the same provider.

Two rules govern this module:

  * **Zero overlap is proved at FIXTURE-ID level, not by date range.** A date argument can be
    wrong by a fixture; an identifier set cannot.
  * **Development and confirmatory are disjoint by construction.** The whole historical corpus
    (everything V7 saw, plus everything V7.1's repair work touched) is DEVELOPMENT. The fresh
    season is CONFIRMATORY and is never read for an effect before authorization.

Fold construction is chronological and outcome-blind: equal-count blocks in kickoff order,
with the training cutoff of each fold at its own start. Nothing about a fold depends on a
result.
"""
from __future__ import annotations

import datetime
import hashlib
import json

FRESH_VERSION = "v71_fresh_v1"

#: V7's frozen confirmatory window. Every fixture inside it is DEVELOPMENT for V7.1 and may
#: never appear in the confirmatory manifest.
V7_CONFIRMATORY_START = "2025-01-01"
V7_CONFIRMATORY_END = "2026-05-31"

#: The fresh season ids, one per competition. Membership is by SEASON ID, not by date, so a
#: rescheduled fixture cannot drift across the boundary.
FRESH_SEASON_IDS = ("sn_3014533", "sn_8406098", "sn_8407970",
                    "sn_1368511", "sn_3011424", "sn_7255696")

N_FOLDS = 3


def _unix(datestr):
    return int(datetime.datetime.fromisoformat(datestr)
               .replace(tzinfo=datetime.UTC).timestamp())


def partition(records):
    """Split corpus records into (development, confirmatory) by SEASON ID."""
    fresh = {str(s) for s in FRESH_SEASON_IDS}
    dev = [r for r in records if str(r.season_id) not in fresh]
    conf = [r for r in records if str(r.season_id) in fresh]
    return dev, conf


def zero_overlap_proof(confirmatory, development):
    """Fixture-identifier-level disjointness, plus the V7 confirmatory window as a subset."""
    conf_ids = {str(r.fixture_id) for r in confirmatory}
    dev_ids = {str(r.fixture_id) for r in development}
    lo, hi = _unix(V7_CONFIRMATORY_START), _unix(V7_CONFIRMATORY_END) + 86400
    v7_ids = {str(r.fixture_id) for r in development if lo <= int(r.kickoff_unix) < hi}
    return {
        "n_confirmatory_fixtures": len(conf_ids),
        "n_development_fixtures": len(dev_ids),
        "n_v7_confirmatory_fixtures": len(v7_ids),
        "overlap_with_development": sorted(conf_ids & dev_ids),
        "overlap_with_v7_confirmatory": sorted(conf_ids & v7_ids),
        "disjoint_from_development": not (conf_ids & dev_ids),
        "disjoint_from_v7_confirmatory": not (conf_ids & v7_ids),
        "proof_level": "FIXTURE_IDENTIFIER_SET",
        "confirmatory_fixture_sha256": hashlib.sha256(
            json.dumps(sorted(conf_ids), separators=(",", ":")).encode()).hexdigest(),
    }


def build_folds(confirmatory, n_folds=N_FOLDS):
    """Equal-count chronological blocks. Outcome-blind: only kickoff order is consulted."""
    recs = sorted(confirmatory, key=lambda r: (int(r.kickoff_unix), str(r.fixture_id)))
    if len(recs) < n_folds:
        return []
    size, folds = len(recs) // n_folds, []
    for k in range(n_folds):
        lo = k * size
        hi = (k + 1) * size if k < n_folds - 1 else len(recs)
        block = recs[lo:hi]
        folds.append({
            "fold_index": k,
            "train_end_unix": int(block[0].kickoff_unix),
            "validate_start_unix": int(block[0].kickoff_unix),
            "validate_end_unix": int(block[-1].kickoff_unix) + 1,
            "validate_start": datetime.datetime.fromtimestamp(
                int(block[0].kickoff_unix), datetime.UTC).isoformat(),
            "validate_end": datetime.datetime.fromtimestamp(
                int(block[-1].kickoff_unix), datetime.UTC).isoformat(),
            "n_fixtures": len(block),
            "competitions": sorted({r.competition for r in block}),
            "fixture_ids": sorted(str(r.fixture_id) for r in block),
        })
    return folds


def structure(confirmatory, folds, *, exclusions=()):
    """The outcome-blind structural summary the evaluability gate consumes."""
    teams = {str(r.home_id) for r in confirmatory} | {str(r.away_id) for r in confirmatory}
    comps = sorted({r.competition for r in confirmatory})
    return {
        "n_fixtures": len(confirmatory),
        "n_teams": len(teams),
        "n_competitions": len(comps),
        "competitions": comps,
        "n_folds": len(folds),
        "min_fixtures_per_fold": min((f["n_fixtures"] for f in folds), default=0),
        "fold_competition_cells": sum(len(f["competitions"]) for f in folds),
        "n_excluded": len(exclusions),
        "exclusions": list(exclusions),
        "contains_effects": False,
    }


def manifest(confirmatory, development, folds, struct, overlap, *, gate=None):
    doc = {
        "fresh_version": FRESH_VERSION,
        "provider": "thestatsapi",
        "season_ids": list(FRESH_SEASON_IDS),
        "partition_rule": ("development = every record outside the fresh season ids "
                           "(the whole historical corpus, including everything V7 viewed "
                           "and everything V7.1's repair touched); confirmatory = the fresh "
                           "season only"),
        "fold_rule": (f"{len(folds)} equal-count chronological blocks in kickoff order; each "
                      "fold trains on everything strictly before its own start"),
        "zero_overlap": overlap,
        "structure": struct,
        "folds": [{k: v for k, v in f.items() if k != "fixture_ids"} for f in folds],
        "fold_fixture_ids": {str(f["fold_index"]): f["fixture_ids"] for f in folds},
        "confirmatory_outcomes_computed": False,
        "confirmatory_outcomes_viewed": False,
    }
    if gate is not None:
        doc["evaluability_gate"] = gate
    return doc


def version_stamp() -> dict:
    return {"fresh_version": FRESH_VERSION,
            "n_folds": N_FOLDS,
            "season_ids": list(FRESH_SEASON_IDS),
            "overlap_proof_level": "FIXTURE_IDENTIFIER_SET",
            "v7_confirmatory_window": [V7_CONFIRMATORY_START, V7_CONFIRMATORY_END],
            "reads_confirmatory_outcomes": False}
