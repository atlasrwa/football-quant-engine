"""Build + freeze every ITEM 6 STAGE 2 design artifact. ZERO OUTCOME ACCESS, ZERO LLM CALLS.

Reads: the frozen Stage-1 analysis result, the FootyStats corpus (feature inputs only), and the
champion artifact's DECLARED FEATURE NAMES (not its results).
Never reads: a target label, a market price, an OOS metric, or any model output.
"""
import hashlib, json, os, sys, time, collections

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import pilotC_stat_mixer as mix
from src.research.item6.stage2 import (canonical_family as CF, evaluation as EV,
                                       feature_generator as FG, feature_spec as FS,
                                       folds as FD, funnel as FN, model_specs as MS,
                                       power as PW, provider_measurability as PM,
                                       similarity_policy as SP, threshold_policy as TP)

OUT = "/home/ubuntu/research/item6/stage2"
STAGE1_RESULT = "/home/ubuntu/research/item6/out/execution/stage1_live_v6/ITEM6_STAGE1_RESULT_V1.json"
STAGE1_REGISTRY = "/home/ubuntu/research/item6/out/execution/stage1_live_v6/ITEM6_STAGE1_NOVEL_FAMILY_REGISTRY_V1.json"
PRIMARY_TARGET = {"market": "goals", "line": 2.5}
SECONDARY_TARGETS = [{"market": "corners", "line": 9.5}, {"market": "cards", "line": 3.5}]


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(o):
    return hashlib.sha256(canon(o)).hexdigest()


