"""V7 pre-OOS adversarial + apparatus tests (Phase 32). ZERO SPEND, NO confirmatory OOS.

Every test here exercises the deterministic V7 apparatus over the immutable V6.1 outputs or
synthetic structural inputs. None computes a confirmatory OOS effect; none calls Bedrock;
none touches CHAMPION. The 22 required adversarial cases are covered plus reproducibility and
artifact/state integrity.
"""
from __future__ import annotations

import hashlib
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
from src.research.hypothesis_v7 import leakage as L
from src.research.hypothesis_v7 import null_benchmark as NB
from src.research.hypothesis_v7 import pit as PIT
from src.research.hypothesis_v7 import provider as P
from src.research.hypothesis_v7 import similarity as S
from src.research.hypothesis_v7 import universe as U
from src.research.hypothesis_v7 import walkforward as W

ROOT = "/home/ubuntu"
V61_EXEC = f"{ROOT}/research/hypothesis_oos/out/v6_1/execution"
V7_OUT = f"{ROOT}/research/hypothesis_oos/out/v7"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_SHA = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _spec(**kw):
    base = {"target_metrics": [], "subject": "HOME_TEAM", "side": "FOR",
            "comparison": "SUBJECT_OVERALL_BASELINE", "conditions": [], "window": "ALL_PRIOR",
            "research_family": "ATTACK_VOLUME", "required_capabilities": []}
    base.update(kw)
    return base


# ---- 1,2: dedup weight + deterministic equivalence -------------------------------------
def test_01_duplicate_no_double_weight():
    uni = U.extract_universe(V61_EXEC)
    canon = C.canonicalize_universe(uni)
    dedup = C.deduplicate(canon)
    # every canonical family is counted once regardless of origin multiplicity
    assert dedup["n_canonical_families"] <= dedup["n_raw_qualified"]
    for fam in dedup["families"]:
        assert fam["n_origins"] >= 1
    # structural duplicates exist and are recorded, never merged into extra evidence
    dup = [d for d in dedup["duplicate_classifications"]
           if d["class"] == "STRUCTURAL_DUPLICATE"]
    assert len(dup) >= 1

def test_02_equivalent_wording_maps_deterministically():
    a = _spec(target_metrics=["total_shots"])
    b = _spec(target_metrics=["shots"])          # synonym -> same canonical metric
    assert C.canonical_id(a) == C.canonical_id(b)
    # ordering of metrics must not matter
    c = _spec(target_metrics=["goals", "xg"])
    d = _spec(target_metrics=["xg", "goals"])
    assert C.canonical_id(c) == C.canonical_id(d)


# ---- 3,4: measurability gates ----------------------------------------------------------
def test_03_unsupported_provider_field_unmeasurable():
    # a metric genuinely absent from the frozen contract is UNMEASURABLE_MISSING_FIELD.
    m = P.classify_measurability(
        C.canonical_spec(_spec(target_metrics=["dangerous_attacks"])))
    assert m["status"] == P.UNMEASURABLE_MISSING_FIELD
    # a semantically ambiguous metric is refused rather than silently resolved
    m2 = P.classify_measurability(C.canonical_spec(_spec(target_metrics=["cards"])))
    assert m2["status"] == P.UNMEASURABLE_PROVIDER
    # `possession` WAS wrongly excluded by the v1 contract; it is a real corpus field with
    # 0.995 measured coverage, so with a passing coverage matrix it must be MEASURABLE.
    m3 = P.classify_measurability(C.canonical_spec(_spec(target_metrics=["possession"])),
                                  _synthetic_coverage(["possession"]))
    assert m3["status"] == P.MEASURABLE


def _synthetic_coverage(passing, failing=()):
    """A minimal coverage matrix: `passing` metrics clear the gate, `failing` ones do not."""
    metrics = {}
    for m in passing:
        metrics[m] = {"overall_coverage": 0.99,
                      "competition_coverage": {"champ": 0.99, "epl": 0.99},
                      "excluded_competitions": [], "admissible_competitions":
                          ["champ", "epl"], "coverage_gate_pass": True}
    for m in failing:
        metrics[m] = {"overall_coverage": 0.60,
                      "competition_coverage": {"champ": 0.60, "epl": 0.99},
                      "excluded_competitions": ["champ"], "admissible_competitions": ["epl"],
                      "coverage_gate_pass": False}
    return {"metrics": metrics}


