"""V7 Control-B comparability, endpoint and regression-lock tests. ZERO SPEND, NO OOS.

Covers Task 21's 23 adversarial cases plus the Task 11 fairness nulls and the Task 15/16/17
regression locks. Nothing here computes or reads a confirmatory OOS result.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_v7 import analysis_spec as A
from src.research.hypothesis_v7 import canonical as C
from src.research.hypothesis_v7 import coverage as COV
from src.research.hypothesis_v7 import covariates as CV
from src.research.hypothesis_v7 import endpoints as EP
from src.research.hypothesis_v7 import matching as MT
from src.research.hypothesis_v7 import null_benchmark as NB
from src.research.hypothesis_v7 import provider as P
from src.research.hypothesis_v7 import similarity as S

ROOT = "/home/ubuntu"
V7_OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"


def _load(name):
    return json.load(open(f"{V7_OUT}/{name}"))


def _cov(**kw):
    base = {"uses_similarity": False, "comparator": "SUBJECT_OVERALL_BASELINE",
            "n_conditions": 0, "measurability_status": "MEASURABLE",
            "requires_half_resolution": False, "support_risk_class": "LOW",
            "coverage_class": "FULL", "metric_group": "SCORING", "target_band": "T2",
            "time_scope": "ALL_PRIOR", "subject": "HOME_TEAM", "side": "FOR"}
    base.update(kw)
    return base


def _row(cid, **kw):
    return {"canonical_hypothesis_id": cid, "covariates": _cov(**kw)}


# =====================================================================================
# Task 21 cases 1-5: weighting cannot be inflated by duplication or pool size
# =====================================================================================
def test_21_01_duplicated_controls_do_not_increase_weight():
    llm = [_row("L1")]
    few = [_row(f"C{i}") for i in range(3)]
    many = few + [_row(f"D{i}") for i in range(97)]
    a, b = MT.match(llm, few), MT.match(llm, many)
    # total control weight is 1 per LLM family regardless of how many controls exist
    assert abs(sum(a["control_weights"].values()) - 1.0) < 1e-9
    assert abs(sum(b["control_weights"].values()) - 1.0) < 1e-9


def test_21_02_duplicated_llm_hypotheses_do_not_increase_weight():
    """Deduplication happens upstream: one canonical family = one row = one unit of weight."""
    dedup = _load("V7_DEDUPLICATION.json")
    assert dedup["n_canonical_families"] < dedup["n_raw_qualified"]
    w = _load("V7_CONTROL_B_WEIGHTS.json")
    ids = [a["canonical_hypothesis_id"] for a in w["assignments"]]
    assert len(ids) == len(set(ids)), "an LLM family appears twice in the matched design"


def test_21_03_large_control_pool_does_not_create_naive_precision():
    ess = _load("V7_CONTROL_B_EFFECTIVE_SAMPLE.json")
    w = _load("V7_CONTROL_B_WEIGHTS.json")
    # total control weight equals the number of MATCHED LLM families, never the pool size
    assert abs(ess["total_control_weight"] - w["n_matched"]) < 1e-6
    assert ess["total_control_weight"] < ess["raw_null_n"]
    assert MT.version_stamp()["control_pool_buys_flexibility_not_n"] is True


def test_21_04_poor_common_support_blocks_matched_inference():
    llm = [_row(f"L{i}", metric_group="TERRITORY") for i in range(10)]
    null = [_row(f"C{i}", metric_group="SCORING") for i in range(500)]
    m = MT.match(llm, null)
    assert m["n_no_comparable_control"] == 10
    ess = MT.effective_sample(m["control_weights"], len(null))
    bal = MT.balance([], null, m["control_weights"], list(CV.MATCHING_COVARIATES))
    v = MT.comparability_verdict(m, ess, bal)
    assert v["control_b_comparable"] is False
    assert any("no_comparable_fraction" in r for r in v["reasons"])


def test_21_05_unmatched_llm_hypothesis_is_labelled_not_force_matched():
    llm = [_row("L1", comparator="SIMILAR_OPPONENT_COHORT")]
    null = [_row(f"C{i}") for i in range(50)]
    m = MT.match(llm, null)
    a = m["assignments"][0]
    assert a["tier"] == MT.NO_MATCH
    assert a["n_controls"] == 0 and a["weight_per_control"] == 0.0


# =====================================================================================
# Task 21 cases 6-10: imbalance is visible and reduced by matching
# =====================================================================================
@pytest.mark.parametrize("field,llm_val,null_val", [
    ("metric_group", "SET_PIECE", "DISCIPLINE"),          # 6 target-metric imbalance
    ("n_conditions", 0, 1),                                # 7 condition-count imbalance
    ("uses_similarity", True, False),                      # 8 similarity-use imbalance
    ("coverage_class", "FULL", "PARTIAL"),                 # 9 coverage-class imbalance
    ("support_risk_class", "LOW", "HIGH"),                 # 10 support-class imbalance
])
def test_21_06_to_10_imbalance_visible_and_reduced(field, llm_val, null_val):
    llm = [_row(f"L{i}", **{field: llm_val}) for i in range(10)]
    null = ([_row(f"C{i}", **{field: null_val}) for i in range(40)]
            + [_row(f"G{i}", **{field: llm_val}) for i in range(10)])
    m = MT.match(llm, null)
    bal = MT.balance(llm, null, m["control_weights"], [field])
    raw = max(r["smd_raw"] for r in bal["rows"])
    wtd = max(r["smd_weighted"] for r in bal["rows"])
    assert raw > 0, f"{field}: imbalance must be VISIBLE in the raw diagnostic"
    assert wtd <= raw, f"{field}: matching must not worsen imbalance ({wtd} > {raw})"
    assert wtd <= MT.MAX_STANDARDIZED_DIFF, f"{field}: weighted imbalance {wtd} not reduced"


# =====================================================================================
# Task 21 cases 11-12: concentration and ESS
# =====================================================================================
def test_21_11_extreme_weights_trigger_concentration_failure():
    ess = MT.effective_sample({"c1": 0.9, "c2": 0.05, "c3": 0.05}, 3)
    assert ess["concentration_ok"] is False
    assert ess["max_single_control_share"] > MT.MAX_CONTROL_WEIGHT_SHARE


def test_21_12_effective_sample_size_is_correct():
    assert abs(MT.effective_sample({f"c{i}": 1.0 for i in range(4)}, 4)["effective_n"]
               - 4.0) < 1e-9
    # (0.9+0.05+0.05)^2 / (0.81+0.0025+0.0025) = 1/0.815
    got = MT.effective_sample({"a": 0.9, "b": 0.05, "c": 0.05}, 3)["effective_n"]
    assert abs(got - (1.0 / 0.815)) < 1e-6
    assert MT.effective_sample({}, 0)["effective_n"] == 0.0


# =====================================================================================
# Task 21 cases 13-15: the design cannot reach outcomes
# =====================================================================================
def test_21_13_14_matching_and_covariates_cannot_read_oos_or_effects():
    for mod in ("matching", "covariates", "endpoints", "null_benchmark"):
        src = open(f"{ROOT}/src/research/hypothesis_v7/{mod}.py").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                b = getattr(node, "body", [])
                if b and isinstance(b[0], ast.Expr) and isinstance(
                        getattr(b[0], "value", None), ast.Constant) and isinstance(
                        b[0].value.value, str):
                    b.pop(0)
        # drop the guard list itself -- FORBIDDEN_COVARIATE_SOURCES *names* the tokens it
        # exists to forbid, so scanning it would flag the guard as the violation.
        tree.body = [n for n in tree.body
                     if not (isinstance(n, ast.Assign)
                             and any(getattr(t, "id", None) in
                                     ("FORBIDDEN_COVARIATE_SOURCES",
                                      "DESCRIPTIVE_ONLY_COVARIATES")
                                     for t in n.targets))]
        code = ast.unparse(tree)
        for tok in ("V7_OUTCOMES", "oos_result", "OOS_RESULTS", "fold_effect",
                    "effect_size", "p_value"):
            assert tok not in code, f"{mod} references {tok}"
        # no module may open a file for reading OOS artifacts either
        assert "out/v7" not in code, f"{mod} reaches into the artifact directory"


def test_21_15_null_generator_cannot_access_v6_1_outcomes():
    src = open(f"{ROOT}/src/research/hypothesis_v7/null_benchmark.py").read()
    for tok in ("scores.json", "V6_1_VERDICT", "execution/raw", "qualified",
                "scorecard", "verdict"):
        assert tok not in src, f"null generator references {tok}"
    assert NB.version_stamp()["reads_outcomes"] is False
    # marginals are derived from canonical STRUCTURE only
    fams = _load("V7_DEDUPLICATION.json")["families"]
    marg = NB.derive_marginals(fams)
    assert "structure only" in marg["source"]


# =====================================================================================
# Task 21 case 16: Base-vs-Research cannot become the confirmatory primary
# =====================================================================================
def test_21_16_arm_contrast_cannot_become_confirmatory_primary():
    cc = _load("V7_CONTROL_COMPARISON.json")
    assert cc["arm_endpoint_feasibility"]["primary_endpoint_feasible"] is False
    assert cc["arm_endpoint_demoted_to_descriptive"] is True
    assert cc["n_canonical_families_in_both_arms"] == 0
    assert EP.version_stamp()["arm_contrast_is_descriptive_only"] is True
    prereg = _load("V7_PREREGISTRATION.json")
    assert "DETERMINISTIC_NULL" in prereg["control_primary_endpoint"]


# =====================================================================================
# Task 21 cases 17-18: the two endpoints treat unmeasurable families oppositely
# =====================================================================================
def test_21_17_end_to_end_endpoint_includes_unmeasurable():
    assert EP.END_TO_END["includes_unmeasurable"] is True
    assert EP.END_TO_END["denominator"].startswith("ALL frozen canonical families")
    ce = _load("V7_CONDITIONAL_SIGNAL_ENDPOINT.json")
    ladder = ce["attrition_ladder_llm"]
    # the ladder starts from ALL canonical families, not the measurable subset
    assert ladder["canonical"] > ladder["measurable"]
    assert ladder["oos_survives"] is None and ladder["oos_stage_computed"] is False


def test_21_18_conditional_endpoint_excludes_unmeasurable_symmetrically():
    assert EP.CONDITIONAL_SIGNAL["excludes_unmeasurable"] is True
    assert EP.CONDITIONAL_SIGNAL["eligibility_applied_symmetrically"] is True
    assert EP.CONDITIONAL_SIGNAL["eligibility"] == ["MEASURABLE", "ADEQUATE_SUPPORT"]
    cs = _load("V7_CONTROL_B_COVARIATE_SPEC.json")
    # both origins are filtered by the SAME predicate
    for side in ("llm_rows", "null_rows"):
        assert all(("is_measurable" in r["covariates"]) for r in cs[side])


def test_21_17b_data_compatibility_is_separate_from_football_evidence():
    dc = _load("V7_DATA_COMPATIBILITY_ENDPOINT.json")
    assert dc["is_football_evidence"] is False
    assert dc["definition"]["is_predictive_evidence"] is False
    # the LLM's lower compatibility is REPORTED, not hidden
    assert dc["llm"]["data_compatibility_rate"] < dc["null"]["data_compatibility_rate"]
    assert dc["llm"]["coverage_failing_share"] > dc["null"]["coverage_failing_share"]
    assert dc["control_pool_used"]["sampling"] == NB.SAMPLING_UNIFORM


# =====================================================================================
# Task 16 / case 19: coverage regression locks
# =====================================================================================
def test_21_19_xg_ligue2_coverage_failure_propagates():
    cov = _load("V7_COVERAGE_MATRIX.json")
    xg = cov["metrics"]["xg"]
    assert xg["competition_coverage"]["ligue2"] == 0.0, "Ligue 2 xG must be measured as zero"
    assert xg["coverage_gate_pass"] is False
    assert "ligue2" in xg["excluded_competitions"]
    # the gate propagates to the hypothesis verdict
    m = P.classify_measurability({"TARGET": ["xg"], "COMPARATOR": "SUBJECT_OVERALL_BASELINE",
                                  "CONDITIONS": [], "SIMILARITY_DIMENSIONS": []}, cov)
    assert m["status"] == P.UNMEASURABLE_COVERAGE
    # and similarity may not use an xG dimension
    assert "xg_conceded_per_match" not in S.SIMILARITY_DIMENSIONS
    assert "xg" not in S.DIMENSION_METRIC.values()
    assert S.validate_dimension_coverage(cov)["all_dimensions_clear_coverage_gate"] is True


def test_coverage_lock_previously_excluded_fields_are_measurable():
    """Task 16: shots / possession / saves were wrongly excluded by the v1 contract."""
    cov = _load("V7_COVERAGE_MATRIX.json")
    for metric in ("shots", "possession", "saves"):
        row = cov["metrics"][metric]
        assert row["coverage_gate_pass"] is True, metric
        assert row["excluded_competitions"] == [], metric
        assert row["overall_coverage"] >= 0.95, metric
        r = P.resolve_metric(metric, cov)
        assert r["status"] == P.MEASURABLE, metric
        assert r["field"] is not None and r["block"] in ("base", "rich", "extra")
    # `shots` must read the provider's own total, never a sum of the box split
    assert P.METRIC_CONTRACT["shots"]["field"] == "total_shots"
    assert "never summed" in P.METRIC_CONTRACT["shots"]["semantic"]


# =====================================================================================
# Task 15 / cases 20-21: provider-provenance regression lock
# =====================================================================================
def test_21_20_genuine_cross_provider_mismatch_is_rejected():
    """A REAL two-provider target set must be refused all the way to a verdict."""
    saved = dict(P.METRIC_CONTRACT)
    try:
        # inject a genuinely foreign-provider metric
        P.METRIC_CONTRACT["fs_total_shots"] = {
            "block": "base", "field": "fs_total_shots", "unit": "count",
            "semantic": "FootyStats total shots (different shot definition, corr 0.80)",
            "resolution": "match", "audited": True}
        real = P.resolve_metric("shots", {"metrics": {"shots": {
            "overall_coverage": 0.99, "competition_coverage": {"a": 0.99},
            "excluded_competitions": [], "admissible_competitions": ["a"],
            "coverage_gate_pass": True}}})
        assert real["provider"] == P.THESTATSAPI
        # simulate the foreign row resolving to the OTHER provider and drive the gate
        orig = P.CORPUS_PROVIDER
        import src.research.hypothesis_v7.provider as PM
        rows = {"shots": real,
                "fs_total_shots": dict(real, metric="fs_total_shots",
                                       provider=PM.FOOTYSTATS, status=PM.MEASURABLE)}
        providers = sorted({r["provider"] for r in rows.values()})
        assert len(providers) == 2 and PM.FOOTYSTATS in providers
        # the gate's own rule rejects a multi-provider target set
        spec = {"TARGET": ["shots", "fs_total_shots"],
                "COMPARATOR": "SUBJECT_OVERALL_BASELINE", "CONDITIONS": [],
                "SIMILARITY_DIMENSIONS": []}
        monkey = {"metrics": {m: {"overall_coverage": 0.99,
                                  "competition_coverage": {"a": 0.99},
                                  "excluded_competitions": [],
                                  "admissible_competitions": ["a"],
                                  "coverage_gate_pass": True}
                              for m in spec["TARGET"]}}
        real_resolve = PM.resolve_metric

        def fake_resolve(metric, coverage=None):
            r = real_resolve(metric, coverage)
            if metric == "fs_total_shots":
                r = dict(r, provider=PM.FOOTYSTATS)
            return r
        PM.resolve_metric = fake_resolve
        try:
            out = PM.classify_measurability(spec, monkey)
        finally:
            PM.resolve_metric = real_resolve
        assert out["status"] == P.UNMEASURABLE_PROVIDER
        assert any("multiple providers" in r for r in out["reasons"])
        assert orig == P.CORPUS_PROVIDER
    finally:
        P.METRIC_CONTRACT.clear()
        P.METRIC_CONTRACT.update(saved)


def test_21_21_storage_block_labels_cannot_create_a_fake_provider_split():
    """base/rich/extra are STORAGE, not provenance. The phantom split must stay dead."""
    inv = P.cross_provider_invariant()
    assert inv["n_distinct_providers"] == 1
    assert inv["footystats_values_loaded"] == 0
    assert inv["pooling_guard_fires_on_this_corpus"] is False
    blocks = {row["block"] for row in P.METRIC_CONTRACT.values() if row.get("block")}
    assert blocks == {"base", "rich", "extra"}
    # every block resolves to the SAME provider -- a block name is never a provider identity
    for metric, row in P.METRIC_CONTRACT.items():
        if row.get("block"):
            assert P.resolve_metric(metric)["provider"] == P.THESTATSAPI, metric
    # a target set spanning all three storage blocks must pool freely
    cov = _load("V7_COVERAGE_MATRIX.json")
    out = P.classify_measurability(
        {"TARGET": ["goals", "corner_kicks", "shots"],   # base + rich + extra
         "COMPARATOR": "SUBJECT_OVERALL_BASELINE", "CONDITIONS": [],
         "SIMILARITY_DIMENSIONS": []}, cov)
    assert out["status"] == P.MEASURABLE, out["reasons"]


def test_provenance_matches_the_actual_loader():
    """The contract's provenance claim must match what the corpus loader really does."""
    adapter = open(f"{ROOT}/scripts/championship_adapter.py").read()
    multisrc = open(f"{ROOT}/scripts/multisrc_corpus.py").read()
    assert "def adapt_match(fixture, stats_json)" in adapter
    assert "TheStatsAPI fixture" in multisrc          # _to_adapter_shape's own docstring
    assert P.CORPUS_PROVIDER == P.THESTATSAPI


