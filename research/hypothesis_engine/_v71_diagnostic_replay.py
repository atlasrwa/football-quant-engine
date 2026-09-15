"""V7.1 SECTION 17: diagnostic replay of the already-viewed V7 sample through repaired code.

CLASSIFICATION, on every output: DIAGNOSTIC_ONLY / NON_CONFIRMATORY / OUTCOME_ALREADY_VIEWED.

The goal is NOT to discover better effects. It is to establish, on structure:
  * that the families V7 terminated TAUTOLOGICAL are now refused for a NAMED structural reason
    before any measurement;
  * how much of the intended question survives the repair (semantic recovery);
  * that features are non-degenerate where a contrast genuinely exists;
  * whether any remaining structural failure is a generic apparatus bug.

It also estimates ONE precision quantity the section-16 gate needs: the DISPERSION of the
per-cluster endpoint statistic. Dispersion is not an effect -- it carries no direction and no
significance -- and section 16 explicitly permits development-window simulation for sizing.
No threshold or semantic in this repository is changed in response to any effect seen here.

ZERO SPEND. No Bedrock. No CHAMPION. Writes nothing to production.
"""
from __future__ import annotations

import collections
import json
import os
import sys
import time

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import compiler as CO      # noqa: F401  (contract import)
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import recency as REC
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v7 import analysis_spec as V7A

ROOT = "/home/ubuntu"
V7OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"

CLASSIFICATION = ["DIAGNOSTIC_ONLY", "NON_CONFIRMATORY", "OUTCOME_ALREADY_VIEWED"]

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")


def build_terciles(index, cutoff_unix, axes):
    ter, cache = {}, {}
    for axis in axes:
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in index.metrics:
            continue
        by_comp = {}
        for tid, s in index.series.items():
            pre = [e for e in s if e[1] < cutoff_unix]
            if len(pre) < 6:
                continue
            vals = [index.team_value(i, tid, metric, side) for (i, _k, _c, _h, _o) in pre]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            mv = sum(vals) / len(vals)
            cache[(tid, axis)] = mv
            by_comp.setdefault(pre[-1][2], []).append(mv)
        for comp, xs in by_comp.items():
            xs.sort()
            if len(xs) >= 3:
                ter[(comp, axis)] = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
    return ter, cache