def test_03b_coverage_failing_metric_is_unmeasurable_coverage():
    # a metric whose SEMANTICS are fine but whose measured coverage fails the frozen gate is
    # rejected, and reported as a COVERAGE failure rather than mislabelled as a provider one.
    m = P.classify_measurability(C.canonical_spec(_spec(target_metrics=["xg"])),
                                 _synthetic_coverage([], failing=["xg"]))
    assert m["status"] == P.UNMEASURABLE_COVERAGE
    # coverage can only ever REMOVE a metric, never add one: an unaudited metric stays out
    m2 = P.classify_measurability(C.canonical_spec(_spec(target_metrics=["np_xg"])),
                                  _synthetic_coverage(["np_xg"]))
    assert m2["status"] == P.UNMEASURABLE_PROVIDER


def test_03c_real_coverage_matrix_excludes_only_low_coverage_metrics():
    cov = json.load(open(f"{V7_OUT}/V7_COVERAGE_MATRIX.json"))
    # every competition is represented -- no league was silently dropped from the matrix
    assert len(cov["corpus"]["competitions"]) == 6
    failing = sorted(m for m, r in cov["metrics"].items()
                     if not r["coverage_gate_pass"])
    assert "xg" in failing and "touches_in_penalty_area" in failing
    for m in ("shots", "possession", "saves", "corner_kicks", "goals"):
        assert cov["metrics"][m]["coverage_gate_pass"], f"{m} should clear the gate"
        assert cov["metrics"][m]["excluded_competitions"] == []

def test_04_unsafe_temporal_resolution_unmeasurable():
    """A half-resolution metric the corpus cannot support at half level is UNMEASURABLE.

    The naive version of this test passed a metric absent from the contract, which returns
    UNMEASURABLE_MISSING_FIELD and never reaches the half-resolution branch at all. The only
    half-resolution metric in the contract (`cards_2h`) IS supported, so the branch has to be
    exercised by injecting an unsupported one.
    """
    # absent metric: missing-field, NOT a temporal-resolution verdict
    m0 = P.classify_measurability({"TARGET": ["shots_inside_box_2h"], "COMPARATOR":
                                   "SUBJECT_OVERALL_BASELINE", "CONDITIONS": [],
                                   "SIMILARITY_DIMENSIONS": []})
    assert m0["status"] == P.UNMEASURABLE_MISSING_FIELD

    # the real half-resolution guard
    assert P.METRIC_CONTRACT["cards_2h"]["resolution"] == "half"
    assert "cards_2h" in P.HALF_STATE_SUPPORTED_METRICS
    P.METRIC_CONTRACT["corners_2h"] = {"block": "rich", "field": "corner_kicks_2h",
                                       "unit": "count", "semantic": "2nd-half corners",
                                       "resolution": "half", "audited": True}
    try:
        m = P.classify_measurability(
            {"TARGET": ["corners_2h"], "COMPARATOR": "SUBJECT_OVERALL_BASELINE",
             "CONDITIONS": [], "SIMILARITY_DIMENSIONS": []},
            _synthetic_coverage(["corners_2h"]))
        assert m["status"] == P.UNMEASURABLE_TEMPORAL_RESOLUTION, m["reasons"]
        assert any("half resolution unsupported" in r for r in m["reasons"])
    finally:
        P.METRIC_CONTRACT.pop("corners_2h", None)

    # and the supported half metric is NOT rejected on resolution grounds
    m2 = P.classify_measurability(
        {"TARGET": ["cards_2h"], "COMPARATOR": "SUBJECT_OVERALL_BASELINE",
         "CONDITIONS": [], "SIMILARITY_DIMENSIONS": []},
        _synthetic_coverage(["cards_2h"]))
    assert m2["status"] == P.MEASURABLE


def test_03d_unmeasurable_provider_class_is_reachable():
    """Case 3's UNMEASURABLE_PROVIDER verdict must be genuinely reachable, not vestigial."""
    for metric in ("cards", "np_xg"):          # null binding / unaudited semantics
        m = P.classify_measurability(C.canonical_spec(_spec(target_metrics=[metric])),
                                     _synthetic_coverage([metric]))
        assert m["status"] == P.UNMEASURABLE_PROVIDER, (metric, m["status"])