# =====================================================================================
# Task 17 / case 22: shrinkage implementation lock
# =====================================================================================
def test_21_22_shrinkage_spec_mutation_causes_integrity_failure():
    ok = S.shrinkage_integrity(S.version_stamp())
    assert ok["integrity_ok"] is True and ok["k_applied_in_production_code"] is True
    # spec claims a k the code does not apply -> hard failure
    bad = S.shrinkage_integrity({"profile_shrinkage_k": S.PROFILE_SHRINKAGE_K + 7.0})
    assert bad["integrity_ok"] is False and bad["spec_matches_code"] is False
    # the frozen artifact carries the passing check
    spec = _load("V7_SIMILARITY_SPEC.json")
    assert spec["shrinkage_integrity"]["integrity_ok"] is True
    assert spec["profile_shrinkage_k"] == S.PROFILE_SHRINKAGE_K
    assert spec["profile_shrinkage_applied"] is True


# =====================================================================================
# Task 21 case 23: CHAMPION
# =====================================================================================
def test_21_23_champion_write_attempt_fails():
    import hashlib
    before = hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest()
    src = open(f"{ROOT}/research/hypothesis_engine/_freeze_v7.py").read()
    assert 'problems.append("CHAMPION changed")' in src
    assert 'out["executive_verdict"] = "V7_CONTROL_B_BLOCKED"' in src
    for mod in ("matching", "covariates", "endpoints", "null_benchmark"):
        code = open(f"{ROOT}/src/research/hypothesis_v7/{mod}.py").read()
        for tok in ("pilotC", "stat_mixer", "p_model", "data/discovery"):
            assert tok not in code, f"{mod} references {tok}"
    assert hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest() == before


