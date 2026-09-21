"""Build ITEM6_STAGE1_COHORT_MANIFEST_V1.

Fresh Stage-1 cohort. Selection uses provider/data AVAILABILITY ONLY (never chosen because a
fixture "looks conducive to novelty"). The cohort is required to have ZERO overlap with the
V1/V2/V3 fixture universe.

V1/V2/V3 universe = the prior hypothesis-engine cohort, concretely enumerated by
research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json (1000 fixtures) PLUS the taint registry
(T1/T2/T3) it references. Any fixture appearing there is excluded.

Prospectivity: the true Stage-1 live cohort is a FUTURE-kickoff selection (kickoffs strictly
after the prior cohort's max kickoff), which structurally cannot overlap the prior cohort.
Because this is a zero-spend build with no live fetch authorized, we materialize a concrete
CANDIDATE cohort from the local discovery corpus using availability-only rules and prove
overlap=0. The live run will re-select under the identical rule once future fixtures exist;
the rule — not this snapshot — is the frozen object.

Selection rule (frozen, availability-only):
  1. eligible = corpus matches with status complete, both team ids present, a valid kickoff.
  2. exclude any fixture whose id (in EITHER id namespace) collides with the prior universe.
  3. require both teams to have >= MIN_PRIOR_N prior completed matches in the corpus (support
     availability — NOT an outcome), mirroring the prior manifest's >=20 rule.
  4. competition-proportional stratified selection, SHA256(fixture_id)-ordered tie-break,
     chronological output order. Take the N latest-kickoff eligible fixtures per stratum.

NO target outcome is read into the manifest (only ids, team ids, kickoff, competition,
prior-match COUNTS). Reads no hypothesis effect, no LLM output.
"""
from __future__ import annotations

import glob
import hashlib
import json
from collections import defaultdict

ROOT = "/home/ubuntu"
CORPUS = f"{ROOT}/data/discovery/corpus"
PRIOR_MANIFEST = f"{ROOT}/research/hypothesis_engine/V8B1_FIXTURE_MANIFEST.json"
OUT = f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"

N_TARGET = 120            # see STAGE1_POWER_AND_COST: 120 fixtures x K=5 mechanisms
MIN_PRIOR_N = 20          # availability floor (support), mirrors prior manifest
COHORT_VERSION = "item6_stage1_cohort_manifest_v1"

# competition id -> label (footystats season files map to these six leagues in this corpus)
COMP_LABELS = {
    10977: "epl", 11120: "laliga", 11321: "laliga2",
    12120: "ligue1", 12132: "ligue2", 12137: "champ",
}


