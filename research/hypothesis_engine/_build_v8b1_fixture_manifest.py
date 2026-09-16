"""Builds V8B1_FIXTURE_MANIFEST.json -- the frozen, deterministic ~1000-fixture target set for
the V8B.1 retrospective LLM-selection-policy experiment.

Frozen BEFORE any Sonnet call, BEFORE any control-arm selection, and BEFORE any target outcome
is opened for scoring purposes (reading a fixture's own kickoff_unix/home/away/competition to
decide ELIGIBILITY is not "opening its outcome" -- eligibility never reads goals/shots/cards/
observed statistics, only structural metadata already used by the corpus loader itself).

Selection rule (stated in full, applied mechanically, no manual curation):
  1. Universe = the full cached corpus (src.research.hypothesis_v71.corpus_index.load_records).
  2. Taint exclusion: remove every T1 fixture (V8B_TAINT_REGISTRY.json). T2/T3 fixtures REMAIN
     eligible -- this is a RETROSPECTIVE POLICY EVALUATION, not a pristine-confirmation claim
     (per explicit instruction; see the taint registry's own pristine_reservation_finding).
  3. Prehistory sufficiency: BOTH the home and away team must have >= MIN_RAW_N=20 prior
     matches (src.research.hypothesis_v7.pit.MIN_RAW_N, the SAME frozen threshold the
     compiler's own support gate uses elsewhere in this codebase -- not a new number invented
     for this manifest) strictly before the fixture's own kickoff_unix. This is necessary for
     ANY hypothesis to have a chance at SCORE_OK; a fixture failing this would only ever
     produce SCORE_INSUFFICIENT_SUPPORT selections and would waste a Sonnet call.
  4. Chronological eligibility: fixture must have a resolved status/score (i.e. it is a
     completed match with an observed outcome to eventually score against -- checked via the
     same admission filter corpus_index.load_records already applies; no additional filter).
  5. Competition stratification: draw proportionally to each competition's share of the
     eligible pool (after steps 2-4), rounding deterministically (largest-remainder method,
     ties broken by competition name) so no competition is silently over/under-represented
     relative to its actual presence in the eligible pool.
  6. Deterministic tie-breaking / final selection WITHIN each competition's stratum: sort
     eligible fixtures by SHA-256(fixture_id) (the same hash-of-identifier-only ordering
     V6.1's own fixture_selection.json already used, reused here rather than reinvented), take
     the stratum's allocated count from the front of that order.
  7. Target N = 1000, or the full eligible pool if smaller (never inflated by re-including
     excluded fixtures).

No step reads goals, shots, cards, xG, or any other observed match statistic. No step reads
any hypothesis-level effect, p-value, or OOS status. No step is informed by any LLM output.
"""
from __future__ import annotations

import hashlib
import json
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)