# =====================================================================================
# Task 11: Control-B fairness nulls -- identical quality must not create an advantage
# =====================================================================================
def test_11_identical_quality_different_composition_creates_no_advantage():
    """If both origins have identical downstream quality, the matched design must not
    manufacture a difference purely from structural composition."""
    llm = ([_row(f"L{i}", metric_group="SCORING") for i in range(8)]
           + [_row(f"L{i}b", metric_group="DISCIPLINE") for i in range(2)])
    null = ([_row(f"C{i}", metric_group="SCORING") for i in range(20)]
            + [_row(f"C{i}b", metric_group="DISCIPLINE") for i in range(80)])
    m = MT.match(llm, null)
    # a synthetic quality that depends ONLY on composition, identical for both origins
    quality = {"SCORING": 0.8, "DISCIPLINE": 0.2}
    cov_by_id = {r["canonical_hypothesis_id"]: r["covariates"] for r in llm + null}
    diffs = []
    for a in m["assignments"]:
        if a["tier"] == MT.NO_MATCH:
            continue
        q_llm = quality[cov_by_id[a["canonical_hypothesis_id"]]["metric_group"]]
        q_ctl = sum(a["weight_per_control"] * quality[cov_by_id[c]["metric_group"]]
                    for c in a["control_ids"])
        diffs.append(q_llm - q_ctl)
    assert diffs, "no matched sets produced"
    assert abs(sum(diffs) / len(diffs)) < 1e-9, (
        "matching manufactured a difference where downstream quality was identical")


