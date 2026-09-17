"""V8C structural replay of the 50 already-exposed pilot fixtures (§22).

EVIDENCE_CLASS = DEVELOPMENT_APPARATUS_DIAGNOSTIC. These 50 outcomes were opened in V8B.1;
they are development data, NOT pristine OOS evidence, and nothing here may be used to claim a
fresh Sonnet advantage or to choose a threshold (§21).

What it reports, all STRUCTURAL / EVALUABILITY -- never effect direction or magnitude:
  * admissible universe size and PRE-T EVALUABLE universe size, per fixture
  * how many historical Sonnet selections remain pre-T eligible vs pre-T ineligible, with the
    named reason for each ineligibility
  * distinct-R coverage and R IDENTITY COUNT under V8C's repaired control (§12)
  * the same identity count under the OLD V8B.1 control, to size the defect
  * H selection availability over the same universe
  * potential paired S-v-R and S-v-H coverage
  * the §8 consistency invariant, checked against the real post-T scorer on all three arms

ZERO Sonnet calls. Touches ONLY the exposed 50. The 947 are never referenced.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
sys.path.insert(0, ROOT)

FREEZE = f"{ENG}/V8B1_PILOT50_SELECTION_FREEZE.json"
OUT = f"{ENG}/V8C_EXPOSED50_STRUCTURAL_REPLAY.json"


def main():
    from src.research.hypothesis_v71 import engine as ENGmod
    from src.research.hypothesis_v8b1 import controls as V8B1C
    from src.research.hypothesis_v8b1 import search as SE
    from src.research.hypothesis_v8b2 import scorer as SC
    from src.research.hypothesis_v8c import aggregate as AG
    from src.research.hypothesis_v8c import controls as CTL
    from src.research.hypothesis_v8c import harness as H
    from src.research.hypothesis_v8c import pre_t as PT
    from src.research.hypothesis_v8c import universe as UNI

    champ_before = H.assert_champion_unchanged()
    cap, index, _ = H.build(check_champion=False)
    sim = H.fresh_similarity(index)

    fz = json.load(open(FREEZE))
    pilot_ids = fz["pilot_fixture_ids_ordered"]
    assert len(pilot_ids) == 50, "pilot cohort must be exactly 50"
    fx_by = {f["fixture_id"]: f for f in fz["fixtures"]}

    per_fixture, records = [], []
    pre_t_status_totals = Counter()
    s_eligible_total = s_ineligible_total = 0
    s_ineligible_reasons = Counter()
    r_identity_v8c = r_identity_v8b1 = 0
    r_matched = r_unmatched = 0
    r_tiers = Counter()
    invariant_violations = []
    t0 = time.time()

    for n, fid in enumerate(pilot_ids, 1):
        pos = index.pos_of_fixture[fid]
        ctx = H.target_context(index, pos, similarity_engine=sim)
        fu = UNI.build_fixture_universe(index, pos, ctx=ctx, capability=cap, fixture_id=fid)
        pre_t_status_totals.update(fu.status_counts)
        evaluable_ids = set(fu.evaluable_ids())

        # ---- historical Sonnet selections: still eligible under V8C? --------------------
        s_ids = fx_by[fid]["sonnet_selection_ids"]
        s_rows, s_shapes_eligible = [], []
        for hid in s_ids:
            ir = SE.resolve(hid, cap)
            if ir is None:
                s_rows.append({"hypothesis_id": hid, "pre_t_status": "UNRESOLVED"})
                s_ineligible_reasons["UNRESOLVED"] += 1
                s_ineligible_total += 1
                continue
            v = PT.evaluate_candidate(ir, index, pos, ctx=ctx, capability=cap)
            s_rows.append({"hypothesis_id": hid, "pre_t_status": v.status,
                           "raw_n": v.raw_n, "unique_fixtures": v.unique_fixtures,
                           "unique_opponents": v.unique_opponents,
                           "effective_n": v.effective_n})
            if v.evaluable:
                s_eligible_total += 1
                cand = next((c for c in fu.evaluable if c["hypothesis_id"] == hid), None)
                if cand is not None:
                    s_shapes_eligible.append(CTL.shape_of(cand))
            else:
                s_ineligible_total += 1
                s_ineligible_reasons[v.status] += 1

        # ---- Arm R under V8C (distinct) and under V8B.1 (identity permitted) ------------
        r_out = CTL.blind_selections_for_fixture(s_shapes_eligible, fu)
        r_identity_v8c += r_out["identity_count"]
        r_matched += r_out["n_matched"]
        r_unmatched += r_out["n_unmatched"]
        for sel in r_out["selections"]:
            if sel["status"] == CTL.MATCHED:
                r_tiers[sel["matched_tier"]] += 1

        old_identity = 0
        used = set()
        for shape in s_shapes_eligible:
            m = V8B1C.match_blind_control(shape, cap, used)
            if m is not None:
                used.add(m["hypothesis_id"])
                if m["hypothesis_id"] == shape.hypothesis_id:
                    old_identity += 1
        r_identity_v8b1 += old_identity

        # ---- Arm H over the SAME universe ----------------------------------------------
        k_valid = len(s_shapes_eligible)
        h_out = CTL.heuristic_selections_for_fixture(k_valid, fu)

        # ---- post-T scoring, permitted on the EXPOSED 50 only ---------------------------
        def score(hid):
            ir = SE.resolve(hid, cap)
            if ir is None:
                return {"hypothesis_id": hid, "status": "UNRESOLVED", "score": None}
            fs = SC.score_fixture(ir, index, pos, metric=ir.target_metrics[0],
                                  terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                  similarity=ctx.similarity,
                                  recency=ENGmod.recency_family_for(ir), capability=cap)
            return {"hypothesis_id": hid, "status": fs.status, "score": fs.score,
                    "reason": fs.reason}

        arm_ids = {
            "S": [s.hypothesis_id for s in s_shapes_eligible],
            "R": [sel["hypothesis_id"] for sel in r_out["selections"]
                  if sel["status"] == CTL.MATCHED],
            "H": [sel["hypothesis_id"] for sel in h_out["selections"]],
        }
        for arm, ids in arm_ids.items():
            for hid in ids:
                rec = score(hid)
                rec["fixture_id"] = fid
                rec["arm"] = arm
                records.append(rec)
                # §8 consistency invariant: every id here was PRE_T_EVALUABLE.
                if rec["status"] not in PT.PERMITTED_POST_T_STATUSES or (
                        rec["status"] == SC.SCORE_REFUSED
                        and PT.PERMITTED_REFUSAL_REASON not in rec.get("reason", "")):
                    invariant_violations.append(
                        {"fixture_id": fid, "arm": arm, "hypothesis_id": hid,
                         "post_t_status": rec["status"], "reason": rec.get("reason")})

        per_fixture.append({
            "fixture_id": fid,
            "competition": index.recs[pos].competition,
            "ledger": fu.ledger(),
            "n_admissible": fu.n_admissible,
            "n_pre_t_evaluable": fu.n_evaluable,
            "n_metrics_represented": len({c["target_metrics"][0] for c in fu.evaluable}),
            "n_mechanism_types_represented": len({c["comparator"] for c in fu.evaluable}),
            "sonnet_selections": s_rows,
            "n_sonnet_total": len(s_ids),
            "n_sonnet_pre_t_eligible": len(s_shapes_eligible),
            "r_k_valid": r_out["k_valid"], "r_matched": r_out["n_matched"],
            "r_unmatched": r_out["n_unmatched"],
            "r_identity_count_v8c": r_out["identity_count"],
            "r_identity_count_v8b1": old_identity,
            "r_cross_pair_overlap": r_out["cross_pair_overlap_count"],
            "h_status": h_out.get("status"), "h_n_selected": h_out["n_selected"],
            "h_n_ranked_over": h_out.get("n_ranked_over", 0),
        })
        print(f"[replay] {n:2d}/50 {fid} adm={fu.n_admissible} eval={fu.n_evaluable} "
              f"S_elig={len(s_shapes_eligible)}/{len(s_ids)} R_m={r_out['n_matched']} "
              f"R_id={r_out['identity_count']}(old {old_identity}) H={h_out['n_selected']} "
              f"[{time.time()-t0:.0f}s]", flush=True)

    # ---- arm aggregation + paired coverage over the exposed 50 -------------------------
    per_arm = AG.per_fixture_arm_scores(records, pilot_ids)
    blocks = AG.chronological_blocks(pilot_ids)
    sr = AG.paired_endpoint(per_arm, "R", blocks["fixture_to_block"])
    sh = AG.paired_endpoint(per_arm, "H", blocks["fixture_to_block"])

    status_counts = {arm: dict(Counter(r["status"] for r in records if r["arm"] == arm))
                     for arm in ("S", "R", "H")}
    out = {
        "replay_version": "v8c_exposed50_structural_replay_v1",
        "label": "V8C_EXPOSED50_STRUCTURAL_REPLAY",
        "evidence_class": "DEVELOPMENT_APPARATUS_DIAGNOSTIC",
        "evidence_class_note": ("these 50 outcomes were opened in V8B.1; usable for support "
                                "distributions, control-distinctness, endpoint reachability, "
                                "aggregation debugging and real-corpus regression ONLY -- "
                                "never to claim fresh Sonnet advantage, never to choose a "
                                "threshold (V8C instruction 21)"),
        "apparatus": {
            "pit_context": __import__("src.research.hypothesis_v8c.pit_context",
                                      fromlist=["x"]).version_stamp(),
            "pre_t": PT.version_stamp(),
            "universe": UNI.version_stamp(),
            "controls": CTL.version_stamp(),
            "aggregate": AG.version_stamp(),
        },
        "n_fixtures": 50,
        "new_sonnet_calls": 0,
        "sealed_947_referenced": False,

        "universe_summary": {
            "admissible_per_fixture": sorted({f["n_admissible"] for f in per_fixture}),
            "pre_t_evaluable_min": min(f["n_pre_t_evaluable"] for f in per_fixture),
            "pre_t_evaluable_max": max(f["n_pre_t_evaluable"] for f in per_fixture),
            "pre_t_evaluable_mean": round(
                sum(f["n_pre_t_evaluable"] for f in per_fixture) / len(per_fixture), 2),
            "fixtures_with_zero_evaluable": sum(
                1 for f in per_fixture if f["n_pre_t_evaluable"] == 0),
            "pre_t_status_totals": dict(sorted(pre_t_status_totals.items())),
        },
        "sonnet_eligibility": {
            "n_sonnet_selections_total": s_eligible_total + s_ineligible_total,
            "n_pre_t_eligible": s_eligible_total,
            "n_pre_t_ineligible": s_ineligible_total,
            "pre_t_evaluable_rate": round(
                s_eligible_total / max(1, s_eligible_total + s_ineligible_total), 4),
            "ineligibility_reasons": dict(sorted(s_ineligible_reasons.items())),
            "note": ("eligibility is STRUCTURAL: it reads no target observation, no effect, "
                     "no score and no direction"),
        },
        "distinct_r_coverage": {
            "selections_requiring_r_match": r_matched + r_unmatched,
            "distinct_matches": r_matched,
            "unmatched": r_unmatched,
            "matched_tiers": dict(sorted(r_tiers.items())),
            "identity_matches_v8c": r_identity_v8c,
            "identity_matches_v8b1_same_inputs": r_identity_v8b1,
            "coverage_rate": round(r_matched / max(1, r_matched + r_unmatched), 4),
        },
        "h_coverage": {
            "fixtures_with_h_selection": sum(1 for f in per_fixture if f["h_n_selected"] > 0),
            "fixtures_h_unavailable": sum(
                1 for f in per_fixture if f["h_status"] == CTL.H_UNAVAILABLE_EMPTY_UNIVERSE),
        },
        "post_t_status_counts": status_counts,
        "consistency_invariant": {
            "rule": PT.version_stamp()["consistency_invariant"],
            "n_checked": len(records),
            "n_violations": len(invariant_violations),
            "violations": invariant_violations[:20],
            "holds": len(invariant_violations) == 0,
        },
        "paired_coverage": {
            "blocks": {k: v for k, v in blocks.items() if k != "fixture_to_block"},
            "S_vs_R": {k: v for k, v in sr.items() if k != "rows"},
            "S_vs_H": {k: v for k, v in sh.items() if k != "rows"},
            "inference_reachability_S_vs_R": AG.inference_reachability(sr["paired_n"]),
            "inference_reachability_S_vs_H": AG.inference_reachability(sh["paired_n"]),
        },
        "per_fixture": per_fixture,
        "per_fixture_arm_scores": per_arm,
        "champion_unchanged": H.champion_unchanged(),
        "champion_sha256": champ_before,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, default=str)

    print(f"\n[replay] pre-T evaluable universe: min={out['universe_summary']['pre_t_evaluable_min']} "
          f"mean={out['universe_summary']['pre_t_evaluable_mean']} "
          f"max={out['universe_summary']['pre_t_evaluable_max']}")
    print(f"[replay] Sonnet pre-T eligible: {s_eligible_total}/"
          f"{s_eligible_total + s_ineligible_total} "
          f"({out['sonnet_eligibility']['pre_t_evaluable_rate']})")
    print(f"[replay] R identity: V8C={r_identity_v8c}  V8B.1(same inputs)={r_identity_v8b1}")
    print(f"[replay] R matched={r_matched} unmatched={r_unmatched} tiers={dict(r_tiers)}")
    print(f"[replay] post-T: {status_counts}")
    print(f"[replay] consistency invariant holds={len(invariant_violations) == 0} "
          f"({len(invariant_violations)} violations)")
    print(f"[replay] paired S-v-R n={sr['paired_n']}  S-v-H n={sh['paired_n']}")
    print(f"[replay] wrote {OUT}")


if __name__ == "__main__":
    main()