def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    cov = json.load(open(f"{V7OUT}/V7_COVERAGE_MATRIX.json"))
    cap = CAP.CapabilityContract(cov)
    cap.assert_block_is_not_provider()

    dedup = json.load(open(f"{V7OUT}/V7_DEDUPLICATION.json"))
    universe = json.load(open(f"{V7OUT}/V7_HYPOTHESIS_UNIVERSE.json"))
    spec_by_cid = {}
    for h in universe["hypotheses"]:
        cid = None
        for fam in dedup["families"]:
            if any(o["v7_hypothesis_id"] == h["v7_hypothesis_id"] for o in fam["origins"]):
                cid = fam["canonical_hypothesis_id"]
                break
        if cid and cid not in spec_by_cid:
            spec_by_cid[cid] = h["spec"]
    print(f"canonical families: {len(spec_by_cid)}", flush=True)

    # ---- stage 1: structural classification (no measurement) -------------------------
    rows, measurable = [], []
    for cid, spec in sorted(spec_by_cid.items()):
        ir = IRM.build_ir(spec)
        inv = INV.check(ir, capability=cap)
        status, adm, _d = cap.classify_metrics(ir.target_metrics)
        row = {"canonical_hypothesis_id": cid, "ir_status": ir.status,
               "ir_id": ir.ir_id(), "invariant_codes": inv["codes"],
               "capability_status": status, "admissible_competitions": sorted(adm),
               "reconstructed_meaning": ir.describe(),
               "research_family": ir.research_family}
        if ir.status != IRM.OK:
            row["terminal_state"] = EN.SEMANTICALLY_AMBIGUOUS
        elif not inv["ok"]:
            row["terminal_state"] = EN.STRUCTURALLY_INVALID
            row["structural_reason"] = inv["codes"]
        elif status in ("UNKNOWN", "UNSUPPORTED", "INSUFFICIENT_COVERAGE"):
            row["terminal_state"] = EN.UNMEASURABLE
        else:
            measurable.append((cid, spec, ir, adm))
            row["terminal_state"] = None
        rows.append(row)
    print(f"structurally valid AND measurable: {len(measurable)}", flush=True)

    # ---- stage 2: measurement on the DEVELOPMENT (already-viewed) window ------------
    records = CI.load_records(include_fresh=False)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(records, metrics, CAP.METRIC_SEMANTICS)
    v7folds = json.load(open(f"{V7OUT}/V7_WALKFORWARD_FOLDS.json"))["folds"]
    ter, cache = build_terciles(index, v7folds[0]["train_end_unix"], PROFILE_AXES)
    ctx = EN.Context(index, ter, cache, SIM.SimilarityEngine(index))
    folds = []
    for f in v7folds:
        folds.append({"fold_index": f["fold_index"],
                      "positions": list(index.range_positions(f["validate_start_unix"],
                                                              f["validate_end_unix"]))})
    print(f"index {len(index.recs)} records; {len(folds)} development folds", flush=True)

    by_cid = {r["canonical_hypothesis_id"]: r for r in rows}
    scores, done = [], 0
    for cid, spec, ir, adm in measurable:
        # the weighting family is chosen by the engine from the frozen recency contract;
        # a reweighting cohort is evaluated at EVERY half-life and averaged, never at one.
        ev = EN.evaluate_family(ir, folds, index, ctx, cap, restrict_to=adm)
        sc = EN.score_family(ev)
        row = by_cid[cid]
        allc = [c for b in ev["per_metric"].values()
                for c in b["cells"] + b.get("competition_cells", [])]
        row["n_folds_evaluated"] = sum(len(b["cells"]) for b in ev["per_metric"].values())
        row["n_folds_with_effect"] = sum(
            1 for b in ev["per_metric"].values() for c in b["cells"]
            if c["effect"] is not None)
        row["contrastless_cells"] = sum(1 for c in allc if c.get("contrastless"))
        row["confounded_cells"] = sum(1 for c in allc if c.get("confounded_unresolved"))
        if sc is None:
            row["terminal_state"] = EN.INSUFFICIENT_SUPPORT
        else:
            row["terminal_state"] = EN.terminal_state(
                ir_ok=True, invariant_ok=True, capability_status=row["capability_status"],
                evidence=ev, score=sc, fdr_rejected=False)
            row["diagnostic_score"] = sc["oos_quality_score"]
            row["diagnostic_direction_agreement"] = sc["direction_agreement"]
            row["diagnostic_competition_agreement"] = sc["competition_direction_agreement"]
            row["multiplicity_family"] = V7A.multiplicity_family_of(ir.research_family)
            scores.append((row["multiplicity_family"], sc["oos_quality_score"]))
        done += 1
        if done % 5 == 0:
            print(f"  {done}/{len(measurable)}  ({time.time()-t0:.0f}s)", flush=True)

    # ---- stage 3: the precision quantity section 16 needs ---------------------------
    by_cluster = collections.defaultdict(list)
    for fam, s in scores:
        by_cluster[fam].append(s)
    cluster_means = [sum(v) / len(v) for v in by_cluster.values() if v]
    sigma = None
    if len(cluster_means) >= 2:
        m = sum(cluster_means) / len(cluster_means)
        sigma = (sum((x - m) ** 2 for x in cluster_means) / (len(cluster_means) - 1)) ** 0.5

    summary = {
        "classification": CLASSIFICATION,
        "n_canonical_families": len(spec_by_cid),
        "terminal_states": dict(collections.Counter(r["terminal_state"] for r in rows)),
        "structural_reasons": dict(collections.Counter(
            c for r in rows for c in r.get("structural_reason", []) or [])),
        "capability_status": dict(collections.Counter(r["capability_status"] for r in rows)),
        "n_structurally_valid_and_measurable": len(measurable),
        "n_scored": len(scores),
        "semantic_recovery": {
            "v7_tautological_now_named_structurally_invalid": sum(
                1 for r in rows if r["terminal_state"] == EN.STRUCTURALLY_INVALID),
            "v7_unmeasurable_now_measurable_on_restricted_universe": sum(
                1 for r in rows if r["capability_status"] == CAP.RESTRICTED),
        },
        "contrastless_cells_after_repair": sum(r.get("contrastless_cells", 0) or 0
                                               for r in rows),
        "confounded_cells_after_repair": sum(r.get("confounded_cells", 0) or 0
                                             for r in rows),
        "precision_simulation": {
            "quantity": "cluster_sigma",
            "definition": ("standard deviation, across multiplicity-family clusters, of the "
                           "cluster-mean OOS quality score on the DEVELOPMENT window"),
            "is_an_effect": False,
            "n_clusters": len(cluster_means),
            "cluster_sigma": sigma,
        },
        "seconds": round(time.time() - t0, 1),
    }
    doc = {"replay_version": "v71_diagnostic_replay_v1",
           "classification": CLASSIFICATION,
           "engine_spec_hash": EN.spec_hash(),
           "summary": summary, "rows": rows}
    path = f"{OUT}/V7_1_DIAGNOSTIC_REPLAY.json"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)
    print(json.dumps(summary, indent=1))
    print(f"\nwritten: {path}")


if __name__ == "__main__":
    main()