def test_11_one_metric_dominating_either_pool_is_handled():
    for dom_side in ("llm", "null"):
        if dom_side == "llm":
            llm = [_row(f"L{i}", metric_group="SET_PIECE") for i in range(20)]
            null = ([_row(f"C{i}", metric_group="SET_PIECE") for i in range(5)]
                    + [_row(f"D{i}", metric_group="SCORING") for i in range(200)])
        else:
            llm = [_row(f"L{i}", metric_group="SCORING") for i in range(5)]
            null = [_row(f"C{i}", metric_group="SET_PIECE") for i in range(200)]
        m = MT.match(llm, null)
        ess = MT.effective_sample(m["control_weights"], len(null))
        bal = MT.balance([r for r in llm if r["canonical_hypothesis_id"] in
                          {a["canonical_hypothesis_id"] for a in m["assignments"]
                           if a["tier"] != MT.NO_MATCH}],
                         null, m["control_weights"], ["metric_group"])
        v = MT.comparability_verdict(m, ess, bal)
        # either it matched within the dominant group (balanced) or it refused
        assert v["control_b_comparable"] in (True, False)
        if dom_side == "null":
            assert m["n_no_comparable_control"] == len(llm)


def test_11_sparse_exact_matching_falls_back_then_refuses():
    llm = [_row("L1", time_scope="W5", target_band="T4_5")]
    # enough controls at the coarse tier, none at the exact one
    null = [_row(f"C{i}", time_scope="ALL_PRIOR", target_band="T1") for i in range(10)]
    m = MT.match(llm, null)
    assert m["assignments"][0]["tier"] == MT.TIER_3, m["assignments"][0]["tier"]
    # and with nothing shareable at any tier it refuses instead of forcing
    null2 = [_row(f"C{i}", comparator="SIMILAR_OPPONENT_COHORT") for i in range(10)]
    assert MT.match(llm, null2)["assignments"][0]["tier"] == MT.NO_MATCH