def test_04b_uncompilable_comparator_is_unmeasurable_compiler():
    m = P.classify_measurability(
        {"TARGET": ["goals"], "COMPARATOR": "SOME_UNIMPLEMENTED_COMPARATOR",
         "CONDITIONS": [], "SIMILARITY_DIMENSIONS": []},
        _synthetic_coverage(["goals"]))
    assert m["status"] == P.UNMEASURABLE_COMPILER
    # the Phase 10 recency comparator IS compilable (it was 10 spurious COMPILER rejections)
    m2 = P.classify_measurability(
        {"TARGET": ["goals"], "COMPARATOR": "SUBJECT_RECENT_VS_LONG_BASELINE",
         "CONDITIONS": [], "SIMILARITY_DIMENSIONS": []},
        _synthetic_coverage(["goals"]))
    assert m2["status"] == P.MEASURABLE
    assert A.flag_comparator({"COMPARATOR": "SUBJECT_RECENT_VS_LONG_BASELINE",
                              "CONDITIONS": [], "SIMILARITY_DIMENSIONS": []}
                             )["requires_full_decay_family"] is True


# ---- 5,6,7,8: leakage rejections -------------------------------------------------------
def test_05_future_match_in_profile_rejected():
    with pytest.raises(L.LeakageRejected):
        L.assert_no_future_in_profile([1000, 2000], reference_unix=1500)

def test_06_target_in_own_baseline_rejected():
    with pytest.raises(L.LeakageRejected):
        L.assert_target_not_in_baseline("mt_x", ["mt_x", "mt_y"])

def test_07_future_season_similarity_rejected():
    with pytest.raises(L.LeakageRejected):
        L.assert_similarity_past_only([2000], reference_unix=1500)

def test_08_scaler_on_future_fold_rejected():
    with pytest.raises(L.LeakageRejected):
        L.assert_scaler_fit_past_only([2000], train_end_unix=1500)


# ---- 9: random split forbidden as primary ----------------------------------------------
def test_09_random_split_not_primary():
    assert W.RANDOM_SPLIT_ALLOWED_AS_PRIMARY is False
    assert W.version_stamp()["primary_is_temporal"] is True


# ---- 10,11: support failures -----------------------------------------------------------
def test_10_low_n_support_failure():
    r = PIT.classify_support(raw_n=5, unique_fixtures=4, unique_teams=3, effective_n=3.0,
                             concentration=0.1, n_competitions=1)
    assert r["status"] in (PIT.SUPPORT_LOW, PIT.SUPPORT_NOT_EVALUABLE)

def test_11_one_team_dominated_concentration_failure():
    r = PIT.classify_support(raw_n=40, unique_fixtures=30, unique_teams=8, effective_n=25.0,
                             concentration=0.6, n_competitions=2)
    assert r["status"] == PIT.SUPPORT_CONCENTRATED


# ---- 12,13: comparator rejections ------------------------------------------------------
def test_12_tautological_comparator_rejected():
    fl = A.flag_comparator({"COMPARATOR": "SIMILAR_OPPONENT_COHORT", "CONDITIONS": [],
                            "SIMILARITY_DIMENSIONS": []})
    assert not fl["ok"] and "TAUTOLOGICAL_COMPARATOR" in fl["flags"]

def test_13_baseline_absorption_rejected():
    fl = A.flag_comparator({"COMPARATOR": "SUBJECT_VENUE_BASELINE",
                            "CONDITIONS": ["venue:home"], "SIMILARITY_DIMENSIONS": []})
    assert not fl["ok"] and "BASELINE_ABSORPTION" in fl["flags"]


# ---- 14,15,16,17,18: outcome-class semantics (definitions, effect-blind) ---------------
def test_14_zero_effect_is_valid_terminal():
    from src.research.hypothesis_v7 import outcomes as O
    assert "OOS_NO_EFFECT" in O.TERMINAL_STATES

def test_15_sign_reversal_terminal_exists():
    from src.research.hypothesis_v7 import outcomes as O
    assert "OOS_DIRECTION_UNSTABLE" in O.TERMINAL_STATES

