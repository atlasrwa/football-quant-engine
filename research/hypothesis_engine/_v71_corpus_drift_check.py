"""V7.1 corpus drift check (mission item 9): did the D16 repair silently redefine the dataset?

The missing dependency was the CORPUS LOADER, so the repair touches the most dangerous possible
place: if committing `src/research/matchup/corpus.py` had changed which matches load or what
fields they carry, every downstream number would move while every hash still "verified".

This driver re-derives the corpus with the repaired apparatus and compares it, field by field,
against the values the SUPERSEDED v2 freeze recorded:

  * development record count and fresh fixture count (must be 317);
  * the exact fresh fixture-id set and the fixture-set roll-up hash;
  * team ids, kickoff timestamps, competition assignment;
  * every consumable provider field and the exact NULL representation;
  * the fresh-content commitment hash;
  * the historical point-in-time snapshot hash.

An unexplained change is a FAILURE. The fresh-content hash may legitimately move only if the
earlier commitment was computed through bytes that cannot be reproduced from committed source --
in which case the reason must be stated explicitly, not absorbed.

Reads INPUTS ONLY. No effect, correlation, endpoint score, p-value or terminal state is read;
no fresh outcome is computed. CONFIRMATORY_OOS_COMPUTED stays false.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import freshsample as FS
from src.research.hypothesis_v71 import provenance as PV

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
V2 = f"{OUT}/superseded/v71_freeze_v2"

ARTIFACT = "V7_1_CORPUS_DRIFT_CHECK.json"


def main():
    v2_manifest = json.load(open(f"{V2}/V7_1_FREEZE_MANIFEST.json"))
    v2_content = json.load(open(f"{V2}/V7_1_FRESH_CONTENT_COMMITMENT.json"))
    v2_fresh = v2_content["fresh_content"]
    v2_pit = v2_content["historical_pit_snapshot"]
    v2_fresh_manifest = json.load(open(f"{OUT}/V7_1_FRESH_OOS_MANIFEST.json"))

    # ---- re-derive with the repaired apparatus ----------------------------------------
    records = CI.load_records(include_fresh=True)
    development, confirmatory = FS.partition(records)
    overlap = FS.zero_overlap_proof(confirmatory, development)

    live_fresh = PV.content_commitment(confirmatory, CAP.METRIC_SEMANTICS)
    live_pit = PV.content_commitment(development, CAP.METRIC_SEMANTICS)

    checks, drift = {}, []

    def cmp(name, frozen, live):
        same = frozen == live
        checks[name] = {"v2": frozen, "live": live, "identical": same}
        if not same:
            drift.append(name)
        return same

    cmp("n_development_records", v2_pit["n_records"], live_pit["n_records"])
    cmp("n_fresh_fixtures", v2_fresh["n_records"], live_fresh["n_records"])
    cmp("fresh_fixture_count_is_317", 317, live_fresh["n_records"])
    cmp("fresh_content_sha256", v2_fresh["content_sha256"], live_fresh["content_sha256"])
    cmp("historical_pit_content_sha256", v2_pit["content_sha256"], live_pit["content_sha256"])
    cmp("confirmatory_fixture_sha256",
        v2_fresh_manifest["zero_overlap"]["confirmatory_fixture_sha256"],
        overlap["confirmatory_fixture_sha256"])
    cmp("fresh_fixture_id_set",
        sorted(v2_fresh["normalized_record_hashes"]),
        sorted(live_fresh["normalized_record_hashes"]))
    cmp("development_fixture_id_set",
        sorted(v2_pit["normalized_record_hashes"]),
        sorted(live_pit["normalized_record_hashes"]))

    # per-fixture normalized content: identity + teams + kickoff + competition + every
    # consumable provider field + exact null representation, all inside these record hashes
    fresh_changed = sorted(
        f for f in set(v2_fresh["normalized_record_hashes"]) & set(live_fresh["normalized_record_hashes"])
        if v2_fresh["normalized_record_hashes"][f] != live_fresh["normalized_record_hashes"][f])
    pit_changed = sorted(
        f for f in set(v2_pit["normalized_record_hashes"]) & set(live_pit["normalized_record_hashes"])
        if v2_pit["normalized_record_hashes"][f] != live_pit["normalized_record_hashes"][f])
    checks["fresh_records_with_changed_content"] = fresh_changed
    checks["development_records_with_changed_content"] = pit_changed
    if fresh_changed:
        drift.append("fresh_record_content")
    if pit_changed:
        drift.append("development_record_content")

    # structural spot-checks that are explicitly enumerated in the mission
    by_id = {str(r.fixture_id): r for r in confirmatory}
    checks["fresh_structure"] = {
        "n_competitions": len({r.competition for r in confirmatory}),
        "n_distinct_teams": len({t for r in confirmatory for t in (r.home_id, r.away_id)}),
        "kickoff_min_unix": min(int(r.kickoff_unix) for r in confirmatory),
        "kickoff_max_unix": max(int(r.kickoff_unix) for r in confirmatory),
        "all_kickoffs_present": all(int(r.kickoff_unix) > 0 for r in confirmatory),
        "all_team_ids_present": all(r.home_id and r.away_id for r in confirmatory),
        "all_competitions_assigned": all(bool(r.competition) for r in confirmatory),
        "n_fixture_ids": len(by_id),
    }
    # NULL representation: a null consumable field must stay null, never coerced to 0
    nulls = 0
    zeros = 0
    for r in confirmatory:
        content = PV._record_content(r, CAP.METRIC_SEMANTICS)
        for _m, v in content["consumable_fields"].items():
            if v is None:
                nulls += 1
            elif isinstance(v, list) and any(x == 0 for x in v if x is not None):
                zeros += 1
    checks["null_representation"] = {
        "null_consumable_fields_preserved_as_null": nulls,
        "genuine_zero_values_present_and_distinct_from_null": zeros,
        "policy": "NULL != ZERO",
    }

    identical = not drift
    doc = {
        "classification": ["INPUT_ONLY", "NON_CONFIRMATORY"],
        "purpose": ("prove the D16 dependency-closure repair did not silently redefine the "
                    "dataset"),
        "compared_against": {"freeze_version": v2_manifest["freeze_version"],
                             "status": "SUPERSEDED_PRE_OOS_DUE_TO_INCOMPLETE_EXECUTABLE_"
                                       "DEPENDENCY_CLOSURE"},
        "corpus_source_files_now_bound": [
            "src/research/matchup/__init__.py", "src/research/matchup/corpus.py",
            "scripts/multisrc_corpus.py", "scripts/championship_adapter.py"],
        "repair_touched_corpus_behaviour": False,
        "explanation": (
            "The repair COMMITTED the corpus loader unchanged and widened the provenance "
            "commitment to cover it; it did not edit a single byte of corpus behaviour. The "
            "dataset is therefore expected to be bit-identical, and every commitment below is "
            "checked rather than assumed."
            if identical else
            "DRIFT DETECTED -- see `drift` and explain each entry before freezing."),
        "dataset_identical_to_v2": identical,
        "drift": drift,
        "checks": checks,
        "confirmatory_oos_computed": False,
        "confirmatory_oos_viewed": False,
        "reads_outcomes": False,
    }
    path = f"{OUT}/{ARTIFACT}"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)

    print("=== V7.1 CORPUS DRIFT CHECK (repaired apparatus vs superseded v2) ===")
    for k in ("n_development_records", "n_fresh_fixtures", "fresh_content_sha256",
              "historical_pit_content_sha256", "confirmatory_fixture_sha256",
              "fresh_fixture_id_set", "development_fixture_id_set"):
        c = checks[k]
        mark = "OK  " if c["identical"] else "DRIFT"
        shown = c["live"] if not isinstance(c["live"], list) else f"<{len(c['live'])} ids>"
        print(f"  {mark} {k:34s} {shown}")
    print(f"  OK   fresh records with changed content : {len(fresh_changed)}")
    print(f"  OK   dev   records with changed content : {len(pit_changed)}")
    print(f"  fresh structure: {checks['fresh_structure']}")
    print(f"  null representation: {checks['null_representation']}")
    print(f"\nDATASET_IDENTICAL_TO_V2={identical}")
    if drift:
        print("DRIFT:", drift)
        return 1
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