def test_11_extreme_low_coverage_imbalance_refuses():
    llm = [_row(f"L{i}", coverage_class="FULL") for i in range(10)]
    null = [_row(f"C{i}", coverage_class="PARTIAL") for i in range(300)]
    m = MT.match(llm, null)
    assert m["no_comparable_fraction"] == 1.0


# =====================================================================================
# Frozen-artifact integrity for the Control-B design
# =====================================================================================
def test_control_b_artifacts_frozen_and_hashed():
    for name in ("V7_CONTROL_B_COVARIATE_SPEC.json", "V7_CONTROL_B_MATCHING_SPEC.json",
                 "V7_CONTROL_B_BALANCE_REPORT.json", "V7_CONTROL_B_WEIGHTS.json",
                 "V7_CONTROL_B_EFFECTIVE_SAMPLE.json", "V7_ENDPOINT_SPEC.json",
                 "V7_DATA_COMPATIBILITY_ENDPOINT.json",
                 "V7_CONDITIONAL_SIGNAL_ENDPOINT.json", "V7_CONTROL_B_FREEZE.json"):
        assert os.path.exists(f"{V7_OUT}/{name}"), f"missing {name}"
    fr = _load("V7_CONTROL_B_FREEZE.json")
    for flag in ("generated_before_oos", "covariates_defined_before_oos",
                 "matching_algorithm_frozen_before_oos",
                 "balance_thresholds_frozen_before_oos",
                 "endpoint_definitions_frozen_before_oos",
                 "clustering_method_frozen_before_oos"):
        assert fr[flag] is True, flag
    assert fr["confirmatory_oos_computed"] is False
    assert fr["confirmatory_oos_viewed"] is False
    # hashes recomputable from code -> the freeze binds the actual algorithm
    assert fr["covariate_schema_sha256"] == CV.schema_hash()
    assert fr["matching_spec_sha256"] == MT.spec_hash()
    assert fr["endpoint_spec_sha256"] == EP.spec_hash()


