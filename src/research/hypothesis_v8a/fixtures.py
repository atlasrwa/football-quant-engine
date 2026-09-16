"""V8A development fixture sample (`v8a_fixtures_v1`). Brief section 18.

Selection is deterministic, outcome-blind and frozen BEFORE any model call. Order is a
SHA-256 of the fixture identifier only -- never `hash()`, never `random`, never a result.

THREE EXCLUSION LAYERS, each proved at FIXTURE-ID or SEASON-ID level rather than by date
range, because a date argument can be wrong by a fixture and an identifier set cannot:

  1. V7.1 confirmatory / future V8 confirmatory pool -- the six FRESH season ids. Removed by
     `freshsample.partition`, which is the same frozen function V7.1 itself used.
  2. V7's confirmatory OOS window, 2025-01-01 .. 2026-05-31. Those fixtures are DEVELOPMENT
     for V7.1 but were V7's confirmatory sample, and the brief excludes them by name.
  3. Every target fixture any previous LLM hypothesis-generation experiment already saw
     (V5A, V5A.1, V5A.2, V6, V6.1 -- selected AND held-out). A fixture the incumbent protocol
     has already been run on is not a clean place to compare a new protocol against it.

ZERO SPEND. No network, no model, no effect.
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re

FIXTURES_VERSION = "v8a_fixtures_v1"

#: Frozen BEFORE any model call (brief sections 18 and 24).
N_FIXTURES = 12

#: V7's confirmatory OOS window, restated from `v71_freshsample` rather than re-derived.
V7_CONFIRMATORY_START = "2025-01-01"
V7_CONFIRMATORY_END = "2026-05-31"

#: Minimum prior history each SIDE must have for the fixture to be researchable at all. A
#: fixture whose teams have almost no prior matches cannot support behavioural reconnaissance
#: and would test packet-emptiness rather than research protocol.
MIN_PRIOR_MATCHES_PER_SIDE = 12

_PRIOR_EXPERIMENT_DIRS = ("v5a", "v5a1", "v5a2", "v6", "v6_1")


def _unix(datestr):
    return int(datetime.datetime.fromisoformat(datestr)
               .replace(tzinfo=datetime.UTC).timestamp())


def order_key(fixture_id: str) -> str:
    """Deterministic ordering over the identifier ALONE. Reads nothing else."""
    return hashlib.sha256(f"V8A_DEV_SAMPLE_v1|{fixture_id}".encode("utf-8")).hexdigest()


def prior_experiment_fixture_ids(oos_out_root: str) -> dict:
    """Every target fixture id previously used by an LLM hypothesis-generation experiment.

    Read from the frozen packet files (whose top-level keys ARE the target fixture ids) and
    from V6.1's fixture selection, rather than from any narrative report.
    """
    seen = {}
    for sub in _PRIOR_EXPERIMENT_DIRS:
        ids = set()
        for fp in glob.glob(os.path.join(oos_out_root, sub, "packets_*.json")):
            try:
                obj = json.load(open(fp))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(obj, dict):
                ids |= {k for k in obj if re.fullmatch(r"mt_\d+", str(k))}
        fsel = os.path.join(oos_out_root, sub, "fixture_selection.json")
        if os.path.exists(fsel):
            try:
                d = json.load(open(fsel))
            except (OSError, json.JSONDecodeError):
                d = {}
            ids |= {str(x) for x in (d.get("selected_fixtures") or [])}
            ids |= {str(x) for x in (d.get("held_out") or [])}
        if ids:
            seen[sub] = sorted(ids)
    return seen


def eligible(records, *, oos_out_root, index=None):
    """Apply every exclusion layer and return (eligible_records, audit)."""
    from src.research.hypothesis_v71 import freshsample as FS

    dev, conf = FS.partition(records)
    fresh_ids = {str(r.fixture_id) for r in conf}

    lo, hi = _unix(V7_CONFIRMATORY_START), _unix(V7_CONFIRMATORY_END) + 86400
    v7_window_ids = {str(r.fixture_id) for r in dev if lo <= int(r.kickoff_unix) < hi}

    prior = prior_experiment_fixture_ids(oos_out_root)
    prior_ids = {i for v in prior.values() for i in v}

    blocked = fresh_ids | v7_window_ids | prior_ids
    pool = [r for r in dev if str(r.fixture_id) not in blocked]

    thin = []
    if index is not None:
        keep = []
        for r in pool:
            i = index.pos_of_fixture.get(str(r.fixture_id))
            if i is None:
                thin.append(str(r.fixture_id))
                continue
            nh = len(index.prior_entries(str(r.home_id), i))
            na = len(index.prior_entries(str(r.away_id), i))
            if min(nh, na) < MIN_PRIOR_MATCHES_PER_SIDE:
                thin.append(str(r.fixture_id))
            else:
                keep.append(r)
        pool = keep

    audit = {
        "fixtures_version": FIXTURES_VERSION,
        "n_corpus_records": len(records),
        "n_v71_confirmatory_excluded": len(fresh_ids),
        "n_v7_confirmatory_window_excluded": len(v7_window_ids),
        "v7_confirmatory_window": [V7_CONFIRMATORY_START, V7_CONFIRMATORY_END],
        "n_prior_experiment_excluded": len(prior_ids & {str(r.fixture_id) for r in dev}),
        "prior_experiment_fixture_ids": prior,
        "n_excluded_thin_history": len(thin),
        "min_prior_matches_per_side": MIN_PRIOR_MATCHES_PER_SIDE,
        "n_eligible": len(pool),
        "selection_reads_outcomes": False,
        "selection_reads_effects": False,
        "ordering": "sha256(identifier only)",
    }
    return pool, audit


def select(records, *, oos_out_root, index=None, n=N_FIXTURES):
    """The frozen V8A development sample.

    Balanced across competitions by round-robin over competition-local hash order, so the
    sample is not dominated by the largest competition. Brief section 18 also asks for a
    MIXTURE of formation coverage and of capability coverage; both are consequences of
    picking across competitions and are REPORTED (in the capability manifest) rather than
    selected on, because selecting on coverage would be selecting on a data property.
    """
    pool, audit = eligible(records, oos_out_root=oos_out_root, index=index)

    by_comp = {}
    for r in pool:
        by_comp.setdefault(r.competition, []).append(r)
    for comp in by_comp:
        by_comp[comp].sort(key=lambda r: order_key(str(r.fixture_id)))

    chosen, ci = [], 0
    comps = sorted(by_comp)
    while len(chosen) < n and any(by_comp[c] for c in comps):
        comp = comps[ci % len(comps)]
        if by_comp[comp]:
            chosen.append(by_comp[comp].pop(0))
        ci += 1

    chosen.sort(key=lambda r: order_key(str(r.fixture_id)))
    detail = [{"fixture_id": str(r.fixture_id), "competition": r.competition,
               "season_id": str(r.season_id),
               "kickoff_unix": int(r.kickoff_unix),
               "kickoff_date": datetime.datetime.fromtimestamp(
                   int(r.kickoff_unix), datetime.UTC).date().isoformat(),
               "home_team": r.home, "away_team": r.away,
               "home_id": str(r.home_id), "away_id": str(r.away_id),
               "order_key": order_key(str(r.fixture_id))} for r in chosen]

    comp_mix = {}
    for d in detail:
        comp_mix[d["competition"]] = comp_mix.get(d["competition"], 0) + 1

    audit.update({"n_selected": len(detail), "competition_mix": comp_mix,
                  "selected_fixtures": [d["fixture_id"] for d in detail],
                  "selected_detail": detail,
                  "selection_rule": ("round-robin across competitions over "
                                     "sha256(identifier) order; no outcome, no effect, no "
                                     "coverage property is read")})
    return chosen, audit


def manifest_hash(audit: dict) -> str:
    return hashlib.sha256(
        json.dumps(audit, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
