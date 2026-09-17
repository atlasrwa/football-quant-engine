"""V8B2_RETROSPECTIVE_CORRECTED_PILOT50 -- deterministic rescore of the 50 already-exposed pilot
fixtures under the FROZEN V8B.2 scorer, across the three FROZEN arms (S, R, H).

EVIDENCE_CLASS = POST_OUTCOME_SCORER_REPAIR_DIAGNOSTIC (V8B.2 was created after these 50
outcomes were opened; this is NOT pristine confirmatory evidence).

ZERO Sonnet calls. Reuses frozen selections/controls. Touches ONLY the pilot 50; the 947 sealed
fixtures are never referenced. No apparatus/threshold/CHAMPION change.

Stage 1 (this script): per-hypothesis rescore -> V8B2_RETRO50_RESCORE.json
Stage 2 (paired aggregation) is a separate script so the numeric result can be frozen cleanly.
"""
from __future__ import annotations

import hashlib
import json
import sys

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)

FREEZE = f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"
OUT = f"{ENG}/V8B2_RETRO50_RESCORE.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(p):
    with open(f"{ROOT}/{p}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    fz = json.load(open(FREEZE))
    pilot_ids = fz["pilot_fixture_ids_ordered"]
    assert len(pilot_ids) == 50, "pilot cohort must be exactly 50"
    if _sha_file("data/discovery/pilotC_stat_mixer.json") != CHAMPION_EXPECTED:
        raise SystemExit("CHAMPION changed -- refusing rescore")

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import engine as ENGmod
    from src.research.hypothesis_v71 import execution as EX
    from src.research.hypothesis_v8b1 import search as SE
    from src.research.hypothesis_v8b2 import scorer as SC

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

    def score_one(hid, pos):
        ir = SE.resolve(hid, cap)
        if ir is None:
            return {"hypothesis_id": hid, "status": "UNRESOLVED", "score": None}
        fs = SC.score_fixture(ir, index, pos, metric=ir.target_metrics[0],
                              terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                              similarity=ctx.similarity,
                              recency=ENGmod.recency_family_for(ir), capability=cap)
        return {"hypothesis_id": hid, "status": fs.status, "score": fs.score,
                "cohort_n": fs.cohort_n, "unique_opponents": fs.unique_opponents,
                "support_status": fs.support_status,
                "support_failures": [f["field"] for f in fs.support_failures]}

    records = []
    for fid in pilot_ids:
        pos = index.pos_of_fixture[fid]
        f = fx_by[fid]
        s_ids = f["sonnet_selection_ids"]
        r_ids = [x.get("hypothesis_id") for x in R[fid]["selections"] if x["status"] == "MATCHED"]
        h_ids = H[fid]["heuristic_selection_ids"]
        for arm, ids in (("S", s_ids), ("R", r_ids), ("H", h_ids)):
            for hid in ids:
                rec = score_one(hid, pos)
                rec["fixture_id"] = fid
                rec["arm"] = arm
                records.append(rec)

    champ_after = _sha_file("data/discovery/pilotC_stat_mixer.json") == CHAMPION_EXPECTED
    out = {
        "rescore_version": "v8b2_retro50_rescore_v1",
        "label": "V8B2_RETROSPECTIVE_CORRECTED_PILOT50",
        "evidence_class": "POST_OUTCOME_SCORER_REPAIR_DIAGNOSTIC",
        "scorer_version": SC.version_stamp()["scorer_version"],
        "n_fixtures": 50,
        "touched_only_pilot_50": True,
        "sealed_947_referenced": False,
        "new_sonnet_calls": 0,
        "champion_unchanged": champ_after,
        "champion_sha256": CHAMPION_EXPECTED,
        "records": records,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, default=str)

    # quick console summary (counts are EVALUABILITY, not wins)
    from collections import Counter
    for arm in ("S", "R", "H"):
        rs = [r for r in records if r["arm"] == arm]
        st = Counter(r["status"] for r in rs)
        print(f"[rescore] {arm}: total={len(rs)} SCORE_OK={st.get('SCORE_OK',0)} "
              f"statuses={dict(st)}")
    print(f"[rescore] wrote {OUT}; champion_unchanged={champ_after}")


if __name__ == "__main__":
    main()
