"""V8C corpus data-vintage identity (`v8c_vintage_v1`) -- supports P0-A.

THE PROBLEM
-----------
`score_frozen` trusted a frozen integer `rec_i` against a freshly supplied index. A row
inserted, backfilled or reordered between selection and scoring can make that integer point at
a DIFFERENT fixture. And even when fixture identity is unchanged, a historical-data revision
can alter the PIT context, cohort membership, support, baseline, similarity and profile bands
-- so the scorer would silently evaluate a different statistical question than the one that
was selected, and report it as the frozen result.

WHAT IS HASHED
--------------
Not the whole index -- 5,636 records x 25 metrics is slow and over-sensitive to fields the
measurement never reads. Instead exactly what a measurement depends on:

    identity rows   ordered (fixture_id, kickoff_unix, competition, home_id, away_id)
    value rows      ordered per-metric (home, away) observation pairs

A single mutated prior value changes the hash; that is the property the binding needs and it
is asserted by test.

TARGET-BOUNDED
--------------
`corpus_vintage_before(t)` restricts to records strictly before `t`. A fixture's measurement
can only depend on data it is allowed to see, so binding it to a corpus-wide hash would refuse
scoring whenever any LATER match was appended -- a false alarm, and one that would make routine
corpus growth look like tampering. The vintage that matters is the one the measurement could
actually read.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import bisect
import hashlib
import json

VINTAGE_VERSION = "v8c_vintage_v1"


def _identity_rows(index, upto):
    return [(str(r.fixture_id), int(r.kickoff_unix), r.competition,
             str(r.home_id), str(r.away_id)) for r in index.recs[:upto]]


def _value_rows(index, upto):
    out = []
    for m in sorted(index.metrics):
        row = index.vals[m]
        out.append([m, [None if row[i] is None
                        else [round(float(row[i][0]), 6), round(float(row[i][1]), 6)]
                        for i in range(upto)]])
    return out


def corpus_vintage_before(index, before_unix) -> str:
    """Hash of every record STRICTLY BEFORE `before_unix`: identity rows + metric values."""
    j = bisect.bisect_left(index.kick, int(before_unix))
    payload = {"vintage_version": VINTAGE_VERSION, "n_records": j,
               "identity": _identity_rows(index, j), "values": _value_rows(index, j)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def corpus_vintage_full(index) -> str:
    """Corpus-wide hash. Diagnostics only -- binding uses the target-bounded form."""
    n = len(index.recs)
    payload = {"vintage_version": VINTAGE_VERSION, "n_records": n,
               "identity": _identity_rows(index, n), "values": _value_rows(index, n)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def capability_hash(capability) -> str:
    """Content hash of the capability contract: every metric's status and admissible set."""
    from src.research.hypothesis_v71 import capability as CAP
    payload = sorted(
        (m, capability.classify_metric(m)[0],
         tuple(sorted(capability.admissible_competitions(m))))
        for m in CAP.METRIC_SEMANTICS)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def fixture_metadata(index, pos) -> dict:
    """The immutable identity of one target fixture, frozen at selection and re-verified at
    scoring. `rec_i` is recorded for diagnostics ONLY -- resolution is by `fixture_id`."""
    r = index.recs[pos]
    return {"fixture_id": str(r.fixture_id), "kickoff_unix": int(r.kickoff_unix),
            "competition": r.competition, "home_id": str(r.home_id),
            "away_id": str(r.away_id), "rec_i_at_selection": int(pos)}


def version_stamp() -> dict:
    return {"vintage_version": VINTAGE_VERSION,
            "supports": ["P0-A"],
            "hashes": ["ordered identity rows", "ordered per-metric value rows"],
            "target_bounded": True,
            "why_target_bounded": ("a measurement can only depend on data it may read; a "
                                   "corpus-wide hash would treat routine corpus growth as "
                                   "tampering"),
            "rec_i_is_diagnostic_only": True,
            "resolution_is_by_fixture_id": True}