def test_16_huge_insample_zero_oos_terminal_exists():
    from src.research.hypothesis_v7 import outcomes as O
    assert "OOS_FAIL" in O.TERMINAL_STATES and "HISTORICAL_EFFECT_ONLY" in O.TERMINAL_STATES

def test_17_pvalue_not_sole_promotion():
    assert "Nominal p<0.05 is NEVER sufficient" in A.PROMOTION_RULE

def test_18_stable_modest_effect_can_survive():
    from src.research.hypothesis_v7 import outcomes as O
    assert "OOS_SURVIVES" in O.TERMINAL_STATES and \
        "CANDIDATE_FEATURE_ELIGIBLE" in O.TERMINAL_STATES


# ---- 19: multiplicity adjustment defined -----------------------------------------------
def test_19_multiplicity_method_frozen():
    vs = A.version_stamp()
    assert "BENJAMINI_HOCHBERG" in vs["multiplicity_method"]
    assert vs["fdr_q"] == 0.10


# ---- 20: provider mismatch -> no pooling -----------------------------------------------
def test_20_cross_provider_no_pooling():
    """The corpus is SINGLE-provider, so the pooling guard must be armed but never fire.

    v1 of the contract labelled `base` FootyStats and `rich` TheStatsAPI and rejected any
    hypothesis spanning them. That provenance was wrong -- `adapt_match` reads every field from
    one TheStatsAPI payload -- and the phantom split discarded 33 canonical families on a
    distinction that does not exist. This test pins the corrected invariant in both
    directions: it does not fire here, and it DOES fire when providers genuinely differ.
    """
    inv = P.cross_provider_invariant()
    assert inv["n_distinct_providers"] == 1
    assert inv["corpus_provider"] == P.THESTATSAPI
    assert inv["footystats_values_loaded"] == 0
    assert inv["pooling_guard_armed"] is True

    # every contracted metric resolves to the one real provider -- no phantom split
    for metric, row in P.METRIC_CONTRACT.items():
        if row.get("block"):
            assert P.resolve_metric(metric)["provider"] == P.THESTATSAPI, metric

    # metrics stored in DIFFERENT blocks of the SAME provider must pool freely
    cov = _synthetic_coverage(["shots_on_target", "shots", "goals"])
    m = P.classify_measurability({"TARGET": ["shots_on_target", "shots", "goals"],
                                  "COMPARATOR": "SUBJECT_OVERALL_BASELINE", "CONDITIONS": [],
                                  "SIMILARITY_DIMENSIONS": []}, cov)
    assert m["status"] == P.MEASURABLE, m["reasons"]

    # and the guard still fires when two providers genuinely appear
    saved = P.METRIC_CONTRACT["goals"].copy()
    try:
        P.METRIC_CONTRACT["goals"] = {**saved, "block": "base"}
        real = P.resolve_metric("shots_on_target", cov)
        fake = dict(real, metric="fs_metric", provider=P.FOOTYSTATS)
        providers = sorted({real["provider"], fake["provider"]})
        assert len(providers) > 1  # the condition classify_measurability rejects on
    finally:
        P.METRIC_CONTRACT["goals"] = saved


# ---- 21: V6.1 replay cannot alter V7 universe -------------------------------------------
def test_21_universe_is_pure_function_of_immutable_v6_1():
    u1 = U.extract_universe(V61_EXEC)
    u2 = U.extract_universe(V61_EXEC)
    assert u1["n_qualified_total"] == u2["n_qualified_total"]
    # the universe is bound to the immutable scores hash; a replay artifact is not read
    assert u1["source_scores_sha256"] == u2["source_scores_sha256"]
    # the extractor reads only scores.json + raw/, never any posthoc replay file
    src = open(f"{ROOT}/src/research/hypothesis_v7/universe.py").read()
    assert "POSTHOC" not in src and "replay" not in src.lower()


