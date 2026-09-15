"""Freeze the V7_DETERMINISTIC_HYPOTHESIS_VALIDATION pre-OOS apparatus. ZERO SPEND.

Emits every immutable V7 artifact with deterministic SHA-256 hashes, verifies CHAMPION
isolation, and STOPS at V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED. It computes NO confirmatory
OOS effect. It reads ONLY the immutable V6.1 execution outputs and the local historical
corpus. It never writes to production, never touches p_model, never calls Bedrock.

Artifacts (out/v7/):
  V7_HYPOTHESIS_UNIVERSE.json     V7_CANONICAL_HYPOTHESES.json   V7_DEDUPLICATION.json
  V7_MEASURABILITY.json           V7_PROVIDER_CONTRACT.json      V7_SIMILARITY_SPEC.json
  V7_SUPPORT_RULES.json           V7_CONFOUNDER_PLAN.json        V7_MULTIPLICITY_PLAN.json
  V7_WALKFORWARD_FOLDS.json       V7_CONTROL_COMPARISON.json     V7_CANDIDATE_LOCK.json
  V7_LEAKAGE_AUDIT.json           V7_EVALUATOR_FREEZE.json       V7_PREREGISTRATION.json
  V7_STATES.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_v7 import analysis_spec as A
from src.research.hypothesis_v7 import canonical as C
from src.research.hypothesis_v7 import coverage as COV
from src.research.hypothesis_v7 import covariates as CV
from src.research.hypothesis_v7 import endpoints as EP
from src.research.hypothesis_v7 import matching as MT
from src.research.hypothesis_v7 import leakage as L
from src.research.hypothesis_v7 import null_benchmark as NB
from src.research.hypothesis_v7 import outcomes as O
from src.research.hypothesis_v7 import pit as PIT
from src.research.hypothesis_v7 import provider as P
from src.research.hypothesis_v7 import similarity as S
from src.research.hypothesis_v7 import universe as U
from src.research.hypothesis_v7 import walkforward as W

ROOT = "/home/ubuntu"
V61_EXEC = f"{ROOT}/research/hypothesis_oos/out/v6_1/execution"
OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = \
    "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

# V6.1 immutable references frozen into V7 (Phase 0). Verified before use.
V61_REFS = {
    "v6_1_scores": f"{V61_EXEC}/scores.json",
    "v6_1_verdict": f"{V61_EXEC}/V6_1_VERDICT.json",
    "v6_1_execution_summary": f"{V61_EXEC}/execution_summary.json",
    "v6_1_evaluator_freeze": f"{ROOT}/research/hypothesis_oos/out/v6_1/EVALUATOR_FREEZE.json",
}

# V7 apparatus modules whose behavior defines the experiment (frozen via hash).
V7_MODULES = [
    "src/research/hypothesis_v7/__init__.py",
    "src/research/hypothesis_v7/universe.py",
    "src/research/hypothesis_v7/canonical.py",
    "src/research/hypothesis_v7/provider.py",
    "src/research/hypothesis_v7/coverage.py",
    "src/research/hypothesis_v7/pit.py",
    "src/research/hypothesis_v7/similarity.py",
    "src/research/hypothesis_v7/analysis_spec.py",
    "src/research/hypothesis_v7/walkforward.py",
    "src/research/hypothesis_v7/outcomes.py",
    "src/research/hypothesis_v7/leakage.py",
    "src/research/hypothesis_v7/null_benchmark.py",
    "src/research/hypothesis_v7/matching.py",
    "src/research/hypothesis_v7/endpoints.py",
    "src/research/hypothesis_v7/covariates.py",
]

REQUIRED_STATES = [
    "V7_V6_1_HISTORY_FROZEN", "V7_HYPOTHESIS_UNIVERSE_FROZEN",
    "V7_CANONICALIZATION_VALIDATED", "V7_DEDUPLICATION_VALIDATED",
    "V7_MEASURABILITY_RULES_FROZEN", "V7_PROVIDER_SEMANTICS_VALIDATED",
    "V7_PIT_ENGINE_VALIDATED", "V7_SIMILARITY_ENGINE_VALIDATED",
    "V7_SUPPORT_RULES_FROZEN", "V7_CONFOUNDER_PLAN_FROZEN",
    "V7_MULTIPLICITY_PLAN_FROZEN", "V7_WALKFORWARD_DESIGN_FROZEN",
    "V7_CONTROL_A_INFEASIBLE",
    "V7_CONTROL_B_STRUCTURAL_COVARIATES_FROZEN",
    "V7_CONTROL_B_MATCHING_FROZEN",
    "V7_CONTROL_B_BALANCE_VALIDATED",
    "V7_CONTROL_B_EFFECTIVE_SAMPLE_VALIDATED",
    "V7_END_TO_END_ENDPOINT_FROZEN",
    "V7_CONDITIONAL_SIGNAL_ENDPOINT_FROZEN",
    "V7_EVALUATOR_FROZEN",
    "V7_CHAMPION_ISOLATED", "V7_FULLY_PREREGISTERED",
    "V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED",
]


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _write(name, obj):
    os.makedirs(OUT, exist_ok=True)
    p = f"{OUT}/{name}"
    with open(p, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)
    return _sha_file(p)


def main() -> int:
    problems = []

    # Phase 0: V6.1 history frozen references
    for k, p in V61_REFS.items():
        if not os.path.exists(p):
            problems.append(f"V6.1 reference missing: {k} ({p})")
    v61_refs = {k: (_sha_file(p) if os.path.exists(p) else None)
                for k, p in V61_REFS.items()}
    champ_sha = _sha_file(CHAMPION)
    if champ_sha != CHAMPION_FROZEN_SHA:
        problems.append("CHAMPION changed")

    # Phase 1: universe (outcome-blind)
    universe = U.extract_universe(V61_EXEC)
    # Phase 2-3: canonicalize + dedup
    canon = C.canonicalize_universe(universe)
    dedup = C.deduplicate(canon)
    # Phase 25: measure the REAL corpus coverage matrix BEFORE the measurability gate, so
    # every admissibility decision is evidenced by measurement rather than asserted.
    idx = CA.load_index()
    coverage = COV.measure(idx.records, P.corpus_bindings())
    cross_provider = P.cross_provider_invariant(coverage)
    sim_cov = S.validate_dimension_coverage(coverage)
    shrink_ok = S.shrinkage_integrity(S.version_stamp())
    if not shrink_ok["integrity_ok"]:
        problems.append("PROFILE_SHRINKAGE_K integrity failure: "
                        + "; ".join(shrink_ok["problems"]))
    if not sim_cov["all_dimensions_clear_coverage_gate"]:
        problems.append("similarity dimension fails the coverage gate: "
                        + "; ".join(sim_cov["failures"]))
    if cross_provider["n_distinct_providers"] != 1:
        problems.append("corpus is not single-provider; pooling guard must be re-derived")

    # Phase 4/6: measurability over canonical families (schema + measured coverage only)
    from collections import Counter
    meas_rows, meas_counts = [], Counter()
    for fam in dedup["families"]:
        m = P.classify_measurability(fam["canonical_spec"], coverage)
        meas_counts[m["status"]] += 1
        meas_rows.append({"canonical_hypothesis_id": fam["canonical_hypothesis_id"],
                          "family": fam["canonical_spec"]["FAMILY"],
                          "status": m["status"], "providers": m["providers"],
                          "admissible_competitions": m["admissible_competitions"],
                          "reasons": m["reasons"]})
    measurable_ids = [r["canonical_hypothesis_id"] for r in meas_rows
                      if r["status"] == P.MEASURABLE]

    # comparator flags (Phase 8) over measurable families
    comparator_flags = []
    for fam in dedup["families"]:
        if fam["canonical_hypothesis_id"] not in measurable_ids:
            continue
        fl = A.flag_comparator(fam["canonical_spec"])
        comparator_flags.append({"canonical_hypothesis_id": fam["canonical_hypothesis_id"],
                                 "ok": fl["ok"], "flags": fl["flags"]})
    n_comparator_rejected = sum(1 for f in comparator_flags if not f["ok"])

    # walk-forward folds + arm matched cells (restricted to the measurable class, which is
    # what the frozen primary endpoint specifies)
    ks = [int(r.kickoff_unix) for r in idx.records]
    folds = W.build_folds(min(ks), max(ks))
    matched = W.matched_cells(dedup["families"], measurable_ids)
    matched_all = W.matched_cells(dedup["families"])
    arm_feasibility = W.endpoint_feasibility(matched)

    # ---- Phase 20 Control B: deterministic null benchmark ----------------------------
    # Control A (arm-matched) is infeasible, so the PRIMARY control is the mechanically
    # enumerated null, run through the identical pipeline.
    null = NB.build(list(P.corpus_bindings().keys()), C,
                    pool_size=NB.NULL_POOL_SIZE, sampling=NB.SAMPLING_UNIFORM)
    null_meas_rows, null_meas_counts = [], Counter()
    for fam in null["families"]:
        m = P.classify_measurability(fam["canonical_spec"], coverage)
        null_meas_counts[m["status"]] += 1
        null_meas_rows.append({"canonical_hypothesis_id": fam["canonical_hypothesis_id"],
                               "family": fam["canonical_spec"]["FAMILY"],
                               "status": m["status"],
                               "admissible_competitions": m["admissible_competitions"],
                               "reasons": m["reasons"]})
    null_measurable_ids = [r["canonical_hypothesis_id"] for r in null_meas_rows
                           if r["status"] == P.MEASURABLE]
    null_comp_flags = [A.flag_comparator(f["canonical_spec"]) for f in null["families"]
                       if f["canonical_hypothesis_id"] in set(null_measurable_ids)]
    n_null_comp_rejected = sum(1 for f in null_comp_flags if not f["ok"])

    v61_meas_rate = len(measurable_ids) / max(len(dedup["families"]), 1)
    null_meas_rate = len(null_measurable_ids) / max(len(null["families"]), 1)
    v61_comp_reject_rate = n_comparator_rejected / max(len(comparator_flags), 1)
    null_comp_reject_rate = n_null_comp_rejected / max(len(null_comp_flags), 1)

    null_feasibility = W.null_endpoint_feasibility(
        n_null_measurable=len(null_measurable_ids),
        v61_measurability_rate=v61_meas_rate,
        null_measurability_rate=null_meas_rate,
        v61_comparator_reject_rate=v61_comp_reject_rate,
        null_comparator_reject_rate=null_comp_reject_rate)

    # count-balanced null subset: capped at the V6.1 measurable-family count so neither
    # origin is rewarded for volume. Outcome-blind.
    balanced_null = NB.balanced_measurable_subset(
        null["families"], null_measurable_ids, cap=len(measurable_ids))

    # ---- Tasks 3-7: outcome-blind covariates, matching, balance, ESS ------------------
    COVFIELDS = list(CV.MATCHING_COVARIATES)

    def _cov_rows(families, meas_lookup):
        rows = []
        for fam in families:
            cid = fam["canonical_hypothesis_id"]
            cs = fam["canonical_spec"]
            meas = meas_lookup[cid]
            plan = A.confounder_plan_for(cs.get("FAMILY"))
            rows.append({"canonical_hypothesis_id": cid,
                         "arm_membership": fam.get("arm_membership"),
                         "covariates": CV.build(cs, meas, plan)})
        return rows

    llm_meas = {fam["canonical_hypothesis_id"]:
                P.classify_measurability(fam["canonical_spec"], coverage)
                for fam in dedup["families"]}
    null_meas = {fam["canonical_hypothesis_id"]:
                 P.classify_measurability(fam["canonical_spec"], coverage)
                 for fam in null["families"]}
    llm_cov = _cov_rows(dedup["families"], llm_meas)
    null_cov = _cov_rows(null["families"], null_meas)

    # ---- endpoint B: the MARGINAL-matched control pool -------------------------------
    # Structural marginals read from canonical structure only -- no outcome consulted.
    marginals = NB.derive_marginals(dedup["families"])
    nullm = NB.build(list(P.corpus_bindings().keys()), C,
                     pool_size=NB.NULL_MATCHED_POOL_SIZE,
                     sampling=NB.SAMPLING_MARGINAL, marginals=marginals)
    nullm_meas = {fam["canonical_hypothesis_id"]:
                  P.classify_measurability(fam["canonical_spec"], coverage)
                  for fam in nullm["families"]}
    nullm_cov = _cov_rows(nullm["families"], nullm_meas)

    # Endpoint B conditions on MEASURABLE (+ADEQUATE_SUPPORT at OOS time) on BOTH sides.
    llm_elig = [r for r in llm_cov if r["covariates"]["is_measurable"]]
    null_elig = [r for r in nullm_cov if r["covariates"]["is_measurable"]]

    match_result = MT.match(llm_elig, null_elig)
    ess = MT.effective_sample(match_result["control_weights"], len(null_elig))
    # balance is assessed on the MATCHED LLM families against their weighted controls -- the
    # matched region of common support is the estimand, and the matched/unmatched composition
    # is reported separately so the restriction is visible rather than silent.
    _matched_ids = {a["canonical_hypothesis_id"] for a in match_result["assignments"]
                    if a["tier"] != MT.NO_MATCH}
    llm_matched = [r for r in llm_elig if r["canonical_hypothesis_id"] in _matched_ids]
    llm_unmatched = [r for r in llm_elig
                     if r["canonical_hypothesis_id"] not in _matched_ids]
    bal = MT.balance(llm_matched, null_elig, match_result["control_weights"], COVFIELDS)
    bal["balance_population"] = "matched LLM families vs their weighted control sets"
    bal["n_llm_matched"] = len(llm_matched)
    bal["n_llm_unmatched"] = len(llm_unmatched)
    bal["unmatched_llm_composition"] = {
        f: dict(sorted(Counter(str(r["covariates"][f])
                               for r in llm_unmatched).items())) for f in COVFIELDS}
    comparability = MT.comparability_verdict(match_result, ess, bal)
    if not comparability["control_b_comparable"]:
        problems.append("CONTROL B NOT COMPARABLE (outcome-blind): "
                        + "; ".join(comparability["reasons"]))

    # ---- Tasks 1/2/8/9: descriptive data-compatibility + frozen attrition ladders -----
    FAILING = sorted(m for m, r in coverage["metrics"].items()
                     if not r["coverage_gate_pass"])

    def _compat(families, meas_lookup):
        drivers, naming = {}, 0
        for fam in families:
            tgt = set(fam["canonical_spec"]["TARGET"] or [])
            bad = tgt & set(FAILING)
            if bad:
                naming += 1
            for b in bad:
                drivers[b] = drivers.get(b, 0) + 1
        n_meas = sum(1 for fam in families
                     if meas_lookup[fam["canonical_hypothesis_id"]]["status"]
                     == P.MEASURABLE)
        return EP.data_compatibility(len(families), n_meas, naming, drivers)

    compat_llm = _compat(dedup["families"], llm_meas)
    compat_null = _compat(null["families"], null_meas)

    if not null_feasibility["null_endpoint_feasible"]:
        problems.append("PRIMARY NULL-BENCHMARK ENDPOINT INFEASIBLE (outcome-blind): "
                        + "; ".join(null_feasibility["reasons"]))

    # candidate lock: the ELIGIBLE candidate set for OOS = measurable AND comparator-ok
    # AND in a compilable family. Locked by hash BEFORE any OOS. (OOS not run here.)
    eligible = []
    ok_comp = {f["canonical_hypothesis_id"] for f in comparator_flags if f["ok"]}
    for fam in dedup["families"]:
        cid = fam["canonical_hypothesis_id"]
        if cid in measurable_ids and cid in ok_comp:
            eligible.append({"canonical_hypothesis_id": cid,
                             "canonical_spec": fam["canonical_spec"],
                             "arm_membership": fam["arm_membership"]})
    candidate_lock = candidate_lock_hash = W.candidate_lock_hash(eligible)

    # leakage mutation suite (Phase 24)
    leak = L.run_mutation_suite(reference_unix=min(ks) + 400 * 86400,
                                target_fixture_id="mt_LEAK_TEST")
    if not leak["all_pass"]:
        problems.append(f"leakage mutation suite failed: {leak['results']}")

    # ---- write artifacts ----
    hashes = {}
    hashes["V7_HYPOTHESIS_UNIVERSE.json"] = _write("V7_HYPOTHESIS_UNIVERSE.json", universe)
    hashes["V7_CANONICAL_HYPOTHESES.json"] = _write("V7_CANONICAL_HYPOTHESES.json", canon)
    hashes["V7_DEDUPLICATION.json"] = _write("V7_DEDUPLICATION.json", dedup)
    hashes["V7_MEASURABILITY.json"] = _write("V7_MEASURABILITY.json", {
        "measurability_version": P.PROVIDER_VERSION,
        "n_families": len(dedup["families"]),
        "counts": dict(meas_counts), "n_measurable": len(measurable_ids),
        "measurable_rate": round(len(measurable_ids) / max(len(dedup["families"]), 1), 4),
        "rows": meas_rows,
        "depends_on_effect": False})
    hashes["V7_PROVIDER_CONTRACT.json"] = _write("V7_PROVIDER_CONTRACT.json", {
        "provider_contract": P.METRIC_CONTRACT, "version_stamp": P.version_stamp(),
        "cross_provider_invariant": cross_provider})
    hashes["V7_COVERAGE_MATRIX.json"] = _write("V7_COVERAGE_MATRIX.json", coverage)
    hashes["V7_SIMILARITY_SPEC.json"] = _write("V7_SIMILARITY_SPEC.json", {
        **S.version_stamp(), "dimension_coverage_validation": sim_cov,
        "shrinkage_integrity": shrink_ok})
    hashes["V7_SUPPORT_RULES.json"] = _write("V7_SUPPORT_RULES.json", PIT.version_stamp())
    hashes["V7_CONFOUNDER_PLAN.json"] = _write("V7_CONFOUNDER_PLAN.json", {
        "confounder_plan": A.CONFOUNDER_PLAN, "allowed": list(A.ALLOWED_CONFOUNDERS),
        "comparator_semantics": A.VALID_COMPARATORS,
        "comparator_flags_over_measurable": comparator_flags,
        "n_comparator_rejected": n_comparator_rejected,
        "model_confounders_metadata_only": True})
    hashes["V7_MULTIPLICITY_PLAN.json"] = _write("V7_MULTIPLICITY_PLAN.json", {
        "families": A.MULTIPLICITY_FAMILIES, "method": A.MULTIPLICITY_METHOD,
        "fdr_q": A.FDR_Q, "promotion_rule": A.PROMOTION_RULE})
    hashes["V7_WALKFORWARD_FOLDS.json"] = _write("V7_WALKFORWARD_FOLDS.json", folds)
    hashes["V7_CONTROL_COMPARISON.json"] = _write("V7_CONTROL_COMPARISON.json", {
        "primary_endpoint": W.CONTROL_PRIMARY_ENDPOINT, "secondary": W.CONTROL_SECONDARY,
        "primary_control": "DETERMINISTIC_NULL_BENCHMARK (Phase 20 Control B)",
        "primary_null_endpoint": W.NULL_PRIMARY_ENDPOINT,
        "null_endpoint_feasibility": null_feasibility,
        "arm_endpoint_demoted_to_descriptive": not
            arm_feasibility["primary_endpoint_feasible"],
        "arm_endpoint_feasibility": arm_feasibility,
        "arm_matched_cells": matched,
        "arm_matched_cells_all_families_unrestricted": matched_all,
        "n_canonical_families_in_both_arms": dedup["n_families_both_arms"],
        "balanced_null_family_count": len(balanced_null),
        "v61_measurable_family_count": len(measurable_ids),
        "walkforward_version_stamp": W.version_stamp()})
    hashes["V7_CONTROL_B_COVARIATE_SPEC.json"] = _write(
        "V7_CONTROL_B_COVARIATE_SPEC.json",
        {**CV.schema(), "schema_sha256": CV.schema_hash(),
         "llm_rows": llm_cov, "null_rows": null_cov})
    hashes["V7_CONTROL_B_MATCHING_SPEC.json"] = _write(
        "V7_CONTROL_B_MATCHING_SPEC.json",
        {**MT.version_stamp(), "spec_sha256": MT.spec_hash(),
         "n_llm_eligible": len(llm_elig), "n_null_eligible": len(null_elig),
         "control_pool": {"sampling": NB.SAMPLING_MARGINAL,
                          "pool_size": NB.NULL_MATCHED_POOL_SIZE,
                          "n_families": nullm["n_canonical_families"],
                          "marginals_source": marginals["source"]}})
    hashes["V7_CONTROL_B_WEIGHTS.json"] = _write("V7_CONTROL_B_WEIGHTS.json", match_result)
    hashes["V7_CONTROL_B_BALANCE_REPORT.json"] = _write(
        "V7_CONTROL_B_BALANCE_REPORT.json", bal)
    hashes["V7_CONTROL_B_EFFECTIVE_SAMPLE.json"] = _write(
        "V7_CONTROL_B_EFFECTIVE_SAMPLE.json", ess)
    hashes["V7_ENDPOINT_SPEC.json"] = _write(
        "V7_ENDPOINT_SPEC.json", {**EP.version_stamp(), "spec_sha256": EP.spec_hash()})
    hashes["V7_DATA_COMPATIBILITY_ENDPOINT.json"] = _write(
        "V7_DATA_COMPATIBILITY_ENDPOINT.json",
        {"definition": EP.DATA_COMPATIBILITY,
         "coverage_failing_metrics": FAILING,
         "llm": compat_llm, "null": compat_null,
         "control_pool_used": {"sampling": NB.SAMPLING_UNIFORM,
                               "pool_size": NB.NULL_POOL_SIZE,
                               "why": ("the UNIFORM pool is the right comparator here: "
                                       "matching the control to the LLM's metric marginals "
                                       "would condition away the very difference this "
                                       "endpoint measures")},
         "is_football_evidence": False})
    hashes["V7_CONDITIONAL_SIGNAL_ENDPOINT.json"] = _write(
        "V7_CONDITIONAL_SIGNAL_ENDPOINT.json",
        {"definition": EP.CONDITIONAL_SIGNAL,
         "primary_statistic_definition": EP.OOS_QUALITY_SCORE,
         "n_llm_eligible": len(llm_elig), "n_null_eligible": len(null_elig),
         "comparability_verdict": comparability,
         "attrition_ladder_llm": EP.attrition_ladder(len(dedup["families"]),
                                                     len(measurable_ids)),
         "attrition_ladder_null": EP.attrition_ladder(len(null["families"]),
                                                      len(null_measurable_ids)),
         "confirmatory_oos_computed": False})
    hashes["V7_CONTROL_B_FREEZE.json"] = _write("V7_CONTROL_B_FREEZE.json", {
        "control_b_version": NB.NULL_VERSION,
        "pools": {
            "uniform": {"sampling": NB.SAMPLING_UNIFORM, "pool_size": NB.NULL_POOL_SIZE,
                        "n_families": null["n_canonical_families"],
                        "serves_endpoint": "END_TO_END_RESEARCH_YIELD + DATA_COMPATIBILITY"},
            "marginal_matched": {"sampling": NB.SAMPLING_MARGINAL,
                                 "pool_size": NB.NULL_MATCHED_POOL_SIZE,
                                 "n_families": nullm["n_canonical_families"],
                                 "serves_endpoint": "CONDITIONAL_SIGNAL_QUALITY"}},
        "structural_marginals": marginals,
        "covariate_schema_sha256": CV.schema_hash(),
        "matching_spec_sha256": MT.spec_hash(),
        "endpoint_spec_sha256": EP.spec_hash(),
        "null_seed": NB.NULL_SEED,
        "generated_before_oos": True,
        "covariates_defined_before_oos": True,
        "matching_algorithm_frozen_before_oos": True,
        "balance_thresholds_frozen_before_oos": True,
        "endpoint_definitions_frozen_before_oos": True,
        "clustering_method_frozen_before_oos": True,
        "confirmatory_oos_computed": False,
        "confirmatory_oos_viewed": False,
        "comparability": comparability})
    hashes["V7_NULL_BENCHMARK.json"] = _write("V7_NULL_BENCHMARK.json", {
        **{k: v for k, v in null.items() if k != "pool"},
        "pool": null["pool"],
        "measurability": {"counts": dict(null_meas_counts),
                          "n_measurable": len(null_measurable_ids),
                          "measurable_rate": round(null_meas_rate, 4),
                          "rows": null_meas_rows},
        "comparator_rejected": n_null_comp_rejected,
        "balanced_subset_ids": [f["canonical_hypothesis_id"] for f in balanced_null],
        "version_stamp": NB.version_stamp()})
    hashes["V7_CANDIDATE_LOCK.json"] = _write("V7_CANDIDATE_LOCK.json", {
        "candidate_lock_sha256": candidate_lock,
        "n_eligible_candidates": len(eligible),
        "eligibility_rule": ("MEASURABLE AND comparator-not-rejected AND compilable family; "
                             "locked by SHA-256 BEFORE any OOS; post-OOS change invalidates "
                             "confirmatory status"),
        "eligible": eligible})
    hashes["V7_LEAKAGE_AUDIT.json"] = _write("V7_LEAKAGE_AUDIT.json", leak)
    hashes["V7_OUTCOMES.json"] = _write("V7_OUTCOMES.json", O.version_stamp())

    # evaluator freeze = all V7 apparatus module hashes
    evaluator_freeze = {
        "evaluator_version": "v7_evaluator_v1",
        "frozen_before_confirmatory_oos": True,
        "computes_confirmatory_oos": False,
        "module_hashes": {m: _sha_file(f"{ROOT}/{m}") for m in V7_MODULES},
        "version_stamps": {
            "universe": U.version_stamp(), "canonical": C.version_stamp(),
            "provider": P.version_stamp(), "coverage": COV.version_stamp(),
            "pit": PIT.version_stamp(),
            "similarity": S.version_stamp(), "analysis": A.version_stamp(),
            "walkforward": W.version_stamp(), "outcomes": O.version_stamp(),
            "leakage": L.version_stamp(), "null_benchmark": NB.version_stamp(),
            "covariates": CV.schema(), "matching": MT.version_stamp(),
            "endpoints": EP.version_stamp()},
    }
    hashes["V7_EVALUATOR_FREEZE.json"] = _write("V7_EVALUATOR_FREEZE.json", evaluator_freeze)

    # champion isolation: no V7 module IMPORTS or REFERENCES production/prediction state.
    # We check executable code only (strip comments + docstrings via AST) so that a docstring
    # asserting "no p_model" is not itself flagged as a violation.
    import ast as _ast

    def _executable_tokens(path):
        tree = _ast.parse(open(path).read())
        # drop module/function/class docstrings, then unparse back to code-only text
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                                 _ast.ClassDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], _ast.Expr) and \
                        isinstance(getattr(body[0], "value", None), _ast.Constant) and \
                        isinstance(body[0].value.value, str):
                    body.pop(0)     # remove the docstring
        return _ast.unparse(tree)

    champ_isolation = {"champion_sha256": champ_sha,
                       "champion_unchanged": champ_sha == CHAMPION_FROZEN_SHA,
                       "auto_promotion": False,
                       "v7_writes_production_feature_config": False,
                       "v7_modifies_p_model": False,
                       "isolation_check": "executable code only (docstrings/comments stripped "
                                          "via AST)"}
    for m in V7_MODULES:
        code = _executable_tokens(f"{ROOT}/{m}")
        for tok in ("pilotC", "stat_mixer", "p_model"):
            if tok in code:
                champ_isolation.setdefault("violations", []).append(f"{m}:{tok}")
    if champ_isolation.get("violations"):
        problems.append(f"CHAMPION isolation violated: {champ_isolation['violations']}")

    # preregistration
    prereg = {
        "experiment": "V7_DETERMINISTIC_HYPOTHESIS_VALIDATION",
        "preregistration_version": "v7_preregistration_v1",
        "scientific_question": O.PRIMARY_SCIENTIFIC_QUESTION,
        "v6_1_history_refs": v61_refs,
        "v6_1_immutable": True,
        "hypothesis_universe": {"n_qualified": universe["n_qualified_total"],
                                "by_arm": universe["n_qualified_by_arm"],
                                "n_canonical_families": dedup["n_canonical_families"],
                                "n_duplicates": len(dedup["duplicate_classifications"])},
        "measurability": {"counts": dict(meas_counts),
                          "n_measurable": len(measurable_ids),
                          "coverage_gate": coverage["gate"],
                          "cross_provider_invariant": cross_provider},
        "primary_control": "DETERMINISTIC_NULL_BENCHMARK (Phase 20 Control B)",
        "null_benchmark_feasibility": null_feasibility,
        "arm_comparison_feasibility": arm_feasibility,
        "arm_comparison_status": ("DEMOTED_TO_DESCRIPTIVE" if not
                                  arm_feasibility["primary_endpoint_feasible"]
                                  else "CONFIRMATORY"),
        "primary_endpoints": list(O.PRIMARY_ENDPOINTS),
        "terminal_states": list(O.TERMINAL_STATES),
        "control_primary_endpoint": W.NULL_PRIMARY_ENDPOINT,
        "control_arm_endpoint_demoted": W.CONTROL_PRIMARY_ENDPOINT,
        "candidate_lock_sha256": candidate_lock,
        "walkforward": {"n_confirmatory_folds": folds["n_confirmatory_folds"],
                        "confirmatory_start": folds["confirmatory_window"]["start_iso"]},
        "multiplicity": {"method": A.MULTIPLICITY_METHOD, "fdr_q": A.FDR_Q},
        "champion_protection": champ_isolation,
        "artifact_hashes": hashes,
        "spend_authorization": "OOS execution authorization REQUIRED; this preregistration "
                               "does NOT authorize confirmatory OOS computation",
        "no_llm_effect_estimation": True,
        "confirmatory_oos_computed": False,
        "ends_at": "CANDIDATE_FEATURE_ELIGIBLE (no model promotion in V7)",
    }
    hashes["V7_PREREGISTRATION.json"] = _write("V7_PREREGISTRATION.json", prereg)

    # states
    out = {"states_version": "v7_states_v1", "blocking_problems": problems,
           "any_block": bool(problems)}
    if problems:
        out["executive_verdict"] = "V7_CONTROL_B_BLOCKED"
        out["states_emitted"] = []
        _write("V7_STATES.json", out)
        print("=== V7 PRE-OOS: BLOCKED ===")
        for p in problems:
            print("  BLOCK:", p)
        return 1

    if arm_feasibility["primary_endpoint_feasible"]:
        # Control A turned out usable: the state set below asserts it is NOT, so refuse to
        # emit a state that would misdescribe the design rather than silently relabelling.
        problems.append("V7_CONTROL_A_INFEASIBLE would be emitted but Control A is feasible")
        out["blocking_problems"] = problems
        out["any_block"] = True
        out["executive_verdict"] = "V7_CONTROL_B_BLOCKED"
        out["states_emitted"] = []
        _write("V7_STATES.json", out)
        print("=== V7 PRE-OOS: BLOCKED ===")
        for p_ in problems:
            print("  BLOCK:", p_)
        return 1

    out["states_emitted"] = REQUIRED_STATES
    out["executive_verdict"] = "V7_CONTROL_B_READY_FOR_OOS"
    out["control_b_verdict"] = "V7_CONTROL_B_REPAIRED_AND_REFROZEN"
    out["confirmatory_oos_computed"] = False
    out["confirmatory_oos_viewed"] = False
    out["candidate_feature_promotion"] = False
    out["bedrock_change_required"] = False
    out["candidate_lock_sha256"] = candidate_lock
    out["result"] = ("V7 apparatus, universe, folds, multiplicity, confounder plan and "
                     "evaluator frozen. V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED. STOP.")
    _write("V7_STATES.json", out)

    print("=== V7 PRE-OOS APPARATUS FROZEN (ZERO SPEND, NO CONFIRMATORY OOS) ===")
    print(f"  qualified hypotheses : {universe['n_qualified_total']} "
          f"(base {universe['n_qualified_by_arm']['base']}, "
          f"research {universe['n_qualified_by_arm']['research']})")
    print(f"  canonical families   : {dedup['n_canonical_families']} "
          f"({len(dedup['duplicate_classifications'])} duplicates collapsed)")
    print(f"  measurable families  : {len(measurable_ids)} "
          f"({dict(meas_counts)})")
    print(f"  comparator-rejected  : {n_comparator_rejected}")
    print(f"  eligible candidates  : {len(eligible)}  (locked {candidate_lock[:16]})")
    print(f"  confirmatory folds   : {folds['n_confirmatory_folds']}")
    print(f"  matched arm cells    : {matched['n_matched_cells']} "
          f"(measurable-restricted; {matched_all['n_matched_cells']} unrestricted)")
    print(f"  arm endpoint feasible: {arm_feasibility['primary_endpoint_feasible']} "
          f"(both-arm families={dedup['n_families_both_arms']})")
    print(f"  null benchmark       : {len(null['families'])} families, "
          f"{len(null_measurable_ids)} measurable "
          f"(rate {null_meas_rate:.3f} vs v6.1 {v61_meas_rate:.3f})")
    print(f"  balanced null subset : {len(balanced_null)} (cap={len(measurable_ids)})")
    print(f"  null endpoint feasible: {null_feasibility['null_endpoint_feasible']}")
    print(f"  control-B matching   : {match_result['n_matched']}/{match_result['n_llm']} "
          f"matched, {match_result['n_no_comparable_control']} NO_COMPARABLE_CONTROL "
          f"({match_result['no_comparable_fraction']:.3f})")
    print(f"    tiers              : {match_result['tier_composition']}")
    print(f"    ESS                : {ess['effective_n']} "
          f"(max share {ess['max_single_control_share']:.3f})")
    print(f"    balance            : worst |SMD|={bal['worst_smd_weighted']} "
          f"({bal['n_levels_out_of_balance']}/{bal['n_levels']} out of balance)")
    print(f"    comparable         : {comparability['control_b_comparable']}")
    print(f"  data-compat LLM/null : {compat_llm['data_compatibility_rate']} / "
          f"{compat_null['data_compatibility_rate']}")
    print(f"  leakage suite        : all_pass={leak['all_pass']}")
    print(f"  CHAMPION             : {champ_sha[:16]} unchanged="
          f"{champ_sha == CHAMPION_FROZEN_SHA}")
    print("\n  EXECUTIVE VERDICT: V7_CONTROL_B_READY_FOR_OOS "
          "(control B: REPAIRED_AND_REFROZEN)")
    for s in REQUIRED_STATES:
        print(f"    [FROZEN] {s}")
    print("\n  STOP. Do NOT compute confirmatory OOS results until explicitly authorized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