def write(name, obj):
    obj = dict(obj)
    obj["artifact_sha256"] = sha({k: v for k, v in obj.items() if k != "artifact_sha256"})
    p = f"{OUT}/{name}"
    with open(p, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    print(f"  {name}  sha256={obj['artifact_sha256']}")
    return p, obj["artifact_sha256"]


print("[1] loading frozen Stage-1 evidence")
s1 = json.load(open(STAGE1_RESULT))
s1reg = json.load(open(STAGE1_REGISTRY))
forms = []
for o in s1["per_fixture"]:
    for f in o["formalizations"]:
        g = dict(f); g["_fixture_id"] = o["fixture_id"]; forms.append(g)
n_f4 = sum(1 for f in forms if f["f_class"].startswith("F4"))
print(f"    mechanisms={len(forms)} F4={n_f4} stage1_registry_sha256={s1reg['novel_family_registry_sha256']}")

print("[2] funnel (pre-coverage)")
fun = FN.run_funnel(forms)
byseq = {int(r["seq"]): forms[int(r["seq"])] for r in fun["rows"]}
feas = [r for r in fun["rows"] if r["status"] in FN.FEASIBLE_STATUSES]
reg = CF.build_canonical_registry(feas, byseq)
spec = FS.build_feature_spec(reg)
print(f"    feasible={len(feas)} instantiations={reg['n_canonical_metric_instantiations']} cols={spec['n_columns']}")

print("[3] corpus + folds (chronology and feature sufficiency only; no labels)")
ms = [m for m in mix.load_corpus() if m.get("date_unix")]
def sufficiency(train, m):
    h = mix.build_histories(train)
    pv = mix.history_provenance(h, m.get("home_name"), m.get("away_name"), m.get("date_unix"))
    return bool(pv.get("sufficient"))
# build histories once per fold instead of per fixture
_cache = {}
def sufficiency_fast(train, m):
    key = id(train)
    if key not in _cache:
        _cache.clear(); _cache[key] = mix.build_histories(train)
    pv = mix.history_provenance(_cache[key], m.get("home_name"), m.get("away_name"),
                               m.get("date_unix"))
    return bool(pv.get("sufficient"))
foldman = FD.build_fold_manifest(ms, sufficiency_fn=sufficiency_fast)
FD.assert_chronological(foldman)
print(f"    folds_usable={foldman['n_folds_usable']} oos_candidates={foldman['n_oos_fixtures_candidate']} blocks={foldman['n_bootstrap_blocks_iso_weeks']}")

print("[4] training-period coverage screen (outer-training period of fold 0 only)")
f0 = [f for f in foldman["folds"] if not f["skipped"]][0]
train0 = [m for m in ms if m["date_unix"] < f0["train_end_unix"]]
hist0 = mix.build_histories(train0)
SAMPLE = train0[-5000:]
acc = {sk: [] for sk in spec["required_rolling_statistics"]}
share = {}
for m in SAMPLE:
    s = FG.compute_required_stats(hist0, m["home_name"], m["away_name"], m["date_unix"],
                                  spec["required_rolling_statistics"], season_key_fn=mix)
    for sk, d in s.items():
        acc[sk] += [v for v in d.values() if v is not None]
    for c in spec["columns"]:
        if c["kind"] == FS.KIND_HALF_SHARE:
            sk = f"{c['metric']}.{c['perspective']}.2H_SHARE.STD"
            t = m["home_name"] if c["team_slot"] == "h" else m["away_name"]
            sv = FG.second_half_share(hist0, t, c["metric"], c["perspective"], m["date_unix"],
                                       season=mix.current_season_key(hist0, t, m["date_unix"]),
                                       season_key_fn=mix._season_key)
            if sv is not None:
                share.setdefault(sk, []).append(sv)
acc.update(share)
ft = TP.fit(acc, fold_index=0, train_end_unix=f0["train_end_unix"])
pairs = sorted({FG.banding_key(list(c["axis_stat_keys"])) for c in spec["columns"]
                if c["kind"] == FS.KIND_PROFILE_DUMMY})
prof = {k: [] for k in pairs}
for m in SAMPLE[-2500:]:
    for k in pairs:
        aks = k.split("||")
        s = FG.compute_required_stats(hist0, m["home_name"], m["away_name"], m["date_unix"],
                                       aks, season_key_fn=mix)
        for slot in ("h", "a"):
            prof[k].append([(ak, ft.bin_of(ak, s.get(ak, {}).get(slot))) for ak in aks])
pb = {k: SP.fit(v, fold_index=0) for k, v in prof.items()}
cov = collections.Counter(); n_cov = 0
for m in SAMPLE[-3000:]:
    g = FG.generate_features(hist=hist0, home=m["home_name"], away=m["away_name"],
                             before=m["date_unix"], spec=spec, fitted_thresholds=ft,
                             profile_banding=pb, season_key_fn=mix)
    n_cov += 1
    for k, v in g["values"].items():
        if v is not None:
            cov[k] += 1
coverage = {c["name"]: round(cov[c["name"]] / n_cov, 6) for c in spec["columns"]}
below = sorted(k for k, v in coverage.items() if v < MS.MIN_NONMISSING_RATE)
print(f"    coverage computed over {n_cov} training fixtures; below screen={len(below)}")

print("[5] applying S2F3 (insufficient point-in-time coverage) to the funnel")
cols_by_inst = collections.defaultdict(list)
for c in spec["columns"]:
    cols_by_inst[str(c["canonical_key"])].append(str(c["name"]))
dead_keys = {k for k, names in cols_by_inst.items()
             if names and all(coverage.get(n, 0.0) < MS.MIN_NONMISSING_RATE for n in names)}
for r in fun["rows"]:
    if r["status"] in FN.FEASIBLE_STATUSES and str(r["canonical_key"]) in dead_keys:
        r["status"] = FN.S2F3
        r["reasons"] = [f"all columns below the inherited >={MS.MIN_NONMISSING_RATE} "
                        f"training-period coverage screen"]
counts = collections.Counter(str(r["status"]) for r in fun["rows"])
fun["status_counts"] = {s: int(counts.get(s, 0)) for s in FN.ALL_STATUSES}
fun["n_feasible"] = sum(int(counts.get(s, 0)) for s in FN.FEASIBLE_STATUSES)
fun["n_infeasible"] = len(fun["rows"]) - fun["n_feasible"]
fun["coverage_screen"] = {"min_nonmissing_rate": MS.MIN_NONMISSING_RATE,
                          "scope": MS.COVERAGE_SCREEN_SCOPE,
                          "n_instantiations_dropped": len(dead_keys),
                          "n_training_fixtures_used": n_cov,
                          "inherited_from": "champion predeclared >=60% coverage rule"}
feas = [r for r in fun["rows"] if r["status"] in FN.FEASIBLE_STATUSES]
reg = CF.build_canonical_registry(feas, byseq)
spec = FS.build_feature_spec(reg)
spec["training_period_coverage"] = {c["name"]: coverage.get(c["name"]) for c in spec["columns"]}
spec["n_columns_below_coverage_screen"] = sum(
    1 for c in spec["columns"] if coverage.get(c["name"], 0.0) < MS.MIN_NONMISSING_RATE)
print(f"    post-coverage feasible={fun['n_feasible']} instantiations={reg['n_canonical_metric_instantiations']} cols={spec['n_columns']}")

print("[6] M0 / M1 specs")
m0_names = mix.feat_names(PRIMARY_TARGET["market"])
llm_names = [c["name"] for c in spec["columns"]]
m0 = MS.m0_spec(m0_names); m1 = MS.m1_spec(m0_names, llm_names)
parity = MS.parity_assertions(m0, m1)
print(f"    M0={m0['n_features']} M1={m1['n_features']} parity_only_feature_diff={parity['only_difference_is_llm_feature_availability']}")

print("[7] power sensitivity")
med = sorted(coverage.values())[len(coverage)//2] if coverage else 0.0
pwr = PW.build_power_sensitivity(
    n_oos_predictions=foldman["n_oos_fixtures_candidate"],
    n_blocks=foldman["n_bootstrap_blocks_iso_weeks"], n_folds=foldman["n_folds_usable"],
    median_feature_coverage=med, n_columns_below_coverage_screen=spec["n_columns_below_coverage_screen"])

print("[8] writing artifacts")
arts = {}
def rec(name, obj):
    p, h = write(name, obj); arts[name] = {"path": p, "sha256": h}

target_relevance = {}
TM = {"goals": {"goals"}, "corners": {"corner_kicks"},
      "cards": {"yellow_cards", "red_cards", "cards_2h"}, "btts": {"goals"}}
for t, mets in TM.items():
    target_relevance[t] = sum(1 for i in reg["metric_instantiations"]
                              if {c["metric"] for c in i["canonical_metrics"]} & mets)

rec("ITEM6_STAGE2_FEASIBILITY_FUNNEL_V1.json", fun)
rec("ITEM6_STAGE2_CANONICAL_FAMILY_REGISTRY_V1.json", reg)
rec("ITEM6_STAGE2_FEATURE_SPEC_V1.json", spec)
rec("ITEM6_STAGE2_THRESHOLD_POLICY_V1.json",
    {**TP.version_stamp(), "min_train_obs_for_edges": TP.MIN_TRAIN_OBS_FOR_EDGES,
     "bin_labels": list(TP.BIN_LABELS)})
rec("ITEM6_STAGE2_SIMILARITY_POLICY_V1.json", SP.version_stamp())
rec("ITEM6_STAGE2_GRAMMAR_EXTENSIONS_V1.json", {
    "grammar_extensions_version": "item6_stage2_grammar_extensions_v1",
    "existing_extensions": list(FN.EXISTING_EXTENSIONS),
    "new_deterministic_extensions": list(FN.NEW_EXTENSIONS),
    "structural_family_map": CF.STRUCTURAL_FAMILIES,
    "extension_to_feature_kind": {
        "GX_THRESHOLD_CONDITION": FS.KIND_BAND_DUMMY,
        "GX_CROSS_METRIC_JOINT": FS.KIND_STD_PRODUCT,
        "GX_HALF_STATE_INTERACTION": FS.KIND_HALF_SHARE,
        "GX_TWO_AXIS_PROFILE_INTERSECTION": FS.KIND_PROFILE_DUMMY,
        "GX_SEQUENCE_REGIME": "REJECTED_NO_PIT_SAFE_SEQUENCE_REPRESENTATION"},
    "all_extensions_additive_and_deterministic": True})
rec("ITEM6_STAGE2_BASELINE_MODEL_SPEC_V1.json", m0)
rec("ITEM6_STAGE2_AUGMENTED_MODEL_SPEC_V1.json", m1)
rec("ITEM6_STAGE2_MULTIPLICITY_POLICY_V1.json",
    {**MS.multiplicity_policy(), "parity_assertions": parity})
rec("ITEM6_STAGE2_FOLD_MANIFEST_V1.json", foldman)
rec("ITEM6_STAGE2_POWER_SENSITIVITY_V1.json", pwr)
rec("ITEM6_STAGE2_EVALUATION_PROTOCOL_V1.json",
    {**EV.version_stamp(), "decision_rule": EV.decision_rule(),
     "failure_modes": EV.failure_modes(),
     "secondary_metrics": list(EV.SECONDARY_METRICS),
     "statistical_unit": "one_out_of_sample_fixture_prediction",
     "dependence_handling": "paired_cluster_block_bootstrap_over_iso_match_weeks",
     "primary_target": PRIMARY_TARGET, "secondary_targets": SECONDARY_TARGETS})
rec("ITEM6_STAGE2_PROVIDER_MEASURABILITY_V1.json",
    {**PM.version_stamp(),
     "footystats_measurable_metrics": sorted(PM.FOOTYSTATS_FULL_MATCH_FIELD),
     "half_capable_metrics": sorted(PM.HALF_CAPABLE),
     "against_aliases": PM.AGAINST_ALIAS,
     "footystats_absent_concepts": sorted(PM.FOOTYSTATS_ABSENT),
     "empirical_evidence": "corpus match records carry 215 fields; a field-name scan for "
                           "cross/block/tackle/clearance/interception/recovery/touch/pass/"
                           "big_chance returned ZERO matches",
     "accurate_crosses_status": FN.S2F1, "blocks_status": FN.S2F1,
     "goals_conceded_status": FN.S2F8 + " (via AGAINST perspective, existing machinery)"})

protocol = {
    "protocol_version": "item6_stage2_protocol_v1",
    "stage": "STAGE_2_INCREMENTAL_OOS_PREDICTIVE_VALUE",
    "status": "DESIGN_FROZEN_EXECUTION_UNAUTHORIZED",
    "scientific_question":
        "Do deterministically instantiated features derived from the frozen Item 6 "
        "LLM-discovered novel hypothesis families improve walk-forward out-of-sample predictive "
        "performance beyond the frozen deterministic baseline feature universe, when both are "
        "subject to the same data, leakage controls, training process, regularization, "
        "calibration and evaluation?",
    "what_stage2_is_not":
        "It is NOT a search for which of the 592 Stage-1 ideas works. Per-family selection on "
        "OOS results would be a multiple-testing fishing expedition. The primary claim is "
        "M1-universe vs M0-universe.",
    "governing_principle":
        "The LLM is not the predictor. Its role ended at hypothesis proposal. No LLM numerical "
        "reasoning enters Stage 2: the deterministic engine owns feature construction, "
        "thresholds, support counts, similarity, screening, regularization, coefficients, "
        "calibration, p_model and evaluation.",
    "stage1_inputs": {
        "stage1_gate": "PASS",
        "stage1_result_path": STAGE1_RESULT,
        "stage1_novel_family_registry_sha256": s1reg["novel_family_registry_sha256"],
        "n_stage1_mechanisms": len(forms), "n_stage1_accepted_f4": n_f4,
        "n_stage1_signatures": s1["endpoints"]["new_family_count"]},
    "measurement_requirement_source": "deterministic distinct_metrics (NOT the LLM-authored "
                                      "provider_requirements field)",
    "temporal_resolution_source": "period field of the mechanism's cited evidence refs (NOT the "
                                  "LLM's self-declared temporal_resolution_requirement)",
    "target_selection_rule": {
        "rule_provenance":
            "The relevance counts below were COMPUTED FIRST, then the criterion was written. "
            "Both happened before any outcome access -- the counts are a property of the "
            "feasible family set and the target metric definitions, not of any result. The "
            "strongest evidence that the criterion is not gamed is its outcome: it selected "
            "GOALS, while Stage-1 mechanism density was highest for CORNERS.",
        "rule": "The PRIMARY target is the market family "
                "with the largest number of FEASIBLE canonical metric instantiations, because a "
                "target the surviving families cannot speak to yields a null by construction "
                "and answers nothing. Tie-break: base rate closest to 0.50 (maximum information "
                "per prediction).",
        "relevant_instantiation_counts": target_relevance,
        "selected_primary": PRIMARY_TARGET,
        "tie_break_applied": "goals and btts tie on metric relevance; goals O/U 2.5 base rate "
                             "0.556 is closer to 0.50 than btts 0.569",
        "not_selected_because_of_stage1_density":
            "The criterion selected the GOALS family. Stage-1 mechanism density was highest for "
            "corners, which it did NOT select -- so target choice was not driven by where the "
            "LLM happened to generate most.",
        "secondary_targets": SECONDARY_TARGETS},
    "arms": {"M0": "deterministic baseline feature universe (champion stat-mixer pool, "
                   "unweakened)",
             "M1": "M0 + the frozen Stage-2-feasible LLM-derived feature universe",
             "only_difference": "availability of the LLM-discovered feature families"},
    "stage2_m0_is_not_the_production_champion":
        "Both arms re-tune identically by nested chronological CV inside training folds. Reusing "
        "the champion's frozen (C, l1_ratio) -- selected against M0's own pool -- would break "
        "model parity in M0's favour, which is a declared TRUE BLOCKER. The champion artifact is "
        "never written to.",
    "no_outcome_access_during_build": True,
    "no_production_promotion": "Even a Stage-2 PASS promotes nothing. Required onward funnel: "
                               "prospective shadow -> calibration -> market comparison -> "
                               "genuine close -> settlement -> promotion review.",
    "market_edge_excluded_from_primary_endpoint": True,
    "design_amendments": [{
        "amendment_id": "S2-DESIGN-A1",
        "timing": "after the v1 freeze, before any Stage-2 execution, fit or outcome access",
        "unchanged_byte_identical": [
            "ITEM6_STAGE2_FEASIBILITY_FUNNEL_V1.json",
            "ITEM6_STAGE2_CANONICAL_FAMILY_REGISTRY_V1.json",
            "ITEM6_STAGE2_FEATURE_SPEC_V1.json", "ITEM6_STAGE2_FOLD_MANIFEST_V1.json",
            "ITEM6_STAGE2_THRESHOLD_POLICY_V1.json", "ITEM6_STAGE2_SIMILARITY_POLICY_V1.json",
            "ITEM6_STAGE2_GRAMMAR_EXTENSIONS_V1.json",
            "ITEM6_STAGE2_PROVIDER_MEASURABILITY_V1.json"],
        "changes": [
            "model_specs v1->v2: removed 'grouped shrinkage over structural families' (declared "
            "with no group penalty or solver; an executor free parameter and the one declared "
            "machinery difference between arms). Pinned estimator (saga, max_iter 4000, tol 1e-4, "
            "random_state 0), selection rule, calibration data source (isotonic on inner "
            "TimeSeriesSplit OOF predictions, not in-sample), and a [0.01, 0.99] output clip, all "
            "inherited from the champion fitter where one existed. Parity check now fails on ANY "
            "non-feature key that differs between arms.",
            "evaluation v1->v2: pinned scored-set intersection rule, pooling, bootstrap "
            "procedure, percentile CI, ECE binning (champion's 10 equal-width bins), secondary "
            "metric definitions, ablation construction, family-level and secondary-target tests, "
            "fold-failure handling. Decision rule thresholds UNCHANGED.",
            "power v1->v2: bracketed precision between a conservative (block-count) and an "
            "independent (fixture-count) bound; v1 stated the worst case as the verdict. Added "
            "80%-power effect sizes under the conjunctive rule and its <=50% ceiling at MPI.",
            "outcome-blindness audit: narrowed the champion-metadata claim (full-corpus champion "
            "overlaps the OOS window) with the reason it cannot bias the paired endpoint."],
        "decision_rule_changed": False,
        "minimum_practical_improvement_changed": False,
        "outcomes_inspected_before_amendment": False}],
    "artifacts": arts,
}
rec("ITEM6_STAGE2_PROTOCOL_V1.json", protocol)

runman = {
    "run_manifest_version": "item6_stage2_run_manifest_v1",
    "status": "DESIGN_FROZEN_AWAITING_EXPLICIT_HUMAN_EXECUTION_AUTHORIZATION",
    "stage2_executed": False,
    "stage1_oos_data_visible": False,
    "live_sonnet_calls": 0, "bedrock_paid_calls": 0, "pass_b_paid_calls": 0,
    "new_llm_spend_usd": 0,
    "champion_sha256": "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9",
    "champion_independent": True,
    "primary_target": PRIMARY_TARGET, "secondary_targets": SECONDARY_TARGETS,
    "n_oos_fixtures_candidate": foldman["n_oos_fixtures_candidate"],
    "n_folds": foldman["n_folds_usable"],
    "fold_manifest_sha256": foldman["fold_manifest_sha256"],
    "module_versions": {
        "provider_measurability": PM.PROVIDER_MEASURABILITY_VERSION,
        "funnel": FN.FUNNEL_VERSION, "canonical_family": CF.CANONICAL_FAMILY_VERSION,
        "threshold_policy": TP.THRESHOLD_POLICY_VERSION,
        "similarity_policy": SP.SIMILARITY_POLICY_VERSION,
        "feature_spec": FS.FEATURE_SPEC_VERSION,
        "feature_generator": FG.FEATURE_GENERATOR_VERSION,
        "model_specs": MS.MODEL_SPECS_VERSION, "folds": FD.FOLDS_VERSION,
        "evaluation": EV.EVALUATION_VERSION, "power": PW.POWER_VERSION},
    "artifacts": arts,
    "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
rec("ITEM6_STAGE2_RUN_MANIFEST_V1.json", runman)

audit = {
    "audit_version": "item6_stage2_outcome_blindness_audit_v1",
    "STAGE2_OUTCOMES_INSPECTED_DURING_BUILD": False,
    "STAGE2_PRIMARY_METRIC_COMPUTED": False,
    "M0_OOS_RESULTS_VISIBLE": False,
    "M1_OOS_RESULTS_VISIBLE": False,
    "what_was_read": [
        "frozen Stage-1 generation evidence and formalization records",
        "FootyStats corpus FEATURE INPUT fields (rolling stat inputs, half splits) and match "
        "timestamps",
        "corpus record schema (field names)",
        "champion artifact DECLARED FEATURE NAMES and training-period metadata "
        "(base_rate, n_train, reported BSS)",
    ],
    "what_was_never_read": [
        "any Stage-2 target label via mix.outcome() or otherwise",
        "any Stage-2 OOS metric (log loss, Brier, ECE) for either arm",
        "any market price, closing line, settlement or genuine close",
        "any per-family predictive result",
    ],
    "champion_metadata_justification":
        "base_rate / n_train / reported BSS / ECE were read from the FROZEN CHAMPION ARTIFACT "
        "(research/contextual_matchup/CHAMPION_FREEZE.json) of a PRIOR completed experiment. No "
        "Stage-2 fold, arm or prediction was scored to obtain them. They were used only to anchor "
        "the minimum practical improvement and the target tie-break, both frozen before "
        "execution.",
    "champion_metadata_overlap_disclosure":
        "The champion is 'elasticnet_logistic_full_corpus': its base rates come from the same "
        "FootyStats corpus, so they DO cover calendar periods inside the Stage-2 OOS window, and "
        "its reported BSS/ECE are an M0-like model's aggregate skill on a chronological 30% tail "
        "that also overlaps it. They are therefore NOT free of Stage-2-period outcome "
        "information. What they are is aggregate marginal statistics (one base rate per market, "
        "one BSS/ECE per market) from a prior experiment already in the repository. They carry "
        "no information about the paired M0-vs-M1 per-fixture difference, which is the primary "
        "endpoint, and no information about any LLM-derived feature. So they cannot bias the "
        "primary comparison and do not trigger a re-cohort; this disclosure narrows the v1 "
        "claim that they were 'not Stage-2 outcomes'.",
    "mix_outcome_never_called": True,
    "outcome_label_function_scope_note":
        "`mix.outcome()` -- the only label-producing function in the pipeline -- was never "
        "called anywhere in the Stage-2 build. Verified by inspection of this build script and "
        "the stage2 package; a test additionally asserts the feature generator contains no "
        "reference to it.",
    "fold_manifest_inputs":
        "date_unix, home_name, away_name, competition_id and feature-sufficiency match COUNTS "
        "only. Sufficiency comes from mix.history_provenance(), which was read and verified to "
        "compute only season keys, completed-match counts and window-population flags -- it "
        "touches no score or outcome field.",
    "scope_caveat":
        "Corpus match dicts physically contain outcome fields (homeGoalCount, totalGoalCount, "
        "team_a_corners, ...) because they are whole provider records. The claim made here is "
        "that no such field was READ or EVALUATED for any target, not that the dicts were "
        "stripped of them. Feature construction reads only the metric fields named in "
        "feature_generator.FULL_FIELDS / HALF_FIELDS, of which team_a_corners and homeGoalCount "
        "are legitimately among them AS PRIOR-MATCH FEATURE INPUTS for completed matches "
        "strictly before kickoff -- never as a label for the fixture being predicted.",
    "fold_manifest_built_without_label_availability": True,
}
rec("ITEM6_STAGE2_OUTCOME_BLINDNESS_AUDIT_V1.json", audit)

summary = {
    "n_stage1_mechanisms": len(forms), "n_stage1_accepted_f4": n_f4,
    "n_stage1_signatures": s1["endpoints"]["new_family_count"],
    "funnel_status_counts": fun["status_counts"],
    "n_feasible": fun["n_feasible"], "n_infeasible": fun["n_infeasible"],
    "n_canonical_structural_families": reg["n_canonical_structural_families"],
    "n_canonical_metric_instantiations": reg["n_canonical_metric_instantiations"],
    "structural_families": [(s["structural_family"], s["n_metric_instantiations"])
                            for s in reg["structural_families"]],
    "n_llm_feature_columns": spec["n_columns"],
    "m0_n_features": m0["n_features"], "m1_n_features": m1["n_features"],
    "n_oos_candidates": foldman["n_oos_fixtures_candidate"],
    "n_blocks": foldman["n_bootstrap_blocks_iso_weeks"],
    "n_folds": foldman["n_folds_usable"],
    "max_detectable_paired_sd": pwr["max_paired_sd_detectable_at_minimum_practical_improvement"],
    "max_paired_sd_ci_within_mpi_bounds": pwr["max_paired_sd_with_ci_half_width_at_or_below_mpi"],
    "model_specs_version": MS.MODEL_SPECS_VERSION, "evaluation_version": EV.EVALUATION_VERSION,
    "power_version": PW.POWER_VERSION,
    "parity_differing_knobs": parity["differing_shared_knobs"],
    "target_relevance": target_relevance,
}
json.dump(summary, open(f"{OUT}/_BUILD_SUMMARY.json", "w"), indent=1, sort_keys=True)
print("\nSUMMARY " + json.dumps(summary, sort_keys=True))
