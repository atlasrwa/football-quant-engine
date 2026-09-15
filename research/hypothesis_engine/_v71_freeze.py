"""V7.1 freeze driver: build, hash and gate the whole apparatus. Sections 15, 16, 18, 20, 21.

Runs the entire pre-OOS path end to end:

  1. verify V7's frozen artifacts and CHAMPION are byte-unchanged;
  2. build every V7.1 specification and control universe;
  3. prove slot inhabitation and Endpoint-B balance BEFORE any outcome exists;
  4. build the fresh confirmatory manifest with a fixture-identifier-level zero-overlap proof;
  5. run the section-16 evaluability gate on fresh STRUCTURE + development SIMULATION;
  6. SHA-256 every artifact into one freeze manifest.

CONFIRMATORY_OOS_COMPUTED stays false. No effect is computed on any fresh fixture here: the
driver reads the fresh sample's structure (fixture, team, competition and fold counts) and
nothing else.

ZERO SPEND. No Bedrock. No CHAMPION write.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/src")

from src.research.hypothesis_v7 import covariates as V7COV
from src.research.hypothesis_v7 import matching as V7MATCH
from src.research.hypothesis_v71 import bugledger as BUG
from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import compiler as CO
from src.research.hypothesis_v71 import confounders as CF
from src.research.hypothesis_v71 import controls as CTRL
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import covariate_bridge as CB
from src.research.hypothesis_v71 import engine as EN
from src.research.hypothesis_v71 import estimator as ES
from src.research.hypothesis_v71 import evaluability as EVAL
from src.research.hypothesis_v71 import freshsample as FS
from src.research.hypothesis_v71 import golden as GOLD
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v71 import leakage as LEAK
from src.research.hypothesis_v71 import ontology as ONT
from src.research.hypothesis_v71 import recency as REC
from src.research.hypothesis_v71 import similarity as SIM

ROOT = "/home/ubuntu"
V7OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7_1"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha_obj(o):
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write(name, doc, manifest):
    path = f"{OUT}/{name}"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True, default=str)
    manifest[name] = sha_file(path)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    problems, manifest = [], {}

    # ---- 1. V7 immutability ------------------------------------------------------------
    v7_pre = json.load(open(f"{V7OUT}/V7_PREREGISTRATION.json"))
    v7_check = {}
    for name, expected in v7_pre["artifact_hashes"].items():
        got = sha_file(f"{V7OUT}/{name}")
        v7_check[name] = {"expected": expected, "actual": got, "match": got == expected}
        if got != expected:
            problems.append(f"V7 artifact {name} changed")
    champion_sha = sha_file(CHAMPION)
    if champion_sha != v7_pre["champion_protection"]["champion_sha256"]:
        problems.append("CHAMPION changed")
    v7_immutable = {"n_verified": len(v7_check),
                    "all_match": all(r["match"] for r in v7_check.values()),
                    "champion_sha256": champion_sha,
                    "champion_unchanged":
                        champion_sha == v7_pre["champion_protection"]["champion_sha256"],
                    "artifacts": v7_check}
    write("V7_1_V7_IMMUTABILITY_PROOF.json", v7_immutable, manifest)
    print(f"V7 immutability: {v7_immutable['all_match']}, CHAMPION unchanged: "
          f"{v7_immutable['champion_unchanged']}", flush=True)

    # ---- 2. specifications --------------------------------------------------------------
    cov_matrix = json.load(open(f"{V7OUT}/V7_COVERAGE_MATRIX.json"))
    cap = CAP.CapabilityContract(cov_matrix)
    cap.assert_block_is_not_provider()

    envelope = cap.spec()
    envelope["filter_dimensions_supported"] = {
        k: list(v["values"]) for k, v in ONT.FILTER_DIMENSIONS.items()}
    write("V7_1_ONTOLOGY.json", ONT.version_stamp(), manifest)
    write("V7_1_IR_SPEC.json", IRM.version_stamp(), manifest)
    write("V7_1_INVARIANTS.json", INV.version_stamp(), manifest)
    write("V7_1_CAPABILITY_MATRIX.json", envelope, manifest)
    write("V7_1_COMPILER_SPEC.json", CO.version_stamp(), manifest)
    write("V7_1_SIMILARITY_SPEC.json", SIM.version_stamp(), manifest)
    write("V7_1_RECENCY_SPEC.json", REC.version_stamp(), manifest)
    write("V7_1_CONFOUNDER_PLAN.json",
          {**CF.version_stamp(),
           "resolved": {f: CF.plan_for(f) for f in sorted(CF.PLAN)}}, manifest)
    write("V7_1_ESTIMATOR_CONTRACTS.json", ES.version_stamp(), manifest)
    write("V7_1_ENGINE_SPEC.json", EN.spec(), manifest)
    write("V7_1_GOLDEN_CORPUS.json",
          {**GOLD.version_stamp(), "cases": GOLD.GOLDEN_CASES}, manifest)
    write("V7_1_COVARIATE_SPEC.json",
          {**CB.version_stamp(), "v7_schema": V7COV.schema()}, manifest)
    write("V7_1_BUG_LEDGER.json", BUG.version_stamp(), manifest)
    if BUG.unresolved_blocking():
        problems.append(f"unresolved P0-P3 defects: {BUG.unresolved_blocking()}")

    # ---- 3. treated universe under the hardened semantics -------------------------------
    dedup = json.load(open(f"{V7OUT}/V7_DEDUPLICATION.json"))
    universe = json.load(open(f"{V7OUT}/V7_HYPOTHESIS_UNIVERSE.json"))
    origin_to_cid = {o["v7_hypothesis_id"]: f["canonical_hypothesis_id"]
                     for f in dedup["families"] for o in f["origins"]}
    spec_by_cid = {}
    for h in universe["hypotheses"]:
        cid = origin_to_cid.get(h["v7_hypothesis_id"])
        if cid and cid not in spec_by_cid:
            spec_by_cid[cid] = h["spec"]

    treated_rows, treated_specs = [], []
    for cid, spec in sorted(spec_by_cid.items()):
        ir = IRM.build_ir(spec)
        inv = INV.check(ir, capability=cap)
        status, adm, per_metric = cap.classify_metrics(ir.target_metrics)
        row = {"canonical_hypothesis_id": cid, "arm": "LLM", "ir_status": ir.status,
               "ir_id": ir.ir_id(), "invariant_ok": inv["ok"],
               "invariant_codes": inv["codes"], "capability_status": status,
               "admissible_competitions": sorted(adm),
               "evaluable": ir.status == IRM.OK and inv["ok"]
               and status in (CAP.SUPPORTED, CAP.RESTRICTED),
               "reconstructed_meaning": ir.describe()}
        treated_rows.append(row)
        treated_specs.append(spec)
    n_eval_llm = sum(1 for r in treated_rows if r["evaluable"])
    write("V7_1_TREATED_UNIVERSE.json",
          {"n_canonical_families": len(treated_rows), "n_evaluable": n_eval_llm,
           "ir_status": dict(collections.Counter(r["ir_status"] for r in treated_rows)),
           "invariant_codes": dict(collections.Counter(
               c for r in treated_rows for c in r["invariant_codes"])),
           "capability_status": dict(collections.Counter(
               r["capability_status"] for r in treated_rows)),
           "rows": treated_rows}, manifest)
    print(f"treated: {len(treated_rows)} canonical, {n_eval_llm} evaluable", flush=True)

    # ---- 4. control universes -----------------------------------------------------------
    vocab = sorted(m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block"))
    uniform_pool = CTRL.enumerate_pool(vocab, CTRL.UNIFORM_POOL_SIZE,
                                       sampling=CTRL.SAMPLING_UNIFORM)
    marginals = CTRL.derive_marginals(treated_specs)
    marginal_pool = CTRL.enumerate_pool(vocab, CTRL.MARGINAL_POOL_SIZE,
                                        sampling=CTRL.SAMPLING_MARGINAL,
                                        marginals=marginals)

    def classify_pool(pool):
        out = []
        for p in pool:
            ir = IRM.build_ir(p)
            inv = INV.check(ir, capability=cap)
            status, adm, _d = cap.classify_metrics(ir.target_metrics)
            out.append({"null_index": p["null_index"], "ir_status": ir.status,
                        "invariant_ok": inv["ok"], "invariant_codes": inv["codes"],
                        "capability_status": status,
                        "admissible_competitions": sorted(adm),
                        "evaluable": ir.status == IRM.OK and inv["ok"]
                        and status in (CAP.SUPPORTED, CAP.RESTRICTED)})
        return out

    uniform_rows = classify_pool(uniform_pool)
    marginal_rows = classify_pool(marginal_pool)
    write("V7_1_CONTROL_UNIFORM_POOL.json",
          {**CTRL.version_stamp(), "sampling": CTRL.SAMPLING_UNIFORM,
           "pool_hash": CTRL.pool_hash(uniform_pool), "n": len(uniform_pool),
           "n_evaluable": sum(1 for r in uniform_rows if r["evaluable"]),
           "pool": uniform_pool}, manifest)
    write("V7_1_CONTROL_MARGINAL_POOL.json",
          {**CTRL.version_stamp(), "sampling": CTRL.SAMPLING_MARGINAL,
           "marginals": {k: [list(x) for x in v] for k, v in marginals.items()},
           "pool_hash": CTRL.pool_hash(marginal_pool), "n": len(marginal_pool),
           "n_evaluable": sum(1 for r in marginal_rows if r["evaluable"]),
           "pool": marginal_pool}, manifest)

    slots = CTRL.slot_inhabitation(treated_specs, uniform_pool + marginal_pool[:2000], cap)
    write("V7_1_SLOT_INHABITATION.json", slots, manifest)
    if not slots["no_structural_zero_from_generator_incapability"]:
        problems.append(f"control generator cannot inhabit: {slots['uninhabited']}")
    print(f"slot inhabitation ok: "
          f"{slots['no_structural_zero_from_generator_incapability']}", flush=True)

    # ---- 5. Endpoint-B matching ---------------------------------------------------------
    def cov_row(spec, ir, status, adm, cid):
        meas = {"status": ("MEASURABLE" if status in (CAP.SUPPORTED, CAP.RESTRICTED)
                           else "UNMEASURABLE_COVERAGE"),
                "admissible_competitions": sorted(adm),
                "providers": [CAP.CORPUS_PROVIDER],
                "per_metric": [{"field": CAP.METRIC_SEMANTICS.get(m, {}).get("field"),
                                "resolution": CAP.METRIC_SEMANTICS.get(m, {}).get("resolution")}
                               for m in ir.target_metrics]}
        cspec = {"TARGET": list(ir.target_metrics), "SUBJECT": ir.subject,
                 "SIDE": ir.perspective, "COMPARATOR": ir.comparator,
                 "CONDITIONS": [json.dumps({"dimension": f.dimension, "axis": f.axis,
                                            "value": f.value}, sort_keys=True)
                                for f in (ir.cohort.filters if ir.cohort else ())],
                 "TIME_SCOPE": ir.cohort.window if ir.cohort else "ALL_PRIOR",
                 "SIMILARITY_DIMENSIONS": (["opponent_profile"]
                                           if ir.cohort and ir.cohort.similar_to_opponent
                                           else []),
                 "FAMILY": ir.research_family}
        c = V7COV.build(cspec, meas, CF.plan_for(ir.research_family))
        c["canonical_hypothesis_id"] = cid
        c["n_admissible_competitions"] = len(adm)
        return c

    llm_cov, null_cov = [], []
    for spec, row in zip(treated_specs, treated_rows):
        if not row["evaluable"]:
            continue
        ir = IRM.build_ir(spec)
        status, adm, _d = cap.classify_metrics(ir.target_metrics)
        llm_cov.append(cov_row(spec, ir, status, adm, row["canonical_hypothesis_id"]))
    for p, r in zip(marginal_pool, marginal_rows):
        if not r["evaluable"]:
            continue
        ir = IRM.build_ir(p)
        status, adm, _d = cap.classify_metrics(ir.target_metrics)
        null_cov.append(cov_row(p, ir, status, adm, f"null_{p['null_index']}"))

    matched = V7MATCH.match(llm_cov, null_cov)
    ess = V7MATCH.effective_sample(matched["control_weights"], len(null_cov))
    bal = V7MATCH.balance(llm_cov, null_cov, matched["control_weights"],
                          CB.MATCHING_COVARIATES)
    verdict = V7MATCH.comparability_verdict(matched, ess, bal)
    write("V7_1_MATCHING.json",
          {"spec": V7MATCH.version_stamp(), "covariates": list(CB.MATCHING_COVARIATES),
           "n_llm": len(llm_cov), "n_null_eligible": len(null_cov),
           "match": {k: v for k, v in matched.items() if k != "control_weights"},
           "effective_sample": ess, "balance": bal, "verdict": verdict}, manifest)
    write("V7_1_MATCHING_WEIGHTS.json", matched["control_weights"], manifest)
    print(f"matching: {matched.get('n_matched')}/{len(llm_cov)} matched, "
          f"ESS {ess.get('effective_n')}, verdict {verdict.get('verdict')}", flush=True)

    # ---- 6. leakage red team ------------------------------------------------------------
    guard = LEAK.run_guard_suite(1_700_000_000, "mt_target")
    write("V7_1_LEAKAGE_SUITE.json", guard, manifest)
    if not guard["all_pass"]:
        problems.append("leakage guard suite failed")

    # ---- 7. fresh confirmatory manifest (STRUCTURE ONLY) --------------------------------
    records = CI.load_records(include_fresh=True)
    development, confirmatory = FS.partition(records)
    overlap = FS.zero_overlap_proof(confirmatory, development)
    folds = FS.build_folds(confirmatory)
    struct = FS.structure(confirmatory, folds)
    if not (overlap["disjoint_from_development"]
            and overlap["disjoint_from_v7_confirmatory"]):
        problems.append("fresh sample overlaps development or V7 confirmatory")

    # evaluable families are a STRUCTURAL count: capability x invariants, no effect.
    struct["n_evaluable_families"] = n_eval_llm
    struct["expected_scored_pairs"] = matched.get("n_matched", 0)
    struct["expected_clusters"] = len({
        c.get("research_family_label") for c in llm_cov})
    struct["expected_effective_sample"] = ess.get("effective_n", 0.0)

    replay_path = f"{OUT}/V7_1_DIAGNOSTIC_REPLAY.json"
    simulation = {"cluster_sigma": None}
    if os.path.exists(replay_path):
        sim = json.load(open(replay_path))["summary"]["precision_simulation"]
        simulation = {"cluster_sigma": sim.get("cluster_sigma"),
                      "n_clusters_simulated": sim.get("n_clusters"),
                      "source": "development-window diagnostic replay (no fresh fixture)"}
    gate = EVAL.assess(struct, simulation)
    write("V7_1_EVALUABILITY_GATE.json", gate, manifest)
    write("V7_1_FRESH_OOS_MANIFEST.json",
          FS.manifest(confirmatory, development, folds, struct, overlap, gate=gate),
          manifest)
    print(f"fresh: {struct['n_fixtures']} fixtures, {struct['n_competitions']} competitions, "
          f"{struct['n_folds']} folds; gate {gate['verdict']}", flush=True)

    # ---- 8. freeze manifest -------------------------------------------------------------
    doc = {"freeze_version": "v71_freeze_v1",
           "experiment": "V7_1_HARDENED_HYPOTHESIS_VALIDATION",
           "confirmatory_oos_computed": False,
           "confirmatory_oos_viewed": False,
           "candidate_feature_promotion": False,
           "bedrock_change_required": False,
           "defects_by_severity": BUG.by_severity(),
           "unresolved_p0_p3_defects": BUG.unresolved_blocking(),
           "champion_sha256": champion_sha,
           "module_versions": {
               "ontology": ONT.ONTOLOGY_VERSION, "ir": IRM.IR_VERSION,
               "invariants": INV.INVARIANTS_VERSION, "capability": CAP.CAPABILITY_VERSION,
               "compiler": CO.COMPILER_VERSION, "similarity": SIM.SIMILARITY_VERSION,
               "recency": REC.RECENCY_VERSION, "confounders": CF.CONFOUNDERS_VERSION,
               "estimator": ES.ESTIMATOR_VERSION, "controls": CTRL.CONTROLS_VERSION,
               "evaluability": EVAL.EVALUABILITY_VERSION, "fresh": FS.FRESH_VERSION,
               "leakage": LEAK.LEAKAGE_VERSION, "engine": EN.ENGINE_VERSION},
           "engine_spec_hash": EN.spec_hash(),
           "evaluability_verdict": gate["verdict"],
           "artifact_hashes": manifest,
           "problems": problems}
    path = f"{OUT}/V7_1_FREEZE_MANIFEST.json"
    json.dump(doc, open(path, "w"), indent=1, sort_keys=True)
    print("\n=== FREEZE ===")
    print(json.dumps({k: v for k, v in doc.items() if k != "artifact_hashes"}, indent=1))
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  -", p)


if __name__ == "__main__":
    main()
