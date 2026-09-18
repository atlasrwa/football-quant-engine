"""V8C SCORE-STABILITY audit -- OUTCOME-BLIND.

Inspects the PRE-T distributions of the three quantities that can make a standardized score
pathological, and asks one question: can the frozen ZERO_VARIANCE_FLOOR admit a cohort whose
scale is so small that `raw_improvement / scale_var` explodes?

    scale_var             weighted variance of the COHORT's own prior observations
    effective_n           Kish ESS of the cohort weights
    weight_concentration  max single-observation weight share

Every one is a property of strictly-prior data, so this audit reads NO target outcome and is
legitimate before any spend.

The scorer's thresholds are NOT changed here. Per the mission, a threshold may move only if an
OUTCOME-BLIND failure is demonstrated -- and then only as a versioned successor, preregistered
before fresh outcomes. This script's job is to say whether such a failure exists.
"""
from __future__ import annotations

import json
import statistics
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)
OUT = f"{ROOT}/research/hypothesis_engine/V8C_SCORE_STABILITY_AUDIT.json"


def main():
    from src.research.hypothesis_v7 import pit as V7PIT
    from src.research.hypothesis_v71 import engine as ENGmod
    from src.research.hypothesis_v8c import cohort_stats as CS
    from src.research.hypothesis_v8c import compiler as CO
    from src.research.hypothesis_v8c import golden as G
    from src.research.hypothesis_v8c import grammar as GR
    from src.research.hypothesis_v8c import harness as H
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import pre_t as PT
    from src.research.hypothesis_v8c import universe as UNI

    champ = H.assert_champion_unchanged()
    cap, index, _ = H.build(check_champion=False)

    # Development corpus only: the 50 already-exposed pilot fixtures. The 947 are untouched.
    fz = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_PILOT50_SELECTION_FREEZE.json"))
    pilot = fz["pilot_fixture_ids_ordered"][:12]        # a bounded structural sample

    scale_vars, eff_ns, concs, ratios = [], [], [], []
    n_eval = 0
    for fid in pilot:
        pos = index.pos_of_fixture[fid]
        ctx = PC.build_pit_context(index, pos)
        fu = UNI.build_fixture_universe(index, pos, ctx=ctx, capability=cap, fixture_id=fid)
        n_eval += fu.n_evaluable
        for cand in fu.evaluable:
            ir = GR.resolve(cand["hypothesis_id"], cap)
            if ir is None:
                continue
            try:
                q = CO.compile_query(ir, index, pos, metric=ir.target_metrics[0],
                                     terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                     similarity=ctx.similarity,
                                     recency=ENGmod.recency_family_for(ir)[0],
                                     capability=cap, collect_fixtures=True)
            except Exception:
                continue
            sv = CS.weighted_variance(q.cohort_values, q.cohort_weights)
            if sv is None:
                continue
            scale_vars.append(sv)
            eff_ns.append(V7PIT.kish_effective_n(q.cohort_weights))
            concs.append(V7PIT.weight_concentration(q.cohort_weights))
            # The pathology proxy: how large would a ONE-UNIT raw improvement become?
            ratios.append(1.0 / sv if sv > 0 else float("inf"))

    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None

    floor = CS.ZERO_VARIANCE_FLOOR
    near_floor = [s for s in scale_vars if s <= floor * 1e6]
    tiny = [s for s in scale_vars if s < 1e-6]

    report = {
        "audit_version": "v8c_score_stability_audit_v1",
        "evidence_class": "DEVELOPMENT_APPARATUS_DIAGNOSTIC",
        "outcome_blind": True,
        "reads_target_outcome": False,
        "n_fixtures_sampled": len(pilot),
        "n_pre_t_evaluable_candidates": n_eval,
        "n_cohorts_measured": len(scale_vars),
        "zero_variance_floor": floor,
        "scale_var": {"min": min(scale_vars) if scale_vars else None,
                      "p01": q(scale_vars, 0.01), "p10": q(scale_vars, 0.10),
                      "p50": q(scale_vars, 0.50), "p90": q(scale_vars, 0.90),
                      "max": max(scale_vars) if scale_vars else None,
                      "median": statistics.median(scale_vars) if scale_vars else None},
        "effective_n": {"min": min(eff_ns) if eff_ns else None, "p10": q(eff_ns, 0.10),
                        "p50": q(eff_ns, 0.50), "max": max(eff_ns) if eff_ns else None},
        "weight_concentration": {"min": min(concs) if concs else None,
                                 "p50": q(concs, 0.50),
                                 "max": max(concs) if concs else None},
        "one_unit_improvement_standardized": {
            "p50": q(ratios, 0.50), "p90": q(ratios, 0.90), "p99": q(ratios, 0.99),
            "max": max(ratios) if ratios else None},
        "pathology_check": {
            "n_within_1e6x_of_floor": len(near_floor),
            "n_scale_var_below_1e_6": len(tiny),
            "floor_admits_a_pathological_cohort": len(tiny) > 0,
            "note": ("a cohort clearing MIN_RAW_N=20, MIN_UNIQUE_OPPONENTS=6 and "
                     "MIN_EFFECTIVE_N=10 on real football counts cannot have a near-zero "
                     "weighted variance unless every contributing match had an identical "
                     "value; the support gate is what bounds the ratio, not the floor alone"),
        },
        "verdict": None,
        "thresholds_changed": False,
        "champion_sha256": champ,
        "new_sonnet_calls": 0,
        "sealed_947_referenced": False,
    }
    report["verdict"] = ("NO_OUTCOME_BLIND_FAILURE_DEMONSTRATED" if not tiny
                         else "PATHOLOGY_CANDIDATE_FOUND_REVIEW_REQUIRED")
    with open(OUT, "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(f"[stability] cohorts measured = {len(scale_vars)}")
    print(f"[stability] scale_var p01={report['scale_var']['p01']} "
          f"p50={report['scale_var']['p50']} min={report['scale_var']['min']}")
    print(f"[stability] 1-unit improvement standardized: p99="
          f"{report['one_unit_improvement_standardized']['p99']} "
          f"max={report['one_unit_improvement_standardized']['max']}")
    print(f"[stability] scale_var below 1e-6: {len(tiny)}")
    print(f"[stability] VERDICT = {report['verdict']}  thresholds_changed=False")
    print(f"[stability] wrote {OUT}")


if __name__ == "__main__":
    main()