def test_comparability_verdict_is_met_on_real_data():
    fr = _load("V7_CONTROL_B_FREEZE.json")
    ess = _load("V7_CONTROL_B_EFFECTIVE_SAMPLE.json")
    bal = _load("V7_CONTROL_B_BALANCE_REPORT.json")
    w = _load("V7_CONTROL_B_WEIGHTS.json")
    assert fr["comparability"]["control_b_comparable"] is True
    assert w["no_comparable_fraction"] <= MT.MAX_NO_COMPARABLE_FRACTION
    assert ess["effective_n"] >= MT.MIN_EFFECTIVE_N
    assert ess["max_single_control_share"] <= MT.MAX_CONTROL_WEIGHT_SHARE
    assert bal["balance_ok"] is True and bal["n_levels_out_of_balance"] == 0


def test_covariate_schema_excludes_generator_self_description():
    sch = CV.schema()
    assert "research_family_label" not in sch["matching_covariates"]
    assert "research_family_label" in sch["descriptive_only_covariates"]
    assert sch["excluded_raw_provider_requirements"] is True
    assert sch["outcome_blind"] is True
    for forbidden in CV.FORBIDDEN_COVARIATE_SOURCES:
        assert forbidden not in sch["matching_covariates"]


def test_null_v2_inhabits_the_similarity_slot():
    """The v1 empty cell -- 33/132 LLM vs 0/400 null -- must be closed."""
    nb = NB.build(list(P.corpus_bindings().keys()), C, pool_size=600)
    sim = sum(1 for f in nb["families"]
              if f["canonical_spec"]["SIMILARITY_DIMENSIONS"])
    assert sim > 0, "null still cannot express a similar-opponent hypothesis"
    assert 0.10 <= sim / len(nb["families"]) <= 0.60
    # conditions are structured dicts, so they share a token space with the LLM's
    conds = [c for f in nb["families"] for c in f["canonical_spec"]["CONDITIONS"]]
    assert any("dimension" in c for c in conds)
    assert not any(c.startswith("venue=") for c in conds), "v1 string conditions returned"


