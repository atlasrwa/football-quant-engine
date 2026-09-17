"""V8B2_EXPOSED50_SCORER_REGRESSION -- apparatus diagnostic ONLY (NOT a new scientific run).

Runs the NEW V8B.2 fixture scorer over the 50 already-outcome-EXPOSED pilot fixtures, across
the three ALREADY-FROZEN arms (Sonnet, R matched-blind, H heuristic). Purpose: demonstrate the
scorer operates sensibly on real corpus data -- SCORE_OK is reachable, attrition is not
universally 100%, reason codes are accurate, scoring is deterministic.

CONSTRAINTS:
  * ZERO paid Sonnet calls (reuses V8B1_TRANCHE_50_SELECTIONS.json + V8B1_PILOT50_CONTROL_*.jsonl).
  * Touches ONLY the 50 exposed pilot fixtures. The 947 sealed fixtures are NEVER referenced.
  * Thresholds are NOT chosen from any Sonnet-vs-control difference; this script only reports
    support statistics and SCORE_OK rates. No tuning.
"""
from __future__ import annotations

import hashlib
import json
import sys

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)

FREEZE = f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"
OUT = f"{ENG}/V8B2_EXPOSED50_SCORER_REGRESSION.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(p):
    with open(f"{ROOT}/{p}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _pctiles(xs):
    xs = sorted(v for v in xs if v is not None)
    if not xs:
        return {"p50": None, "p95": None, "max": None, "min": None, "n": 0}
    def q(p):
        if len(xs) == 1:
            return xs[0]
        i = min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))
        return xs[i]
    return {"p50": q(0.50), "p95": q(0.95), "max": xs[-1], "min": xs[0], "n": len(xs)}


def main():
    fz = json.load(open(FREEZE))
    pilot_ids = fz["pilot_fixture_ids_ordered"]
    assert len(pilot_ids) == 50
    if _sha_file("data/discovery/pilotC_stat_mixer.json") != CHAMPION_EXPECTED:
        raise SystemExit("CHAMPION changed -- refusing regression run")

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import engine as ENGmod
    from src.research.hypothesis_v71 import execution as EX
    from src.research.hypothesis_v8b1 import search as SE
    from src.research.hypothesis_v8b2 import scorer as SC
    from src.research.hypothesis_v8b2 import support as SUP

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

    arms = {"SONNET": {}, "R": {}, "H": {}}
    # per-arm accumulators
    for a in arms:
        arms[a] = {"n_scored": 0, "score_ok": 0, "status_counts": {}, "failure_field_counts": {},
                   "raw_n": [], "unique_fixtures": [], "unique_opponents": [],
                   "effective_n": [], "weight_concentration": []}

    import src.research.hypothesis_v7.pit as V7PIT

    def score_ids(hyp_ids, pos, acc):
        for hid in hyp_ids:
            ir = SE.resolve(hid, cap)
            if ir is None:
                acc["status_counts"]["UNRESOLVED"] = acc["status_counts"].get("UNRESOLVED", 0) + 1
                continue
            fs = SC.score_fixture(ir, index, pos, metric=ir.target_metrics[0],
                                  terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                  similarity=ctx.similarity,
                                  recency=ENGmod.recency_family_for(ir), capability=cap)
            acc["n_scored"] += 1
            acc["status_counts"][fs.status] = acc["status_counts"].get(fs.status, 0) + 1
            if fs.status == SC.SCORE_OK:
                acc["score_ok"] += 1
            for f in fs.support_failures:
                acc["failure_field_counts"][f["field"]] = \
                    acc["failure_field_counts"].get(f["field"], 0) + 1
            # capture support distributions whenever cohort was compiled (support was evaluated)
            if fs.cohort_n is not None:
                acc["raw_n"].append(fs.cohort_n)
                if fs.unique_opponents is not None:
                    acc["unique_opponents"].append(fs.unique_opponents)

    for fid in pilot_ids:
        pos = index.pos_of_fixture[fid]
        f = fx_by[fid]
        score_ids(f["sonnet_selection_ids"], pos, arms["SONNET"])
        r_ids = [x.get("hypothesis_id") for x in R[fid]["selections"] if x["status"] == "MATCHED"]
        score_ids(r_ids, pos, arms["R"])
        score_ids(H[fid]["heuristic_selection_ids"], pos, arms["H"])

    # To also report unique_fixtures/effective_n/weight_concentration distributions we recompute
    # the compiled support quantities directly (deterministic, PIT-safe) for the Sonnet arm as
    # the representative real-corpus sample.
    from src.research.hypothesis_v71 import compiler as CO
    for fid in pilot_ids:
        pos = index.pos_of_fixture[fid]
        for hid in fx_by[fid]["sonnet_selection_ids"]:
            ir = SE.resolve(hid, cap)
            if ir is None:
                continue
            try:
                recency = ENGmod.recency_family_for(ir)
                q = CO.compile_query(ir, index, pos, metric=ir.target_metrics[0],
                                     terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                     similarity=ctx.similarity, recency=recency[0],
                                     capability=cap, collect_fixtures=True)
            except Exception:
                continue
            arms["SONNET"]["unique_fixtures"].append(len(q.cohort_fixtures))
            arms["SONNET"]["effective_n"].append(V7PIT.kish_effective_n(q.cohort_weights))
            arms["SONNET"]["weight_concentration"].append(
                V7PIT.weight_concentration(q.cohort_weights))

    champ_after = _sha_file("data/discovery/pilotC_stat_mixer.json") == CHAMPION_EXPECTED

    out = {
        "regression_version": "v8b2_exposed50_scorer_regression_v1",
        "label": "V8B2_EXPOSED50_SCORER_REGRESSION",
        "purpose": "apparatus diagnostic: prove the V8B.2 scorer operates sensibly on real "
                   "corpus data. NOT a scientific evaluation; no threshold tuned on outcomes.",
        "scorer_version": SC.version_stamp()["scorer_version"],
        "support_version": SUP.version_stamp()["fixture_support_version"],
        "n_fixtures": 50,
        "touched_only_pilot_50": True,
        "sealed_947_referenced": False,
        "champion_unchanged": champ_after,
        "arms": {},
    }
    for a, acc in arms.items():
        out["arms"][a] = {
            "n_scored": acc["n_scored"],
            "score_ok": acc["score_ok"],
            "score_ok_rate": round(acc["score_ok"] / acc["n_scored"], 4) if acc["n_scored"] else None,
            "status_counts": acc["status_counts"],
            "failure_field_counts": acc["failure_field_counts"],
            "raw_n": _pctiles(acc["raw_n"]),
            "unique_fixtures": _pctiles(acc["unique_fixtures"]),
            "unique_opponents": _pctiles(acc["unique_opponents"]),
            "effective_n": _pctiles(acc["effective_n"]),
            "weight_concentration": _pctiles(acc["weight_concentration"]),
        }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, default=str)

    print(f"[regression] wrote {OUT}")
    for a in ("SONNET", "R", "H"):
        z = out["arms"][a]
        print(f"[regression] {a}: scored={z['n_scored']} SCORE_OK={z['score_ok']} "
              f"rate={z['score_ok_rate']} statuses={z['status_counts']}")
        print(f"             failures={z['failure_field_counts']}")
    s = out["arms"]["SONNET"]
    print(f"[regression] SONNET raw_n={s['raw_n']} uniq_opp={s['unique_opponents']} "
          f"uniq_fix={s['unique_fixtures']} eff_n={s['effective_n']} "
          f"conc={s['weight_concentration']}")
    print(f"[regression] champion_unchanged={champ_after}")


if __name__ == "__main__":
    main()