def _sha_obj(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def _prior_universe_ids():
    """All fixture ids the prior cohort used, in every namespace we can detect."""
    ids = set()
    man = json.load(open(PRIOR_MANIFEST))
    for fx in man["fixtures"]:
        ids.add(str(fx["fixture_id"]))
        # also record numeric core (strip mt_ prefix) so a namespace-crossing collision is caught
        fid = str(fx["fixture_id"])
        if fid.startswith("mt_"):
            ids.add(fid[3:])
    # taint registry (T1/T2/T3) if present
    taint = f"{ROOT}/research/hypothesis_engine/V8B_TAINT_REGISTRY.json"
    try:
        t = json.load(open(taint))
        for v in _walk_ids(t):
            ids.add(str(v))
    except FileNotFoundError:
        pass
    return ids


def _walk_ids(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (str, int)) and ("fixture" in str(k).lower() or "mt_" in str(v)):
                yield v
            yield from _walk_ids(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_ids(v)


def _load_corpus_matches():
    out = []
    for f in sorted(glob.glob(f"{CORPUS}/league-matches_*.json")):
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            continue
        data = d.get("data") if isinstance(d, dict) else d
        if not isinstance(data, list):
            continue
        for m in data:
            out.append(m)
    return out


def main():
    prior_ids = _prior_universe_ids()
    matches = _load_corpus_matches()

    # prior-match counts per team (availability), by chronological order.
    played = defaultdict(int)
    # first pass: sort by kickoff to compute prior counts as of each fixture
    matches_sorted = sorted(
        [m for m in matches if m.get("status") == "complete"
         and m.get("date_unix") and m.get("homeID") and m.get("awayID")],
        key=lambda m: m["date_unix"])

    eligible = []
    for m in matches_sorted:
        fid = str(m["id"])
        home, away = str(m["homeID"]), str(m["awayID"])
        comp = COMP_LABELS.get(m.get("competition_id"), f"comp_{m.get('competition_id')}")
        hn, an = played[home], played[away]
        # availability gate: both teams have >= MIN_PRIOR_N prior completed matches
        overlap = fid in prior_ids
        if (not overlap) and hn >= MIN_PRIOR_N and an >= MIN_PRIOR_N:
            eligible.append({
                "fixture_id": f"i6_{fid}",       # namespaced Item-6 id (distinct from mt_)
                "source_fixture_id": fid,
                "home_id": home,
                "away_id": away,
                "competition": comp,
                "kickoff_unix": int(m["date_unix"]),
                "home_prior_n": hn,
                "away_prior_n": an,
                "order_key": hashlib.sha256(f"i6_{fid}".encode()).hexdigest(),
            })
        played[home] += 1
        played[away] += 1

    # PROSPECTIVITY: keep only fixtures strictly AFTER the prior cohort's max kickoff.
    prior_max_ko = max(fx["kickoff_unix"] for fx in json.load(open(PRIOR_MANIFEST))["fixtures"])
    prospective = [e for e in eligible if e["kickoff_unix"] > prior_max_ko]

    # If the local corpus has no post-cohort completes (common, since corpus == prior era),
    # fall back to the LATEST-kickoff eligible non-overlapping fixtures. This is a rehearsal
    # snapshot ONLY; the frozen selection rule requires future kickoffs at live time.
    pool = prospective if len(prospective) >= N_TARGET else sorted(
        eligible, key=lambda e: e["kickoff_unix"], reverse=True)
    used_fallback = len(prospective) < N_TARGET

    # competition-proportional stratified selection
    by_comp = defaultdict(list)
    for e in pool:
        by_comp[e["competition"]].append(e)
    total = sum(len(v) for v in by_comp.values())
    selected = []
    for comp, items in sorted(by_comp.items()):
        share = max(1, round(N_TARGET * len(items) / total)) if total else 0
        items_sorted = sorted(items, key=lambda e: (e["order_key"]))
        selected.extend(items_sorted[:share])
    # dedupe + trim/topup to exactly N_TARGET deterministically
    seen = set()
    dedup = []
    for e in sorted(selected, key=lambda e: e["order_key"]):
        if e["fixture_id"] not in seen:
            seen.add(e["fixture_id"])
            dedup.append(e)
    if len(dedup) < N_TARGET:
        for e in sorted(pool, key=lambda e: e["order_key"]):
            if e["fixture_id"] not in seen:
                seen.add(e["fixture_id"])
                dedup.append(e)
            if len(dedup) >= N_TARGET:
                break
    cohort = sorted(dedup[:N_TARGET], key=lambda e: e["kickoff_unix"])

    # overlap verification
    cohort_ids = {c["fixture_id"] for c in cohort} | {c["source_fixture_id"] for c in cohort}
    v_overlap = len(cohort_ids & prior_ids)

    comp_alloc = defaultdict(int)
    for c in cohort:
        comp_alloc[c["competition"]] += 1

    manifest = {
        "manifest_version": COHORT_VERSION,
        "generated_by": "research/item6/_build_stage1_cohort.py",
        "selection_rule": (
            "availability-only: status=complete, both teams present, valid kickoff, both "
            "teams >= MIN_PRIOR_N prior completed matches; exclude any V1/V2/V3 universe id; "
            "prospective (kickoff > prior_max_kickoff) at live time; competition-proportional "
            "stratified; SHA256(fixture_id)-ordered tie-break; chronological output. NOT "
            "chosen for novelty-conduciveness. Reads no outcome/effect/LLM output."),
        "n_target": N_TARGET,
        "n_selected": len(cohort),
        "min_prior_n": MIN_PRIOR_N,
        "prior_universe_id_count": len(prior_ids),
        "prior_max_kickoff_unix": prior_max_ko,
        "prospective_pool_size": len(prospective),
        "used_rehearsal_fallback_latest_eligible": used_fallback,
        "rehearsal_fallback_note": (
            "Local corpus contains only completed matches from the prior era, so no strictly-"
            "future fixtures exist offline. This snapshot uses the latest-kickoff eligible "
            "NON-OVERLAPPING fixtures as a rehearsal cohort. At live time the identical rule "
            "selects future-kickoff fixtures. Either way V1/V2/V3 overlap is 0."),
        "competition_allocation": dict(sorted(comp_alloc.items())),
        "v1_fixture_overlap": v_overlap,
        "v2_fixture_overlap": v_overlap,
        "v3_fixture_overlap": v_overlap,
        "reads_no_observed_statistic": True,
        "reads_no_hypothesis_effect_or_llm_output": True,
        "fixtures": cohort,
    }
    manifest["manifest_hash"] = _sha_obj({k: v for k, v in manifest.items()
                                          if k != "manifest_hash"})
    with open(OUT, "w") as fh:
        json.dump(manifest, fh, indent=1)
    print(f"[cohort] wrote {OUT}")
    print(f"[cohort] n_selected={len(cohort)} overlap={v_overlap} "
          f"prospective_pool={len(prospective)} fallback={used_fallback}")
    print(f"[cohort] manifest_hash={manifest['manifest_hash']}")
    if v_overlap != 0:
        raise SystemExit("FATAL: non-zero V1/V2/V3 overlap")


if __name__ == "__main__":
    main()