TARGET_N = 1000


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def build() -> dict:
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v7 import pit as V7PIT

    recs = CI.load_records(include_fresh=True)
    recs_sorted = sorted(recs, key=lambda r: (int(r.kickoff_unix), str(r.fixture_id)))
    pos_by_fixture = {str(r.fixture_id): i for i, r in enumerate(recs_sorted)}

    # ---- prior-match counts per team, strictly before each fixture (single pass) --------
    team_prior_count = {}   # (team_id, position) -> count of that team's PRIOR matches
    running = {}
    for i, r in enumerate(recs_sorted):
        team_prior_count[(str(r.home_id), i)] = running.get(str(r.home_id), 0)
        team_prior_count[(str(r.away_id), i)] = running.get(str(r.away_id), 0)
        running[str(r.home_id)] = running.get(str(r.home_id), 0) + 1
        running[str(r.away_id)] = running.get(str(r.away_id), 0) + 1

    registry = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B_TAINT_REGISTRY.json"))
    t1 = set(registry["t1_ids"])

    eligible = []
    for i, r in enumerate(recs_sorted):
        fid = str(r.fixture_id)
        if fid in t1:
            continue
        home_prior = team_prior_count.get((str(r.home_id), i), 0)
        away_prior = team_prior_count.get((str(r.away_id), i), 0)
        if home_prior < V7PIT.MIN_RAW_N or away_prior < V7PIT.MIN_RAW_N:
            continue
        eligible.append({
            "fixture_id": fid, "competition": r.competition, "kickoff_unix": int(r.kickoff_unix),
            "home_id": str(r.home_id), "away_id": str(r.away_id),
            "home_prior_n": home_prior, "away_prior_n": away_prior,
            "order_key": _sha(fid),
        })

    n_eligible = len(eligible)
    target_n = min(TARGET_N, n_eligible)

    # ---- proportional stratification by competition, largest-remainder rounding ---------
    by_comp = {}
    for e in eligible:
        by_comp.setdefault(e["competition"], []).append(e)
    comp_order = sorted(by_comp.keys())
    raw_alloc = {c: len(by_comp[c]) / n_eligible * target_n for c in comp_order}
    base_alloc = {c: int(raw_alloc[c]) for c in comp_order}
    remainder = target_n - sum(base_alloc.values())
    # largest-remainder method, ties broken alphabetically by competition name (deterministic)
    fractional = sorted(comp_order, key=lambda c: (-(raw_alloc[c] - base_alloc[c]), c))
    for c in fractional[:remainder]:
        base_alloc[c] += 1
    # never allocate more than a competition actually has available
    for c in comp_order:
        base_alloc[c] = min(base_alloc[c], len(by_comp[c]))
    shortfall = target_n - sum(base_alloc.values())
    if shortfall > 0:
        # redistribute any shortfall (from a competition being capped) to competitions with
        # remaining capacity, largest-pool-first, deterministic
        capacity_order = sorted(comp_order, key=lambda c: (-(len(by_comp[c]) - base_alloc[c]), c))
        for c in capacity_order:
            if shortfall <= 0:
                break
            room = len(by_comp[c]) - base_alloc[c]
            take = min(room, shortfall)
            base_alloc[c] += take
            shortfall -= take

    selected = []
    for c in comp_order:
        pool = sorted(by_comp[c], key=lambda e: e["order_key"])
        selected.extend(pool[:base_alloc[c]])

    selected.sort(key=lambda e: (e["kickoff_unix"], e["fixture_id"]))  # chronological output order

    manifest = {
        "manifest_version": "v8b1_fixture_manifest_v1",
        "generated_by": "research/hypothesis_engine/_build_v8b1_fixture_manifest.py",
        "evidence_label": "RETROSPECTIVE_POLICY_EVALUATION",
        "evidence_label_note": (
            "T1 fixtures excluded. T2/T3 fixtures (infrastructure-touched / incidentally "
            "present in aggregate development-corpus statistics) ARE included, per explicit "
            "instruction to use ~1000 cached fixtures even though a fully pristine "
            "confirmation set does not exist in the current cache (see "
            "V8B_TAINT_REGISTRY.json:pristine_reservation_finding). This experiment's result "
            "must be reported as RETROSPECTIVE, never as a pristine out-of-sample "
            "confirmation."),
        "selection_rule": (
            "taint(T1)-excluded, prehistory>=MIN_RAW_N=20 both teams, competition-"
            "proportional stratified, SHA256(fixture_id)-ordered tie-break within stratum, "
            "chronological output order. Fixed before any Sonnet call, before any control-arm "
            "selection, before any target outcome is opened for scoring."),
        "min_raw_n_threshold": V7PIT.MIN_RAW_N,
        "min_raw_n_threshold_source": V7PIT.PIT_VERSION,
        "n_corpus_total": len(recs_sorted),
        "n_t1_excluded_from_universe": len(t1),
        "n_eligible_after_taint_and_prehistory_filters": n_eligible,
        "n_target_requested": TARGET_N,
        "n_selected": len(selected),
        "shortfall_from_target": TARGET_N - len(selected),
        "competition_allocation": {c: base_alloc[c] for c in comp_order},
        "competition_eligible_pool_sizes": {c: len(by_comp[c]) for c in comp_order},
        "fixtures": selected,
        "reads_no_observed_statistic": True,
        "reads_no_hypothesis_effect_or_llm_output": True,
    }
    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return manifest


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    print(f"n_eligible={out['n_eligible_after_taint_and_prehistory_filters']} "
          f"n_selected={out['n_selected']} shortfall={out['shortfall_from_target']}")
    print("competition allocation:", out["competition_allocation"])
    print("hash:", out["manifest_hash"][:16])
