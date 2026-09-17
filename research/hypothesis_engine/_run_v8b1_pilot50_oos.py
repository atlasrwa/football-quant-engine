"""V8B.1 PILOT-50 out-of-sample evaluation. CROSSES THE OUTCOME SEAL for EXACTLY the 50 pilot
fixtures (and no others) via the frozen scorer. Runs only AFTER V8B1_PILOT50_SELECTION_FREEZE.json
exists and verifies.

For each of the 50 pilot fixtures and each arm (SONNET, R=blind, H=heuristic):
  * resolve each selected hypothesis_id to its IR (frozen search grammar)
  * score_fixture(ir, index, rec_i=pos, metric=ir.target_metrics[0],
                  recency=recency_family_for(ir), ...) -- the ONLY seal-crossing call
  * ARM_SCORE(T) = mean of SCORE_OK scores only (None if zero OK)
Then paired differences D_BLIND(T)=SONNET-BLIND, D_HEUR(T)=SONNET-HEUR (listwise, both non-None)
and the frozen inference estimator.small_cluster_inference over the frozen chronological blocks.

NO change to any frozen rule. Sonnet supplies no numeric prediction. Writes
V8B1_PILOT50_OOS_RESULTS.json.  Records the exact seal-crossing set.
"""
from __future__ import annotations

import hashlib
import json
import sys

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)

FREEZE = f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"
OUT = f"{ENG}/V8B1_PILOT50_OOS_RESULTS.json"
FREEZE_EXPECTED_SELF_HASH = "5aab04f7f682e5df607e4768ed9dd804e136bc5e805f1b8157aa6d760b62c30d"

CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(p):
    with open(f"{ROOT}/{p}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _score_arm_at_fixture(hyp_ids, index, pos, ctx, cap, SE, ENGmod, SC):
    """Return (arm_score_or_None, per_selection_records)."""
    scores_ok, recs = [], []
    for hid in hyp_ids:
        ir = SE.resolve(hid, cap)
        if ir is None:
            recs.append({"hypothesis_id": hid, "status": "UNRESOLVED"})
            continue
        metric = ir.target_metrics[0]
        recency = ENGmod.recency_family_for(ir)
        fs = SC.score_fixture(ir, index, pos, metric=metric, terciles=ctx.terciles,
                              axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                              recency=recency, capability=cap)
        recs.append({"hypothesis_id": hid, "status": fs.status,
                     "score": fs.score, "support_status": fs.support_status,
                     "cohort_n": fs.cohort_n, "reason": fs.reason})
        if fs.status == "SCORE_OK" and fs.score is not None:
            scores_ok.append(fs.score)
    return (_mean(scores_ok), recs)


def main():
    # ---- gate: freeze exists + verifies, CHAMPION unchanged ----
    fz = json.load(open(FREEZE))
    if fz.get("freeze_self_hash") != FREEZE_EXPECTED_SELF_HASH:
        raise SystemExit("freeze self-hash mismatch -- refusing to open outcomes")
    if not fz.get("champion_unchanged"):
        raise SystemExit("freeze says champion changed -- refusing")
    if fz.get("target_outcomes_viewed") is not False:
        raise SystemExit("freeze already marks outcomes viewed -- refusing")
    if _sha_file(CHAMPION_ARTIFACT) != CHAMPION_EXPECTED:
        raise SystemExit("CHAMPION changed at eval time -- refusing")

    pilot_ids = fz["pilot_fixture_ids_ordered"]
    assert len(pilot_ids) == 50

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import engine as ENGmod
    from src.research.hypothesis_v71 import estimator as EST
    from src.research.hypothesis_v71 import execution as EX
    from src.research.hypothesis_v8b1 import scorer as SC
    from src.research.hypothesis_v8b1 import search as SE

    cap = CAP.CapabilityContract(
        json.load(open(f"{ROOT}/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json")))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)
    ctx = EX.build_context(index)

    R = {json.loads(l)["fixture_id"]: json.loads(l)
         for l in open(f"{ENG}/V8B1_PILOT50_CONTROL_R.jsonl")}
    H = {json.loads(l)["fixture_id"]: json.loads(l)
         for l in open(f"{ENG}/V8B1_PILOT50_CONTROL_H.jsonl")}
    fx_by = {f["fixture_id"]: f for f in fz["fixtures"]}

    # ---- SEAL CROSS: score all three arms for exactly the 50 pilot fixtures ----
    seal_crossed = []
    per_fixture = []
    D_blind, D_heur = [], []
    yield_ladder = {"selected": 0, "canonical_resolved": 0, "score_ok": 0,
                    "non_ok_measured": 0}
    for fid in pilot_ids:
        pos = index.pos_of_fixture[fid]
        seal_crossed.append(fid)
        f = fx_by[fid]

        son_ids = f["sonnet_selection_ids"]
        r_ids = [x.get("hypothesis_id") for x in R[fid]["selections"] if x["status"] == "MATCHED"]
        h_ids = H[fid]["heuristic_selection_ids"]

        son_score, son_recs = _score_arm_at_fixture(son_ids, index, pos, ctx, cap, SE, ENGmod, SC)
        r_score, r_recs = _score_arm_at_fixture(r_ids, index, pos, ctx, cap, SE, ENGmod, SC)
        h_score, h_recs = _score_arm_at_fixture(h_ids, index, pos, ctx, cap, SE, ENGmod, SC)

        # Sonnet research-yield ladder (Endpoint 1)
        yield_ladder["selected"] += len(son_ids)
        yield_ladder["canonical_resolved"] += sum(1 for r in son_recs if r["status"] != "UNRESOLVED")
        yield_ladder["score_ok"] += sum(1 for r in son_recs if r["status"] == "SCORE_OK")
        yield_ladder["non_ok_measured"] += sum(
            1 for r in son_recs if r["status"] in ("SCORE_REFUSED", "SCORE_INSUFFICIENT_SUPPORT",
                                                   "SCORE_UNDEFINED"))

        db = (son_score - r_score) if (son_score is not None and r_score is not None) else None
        dh = (son_score - h_score) if (son_score is not None and h_score is not None) else None
        if db is not None:
            D_blind.append((fid, db))
        if dh is not None:
            D_heur.append((fid, dh))

        per_fixture.append({
            "fixture_id": fid, "sonnet_status": f["sonnet_status"],
            "sonnet_arm_score": son_score, "blind_arm_score": r_score, "heuristic_arm_score": h_score,
            "D_blind": db, "D_heur": dh,
            "sonnet_scores": son_recs, "blind_scores": r_recs, "heuristic_scores": h_recs,
        })

    # ---- frozen inference over frozen chronological blocks ----
    blocks = json.load(open(f"{ENG}/V8B1_CHRONOLOGICAL_BLOCKS.json"))
    f2b = blocks["fixture_to_block"]

    def infer(pairs):
        vals = [v for _fid, v in pairs]
        cls = [f2b[fid] for fid, _v in pairs]
        n_blocks = len(set(cls))
        res = EST.small_cluster_inference(vals, cls) if vals else {
            "primary_p_value": None, "point_estimate": None, "n_clusters": 0,
            "inference_status": "NO_PAIRED_FIXTURES"}
        return {"n_paired_fixtures": len(vals), "n_blocks_spanned": n_blocks,
                "mean_difference": _mean(vals), **res}

    endpoint2 = infer(D_blind)   # Sonnet vs matched blind
    endpoint3 = infer(D_heur)    # Sonnet vs heuristic

    champ_after = _sha_file(CHAMPION_ARTIFACT) == CHAMPION_EXPECTED

    results = {
        "results_version": "v8b1_pilot50_oos_results_v1",
        "freeze_self_hash": fz["freeze_self_hash"],
        "cohort": "OUTCOME_EXPOSED_PILOT",
        "n_fixtures": 50,
        "outcome_seal_crossed_fixture_ids": seal_crossed,
        "outcome_seal_crossed_count": len(seal_crossed),
        "seal_note": "these 50 fixtures are now OUTCOME_EXPOSED_PILOT; not pristine confirmatory. "
                     "No other fixture (none of the 947, none of the 3 T2 canaries) was scored.",
        "scorer_version": SC.version_stamp()["scorer_version"],

        "endpoint1_research_yield_sonnet": yield_ladder,

        "endpoint2_sonnet_vs_blind": endpoint2,
        "endpoint3_sonnet_vs_heuristic": endpoint3,

        "evaluable_sonnet_vs_blind": endpoint2["n_paired_fixtures"],
        "evaluable_sonnet_vs_heuristic": endpoint3["n_paired_fixtures"],

        "champion_unchanged_after_eval": champ_after,
        "champion_sha256": CHAMPION_EXPECTED,
        "per_fixture": per_fixture,
    }
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)

    print(f"[oos] wrote {OUT}")
    print(f"[oos] seal_crossed={len(seal_crossed)} (must be 50)")
    print(f"[oos] research_yield={yield_ladder}")
    print(f"[oos] E2 Sonnet-vs-BLIND: n_paired={endpoint2['n_paired_fixtures']} "
          f"blocks={endpoint2['n_blocks_spanned']} point={endpoint2.get('point_estimate')} "
          f"p={endpoint2.get('primary_p_value')} status={endpoint2.get('inference_status')}")
    print(f"[oos] E3 Sonnet-vs-HEUR:  n_paired={endpoint3['n_paired_fixtures']} "
          f"blocks={endpoint3['n_blocks_spanned']} point={endpoint3.get('point_estimate')} "
          f"p={endpoint3.get('primary_p_value')} status={endpoint3.get('inference_status')}")
    print(f"[oos] champion_unchanged_after_eval={champ_after}")


if __name__ == "__main__":
    main()