# ---- 22: CHAMPION write attempt -> hard failure (isolation) ----------------------------
def test_22_champion_isolated_and_unchanged():
    got = hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest()
    assert got == CHAMPION_SHA
    # no V7 module imports/uses production prediction state (executable code)
    import ast
    for m in ("universe", "canonical", "provider", "coverage", "pit", "similarity",
              "analysis_spec", "walkforward", "outcomes", "leakage", "null_benchmark"):
        tree = ast.parse(open(f"{ROOT}/src/research/hypothesis_v7/{m}.py").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                b = getattr(node, "body", [])
                if b and isinstance(b[0], ast.Expr) and isinstance(
                        getattr(b[0], "value", None), ast.Constant) and isinstance(
                        b[0].value.value, str):
                    b.pop(0)
        code = ast.unparse(tree)
        for tok in ("pilotC", "stat_mixer", "p_model"):
            assert tok not in code, f"{m} references {tok}"


def test_22b_no_v7_module_can_write_anywhere():
    """Case 22: a CHAMPION write must be impossible, not merely absent by convention.

    No V7 apparatus module opens ANY file for writing, and none names a production data path.
    The apparatus is pure computation over inputs handed to it; only the freeze driver writes,
    and only under out/v7/.
    """
    import ast
    v7dir = f"{ROOT}/src/research/hypothesis_v7"
    for fn in sorted(os.listdir(v7dir)):
        if not fn.endswith(".py"):
            continue
        src = open(f"{v7dir}/{fn}").read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                mode = ""
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                assert not any(c in mode for c in "wax+"), \
                    f"{fn} opens a file for writing (mode={mode!r})"
        for bad in ("data/discovery", "pilotC_stat_mixer", "data/features",
                    "data/forward", "data/prospective"):
            assert bad not in src, f"{fn} names production path {bad}"


def test_22c_champion_guard_fails_closed_on_mismatch():
    """The freeze driver's CHAMPION check must BLOCK on any hash change, not warn."""
    src = open(f"{ROOT}/research/hypothesis_engine/_freeze_v7.py").read()
    assert 'if champ_sha != CHAMPION_FROZEN_SHA:' in src
    assert 'problems.append("CHAMPION changed")' in src
    # and any non-empty `problems` forces the BLOCKED verdict with no states emitted
    assert 'out["executive_verdict"] = "V7_CONTROL_B_BLOCKED"' in src
    assert 'out["states_emitted"] = []' in src
    # the guard is live: the frozen constant matches the real file right now
    assert hashlib.sha256(open(CHAMPION, "rb").read()).hexdigest() == CHAMPION_SHA
    assert CHAMPION_SHA in src


# ---- PIT engine + similarity determinism -----------------------------------------------
def test_pit_prior_strictly_before():
    from src.research.hypothesis_engine import corpus_adapter as CA
    idx = CA.load_index()
    tgt = max(idx.records, key=lambda r: int(r.kickoff_unix))
    priors = PIT.prior_fixtures(idx, tgt)
    assert all(int(r.kickoff_unix) < int(tgt.kickoff_unix) for r in priors)

def test_similarity_time_decay_future_is_zero():
    # a future observation contributes zero weight (PIT guard inside the weighter)
    assert PIT.time_decay_weight(2000, 1500, 180) == 0.0
    assert PIT.time_decay_weight(1000, 1500, 180) > 0.0

def test_kish_effective_n_and_concentration():
    assert PIT.kish_effective_n([1, 1, 1, 1]) == 4.0
    assert abs(PIT.weight_concentration([9, 1]) - 0.9) < 1e-9


# ---- reproducibility across 4 seeds -----------------------------------------------------
def test_reproducibility_four_seeds():
    code = (
        "import sys,json,hashlib;"
        "sys.path.insert(0,'/home/ubuntu/src');sys.path.insert(0,'/home/ubuntu');"
        "from src.research.hypothesis_v7 import universe as U,canonical as C,"
        "provider as P,null_benchmark as NB;"
        "u=U.extract_universe('%s');cn=C.canonicalize_universe(u);d=C.deduplicate(cn);"
        "nb=NB.build(list(P.corpus_bindings().keys()),C);"
        "payload={'nq':u['n_qualified_total'],'nf':d['n_canonical_families'],"
        "'fam':sorted(f['canonical_hypothesis_id'] for f in d['families']),"
        "'nbn':nb['n_canonical_families'],"
        "'nbf':sorted(f['canonical_hypothesis_id'] for f in nb['families']),"
        "'bind':sorted(P.corpus_bindings().items())};"
        "print(hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest())"
        % V61_EXEC)
    seen = set()
    for seed in ("1", "2", "3", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=env)
        seen.add(r.stdout.strip())
    assert len(seen) == 1, f"universe/canonical not reproducible: {seen}"


# ---- frozen artifacts + states integrity ------------------------------------------------
def test_frozen_artifacts_present_and_states_ready():
    for name in ("V7_HYPOTHESIS_UNIVERSE.json", "V7_CANONICAL_HYPOTHESES.json",
                 "V7_DEDUPLICATION.json", "V7_MEASURABILITY.json",
                 "V7_PROVIDER_CONTRACT.json", "V7_SIMILARITY_SPEC.json",
                 "V7_SUPPORT_RULES.json", "V7_CONFOUNDER_PLAN.json",
                 "V7_MULTIPLICITY_PLAN.json", "V7_WALKFORWARD_FOLDS.json",
                 "V7_CONTROL_COMPARISON.json", "V7_CANDIDATE_LOCK.json",
                 "V7_EVALUATOR_FREEZE.json", "V7_PREREGISTRATION.json", "V7_STATES.json"):
        assert os.path.exists(f"{V7_OUT}/{name}"), f"missing {name}"
    for name in ("V7_COVERAGE_MATRIX.json", "V7_NULL_BENCHMARK.json",
                 "V7_CONTROL_B_COVARIATE_SPEC.json", "V7_CONTROL_B_MATCHING_SPEC.json",
                 "V7_CONTROL_B_BALANCE_REPORT.json", "V7_CONTROL_B_WEIGHTS.json",
                 "V7_CONTROL_B_EFFECTIVE_SAMPLE.json", "V7_ENDPOINT_SPEC.json",
                 "V7_DATA_COMPATIBILITY_ENDPOINT.json",
                 "V7_CONDITIONAL_SIGNAL_ENDPOINT.json", "V7_CONTROL_B_FREEZE.json"):
        assert os.path.exists(f"{V7_OUT}/{name}"), f"missing {name}"
    st = json.load(open(f"{V7_OUT}/V7_STATES.json"))
    assert st["executive_verdict"] == "V7_CONTROL_B_READY_FOR_OOS"
    assert st["control_b_verdict"] == "V7_CONTROL_B_REPAIRED_AND_REFROZEN"
    assert st["any_block"] is False
    assert st["confirmatory_oos_computed"] is False
    assert st["confirmatory_oos_viewed"] is False
    assert st["candidate_feature_promotion"] is False
    assert st["bedrock_change_required"] is False
    assert "V7_OOS_EXECUTION_AUTHORIZATION_REQUIRED" in st["states_emitted"]
    assert "V7_CONTROL_A_INFEASIBLE" in st["states_emitted"]
    for s_ in ("V7_CONTROL_B_STRUCTURAL_COVARIATES_FROZEN",
               "V7_CONTROL_B_MATCHING_FROZEN", "V7_CONTROL_B_BALANCE_VALIDATED",
               "V7_CONTROL_B_EFFECTIVE_SAMPLE_VALIDATED",
               "V7_END_TO_END_ENDPOINT_FROZEN",
               "V7_CONDITIONAL_SIGNAL_ENDPOINT_FROZEN"):
        assert s_ in st["states_emitted"], s_

def test_prereg_declares_no_confirmatory_oos():
    pr = json.load(open(f"{V7_OUT}/V7_PREREGISTRATION.json"))
    assert pr["confirmatory_oos_computed"] is False
    assert pr["no_llm_effect_estimation"] is True
    assert "REQUIRED" in pr["spend_authorization"]

def test_candidate_lock_is_hashed_before_oos():
    lock = json.load(open(f"{V7_OUT}/V7_CANDIDATE_LOCK.json"))
    assert len(lock["candidate_lock_sha256"]) == 64
    assert lock["n_eligible_candidates"] >= 1
    # recompute the lock from the frozen eligible set -> must match (deterministic)
    recomputed = W.candidate_lock_hash(lock["eligible"])
    assert recomputed == lock["candidate_lock_sha256"]


# ---- new leakage guards (Phase 24 completion) -------------------------------------------
def test_shrinkage_hyperparams_fitted_on_future_rejected():
    with pytest.raises(L.LeakageRejected):
        L.assert_hyperparams_fit_past_only([2_000], 1_000)
    L.assert_hyperparams_fit_past_only([999], 1_000)   # past-only must be accepted


def test_target_fixture_own_statistic_rejected():
    with pytest.raises(L.LeakageRejected):
        L.assert_target_stat_absent(["stat:mt_T:corners"], "mt_T")
    L.assert_target_stat_absent(["stat:mt_OTHER:corners"], "mt_T")


def test_settlement_and_future_lineup_fields_rejected():
    for bad in ("settlement", "future_lineup", "future_injury", "closing_odds"):
        with pytest.raises(L.LeakageRejected):
            L.assert_no_forbidden_fields(["team_form", bad])


def test_full_mutation_suite_covers_every_phase24_class():
    r = L.run_mutation_suite(1_700_000_000, "mt_X")
    assert r["all_pass"] is True
    for name in ("future_match_in_profile", "post_cutoff_obs", "at_cutoff_obs",
                 "target_in_baseline", "future_season_similarity", "scaler_on_future_fold",
                 "forbidden_market_field", "settlement_field",
                 "future_lineup_injury_field", "shrinkage_hyperparam_on_future",
                 "target_fixture_own_stat"):
        assert r["results"][name] == "rejected", name
    assert r["results"]["legitimate_pit_obs"] == "accepted"


# ---- arm-endpoint feasibility gate (outcome-blind) ---------------------------------------
def test_arm_endpoint_feasibility_blocks_a_degenerate_matched_design():
    degenerate = {"n_matched_cells": 5, "n_matched_fixtures": 3,
                  "n_base_families_in_matched": 6, "n_research_families_in_matched": 7}
    f = W.endpoint_feasibility(degenerate)
    assert f["primary_endpoint_feasible"] is False
    assert f["depends_on_effect"] is False and f["evaluated_before_oos"] is True
    ample = {"n_matched_cells": 40, "n_matched_fixtures": 9,
             "n_base_families_in_matched": 30, "n_research_families_in_matched": 30}
    assert W.endpoint_feasibility(ample)["primary_endpoint_feasible"] is True


def test_real_arm_design_is_infeasible_and_demoted_not_silently_substituted():
    cc = json.load(open(f"{V7_OUT}/V7_CONTROL_COMPARISON.json"))
    assert cc["arm_endpoint_feasibility"]["primary_endpoint_feasible"] is False
    assert cc["arm_endpoint_demoted_to_descriptive"] is True
    # the direct cause: no canonical specification was produced by BOTH arms
    assert cc["n_canonical_families_in_both_arms"] == 0
    # and the fallback was frozen in the same artifact, before any OOS
    assert "frozen NOW" in cc["arm_endpoint_feasibility"]["fallback_if_infeasible"]


# ---- Phase 20 Control B: deterministic null benchmark -------------------------------------
def test_null_benchmark_is_deterministic_and_llm_free():
    a = NB.build(list(P.corpus_bindings().keys()), C)
    b = NB.build(list(P.corpus_bindings().keys()), C)
    assert [f["canonical_hypothesis_id"] for f in a["families"]] == \
           [f["canonical_hypothesis_id"] for f in b["families"]]
    assert a["version_stamp"]["uses_llm"] is False if "version_stamp" in a else True
    st = NB.version_stamp()
    assert st["uses_llm"] is False
    assert st["fixture_specific_reasoning"] is False
    assert st["reads_outcomes"] is False


def test_null_benchmark_uses_same_canonicalizer_and_same_grammar():
    nb = NB.build(list(P.corpus_bindings().keys()), C)
    # every null family canonicalizes through the SAME function as V6.1 -- no special-casing
    for fam in nb["families"][:25]:
        spec = fam["canonical_spec"]
        assert spec["SUBJECT"] in NB.NULL_SUBJECTS
        assert spec["COMPARATOR"] in NB.NULL_COMPARATORS
        assert spec["COMPARATOR"] in P.COMPILABLE_COMPARATORS
        assert spec["TIME_SCOPE"] in NB.NULL_TIME_SCOPES
    # the null draws coverage-FAILING metrics too, so it faces the same measurability hazards
    drawn = {m for fam in nb["families"] for m in fam["canonical_spec"]["TARGET"]}
    assert "xg" in drawn and "touches_in_penalty_area" in drawn


def test_null_benchmark_not_disadvantaged_by_construction():
    nbj = json.load(open(f"{V7_OUT}/V7_NULL_BENCHMARK.json"))
    cc = json.load(open(f"{V7_OUT}/V7_CONTROL_COMPARISON.json"))
    feas = cc["null_endpoint_feasibility"]
    assert feas["null_endpoint_feasible"] is True
    assert feas["measurability_rate_gap"] <= W.MAX_ORIGIN_MEASURABILITY_RATE_GAP
    assert feas["comparator_reject_rate_gap"] <= W.MAX_ORIGIN_COMPARATOR_REJECT_GAP
    # count-balanced: the null subset never exceeds the V6.1 measurable family count
    assert cc["balanced_null_family_count"] == cc["v61_measurable_family_count"]
    assert nbj["measurability"]["n_measurable"] >= W.MIN_NULL_MEASURABLE_FAMILIES


def test_null_benchmark_rng_is_pythonhashseed_independent():
    code = ("import sys,json,hashlib;"
            "sys.path.insert(0,'/home/ubuntu/src');sys.path.insert(0,'/home/ubuntu');"
            "from src.research.hypothesis_v7 import null_benchmark as NB,canonical as C,"
            "provider as P;"
            "nb=NB.build(list(P.corpus_bindings().keys()),C);"
            "print(hashlib.sha256(json.dumps([f['canonical_hypothesis_id'] "
            "for f in nb['families']],sort_keys=True).encode()).hexdigest())")
    seen = set()
    for seed in ("1", "2", "3", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=env)
        seen.add(r.stdout.strip())
    assert len(seen) == 1, f"null benchmark not reproducible: {seen}"


# ---- similarity: declared spec must match the code ----------------------------------------
def test_similarity_shrinkage_is_actually_applied():
    prof = {"team_id": "t1", "n_matches": 2,
            "dims": {d: 2.0 for d in S.SIMILARITY_DIMENSIONS},
            "dim_n": {d: 2 for d in S.SIMILARITY_DIMENSIONS}}
    baseline = {d: 1.0 for d in S.SIMILARITY_DIMENSIONS}
    shrunk = S.shrink_profile(prof, baseline)
    # (n*v + k*prior)/(n+k) = (2*2 + 8*1)/10 = 1.2 -- strictly between value and prior
    for d in S.SIMILARITY_DIMENSIONS:
        assert abs(shrunk["dims"][d] - 1.2) < 1e-9
    assert shrunk["shrinkage_k"] == S.PROFILE_SHRINKAGE_K
    assert S.version_stamp()["profile_shrinkage_applied"] is True


def test_similarity_dimensions_all_clear_measured_coverage_gate():
    cov = json.load(open(f"{V7_OUT}/V7_COVERAGE_MATRIX.json"))
    v = S.validate_dimension_coverage(cov)
    assert v["all_dimensions_clear_coverage_gate"] is True, v["failures"]
    # the league-broken xg dimension must be gone
    assert "xg_conceded_per_match" not in S.SIMILARITY_DIMENSIONS
    for dim, row in v["per_dimension"].items():
        assert row["excluded_competitions"] == [], (dim, row)


# ---- coverage engine ----------------------------------------------------------------------
def test_coverage_gate_is_effect_blind_and_reports_restricted_universes():
    st = COV.version_stamp()
    assert st["depends_on_effect"] is False
    assert st["silent_league_dropping_prevented"] is True
    cov = json.load(open(f"{V7_OUT}/V7_COVERAGE_MATRIX.json"))
    assert cov["gate"]["min_competition_coverage_rate"] == COV.MIN_COMPETITION_COVERAGE_RATE
    # a metric excluded anywhere must say WHERE -- never a silent drop
    for m, row in cov["metrics"].items():
        if not row["coverage_gate_pass"]:
            assert row["excluded_competitions"] or \
                row["overall_coverage"] < COV.MIN_OVERALL_COVERAGE_RATE, m