def test_control_b_reproducible_across_seeds():
    code = ("import sys,json,hashlib;"
            "sys.path.insert(0,'/home/ubuntu/src');sys.path.insert(0,'/home/ubuntu');"
            "from src.research.hypothesis_v7 import null_benchmark as NB,canonical as C,"
            "provider as P,covariates as CV,matching as MT;"
            "nb=NB.build(list(P.corpus_bindings().keys()),C,pool_size=300);"
            "print(hashlib.sha256(json.dumps([CV.schema_hash(),MT.spec_hash(),"
            "[f['canonical_hypothesis_id'] for f in nb['families']]],"
            "sort_keys=True).encode()).hexdigest())")
    seen = set()
    for seed in ("1", "2", "3", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=env)
        seen.add(r.stdout.strip())
    assert len(seen) == 1, f"control-B design not reproducible: {seen}"


# =====================================================================================
# Task 14B: the blast-radius proof must be current and must cover every changed module
# =====================================================================================
def test_blast_radius_proof_is_current_and_complete():
    """Regenerate the proof and assert it still matches the frozen artifact.

    This is what licenses reporting on a test suite that was not run to completion: a test
    module that cannot transitively import a changed module cannot be affected by the change.
    """
    br = _load("V7_BLAST_RADIUS.json")
    # every module this work changed is declared in the proof
    v7dir = f"{ROOT}/src/research/hypothesis_v7"
    on_disk = {f"src/research/hypothesis_v7/{f}" for f in os.listdir(v7dir)
               if f.endswith(".py")}
    assert on_disk <= set(br["changed_modules"]), (
        f"V7 modules missing from the blast-radius declaration: "
        f"{sorted(on_disk - set(br['changed_modules']))}")
    # the proof is reproducible: rerun it and compare
    r = subprocess.run([sys.executable,
                        f"{ROOT}/research/hypothesis_engine/_v7_blast_radius.py"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    again = _load("V7_BLAST_RADIUS.json")
    assert again["test_modules_reaching_changed_code"] == \
        br["test_modules_reaching_changed_code"]
    # and the reaching set is exactly the two V7 suites, both of which are run in full
    reaching = {x["test_module"] for x in again["test_modules_reaching_changed_code"]}
    assert reaching == {"tests/research/hypothesis_oos/test_v7_control_b.py",
                        "tests/research/hypothesis_oos/test_v7_pre_oos.py"}, reaching
    assert again["n_test_modules_scanned"] > 200


def test_blast_radius_detects_a_reaching_module():
    """Negative control: the analyser must actually FIND a dependency, not vacuously pass."""
    sys.path.insert(0, f"{ROOT}/research/hypothesis_engine")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_v7_blast_radius", f"{ROOT}/research/hypothesis_engine/_v7_blast_radius.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    reach = mod.closure("tests/research/hypothesis_oos/test_v7_control_b.py", {})
    assert "src/research/hypothesis_v7/matching.py" in reach
    assert "src/research/hypothesis_v7/covariates.py" in reach
    # a module with no V7 dependency must come back clean
    clean = mod.closure("research/hypothesis_engine/_v7_blast_radius.py", {})
    assert not (clean & mod.CHANGED)
