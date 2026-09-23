"""ITEM 6 STAGE 2 model arm specifications + multiplicity policy
(`item6_stage2_model_specs_v1`).

M0 = the deterministic baseline feature universe (the champion's stat-mixer pool).
M1 = M0 + the frozen Stage-2-feasible LLM-derived feature universe.

THE ONLY SCIENTIFIC DIFFERENCE BETWEEN THE ARMS IS FEATURE AVAILABILITY.
Everything else is shared by construction: identical fixtures, identical target labels,
identical folds, identical preprocessing, identical model class, identical regularization
selection machinery, identical calibration, identical missing-value handling, identical
coverage screening, identical hyperparameter search grid and selection rule.

WHY STAGE-2 M0 IS NOT THE PRODUCTION CHAMPION
---------------------------------------------
The champion artifact ships FROZEN hyperparameters (C, l1_ratio) that were selected against
M0's own 72-feature pool. Re-using those constants for M1 would hand M0 a tuned advantage and
M1 an untuned handicap -- a model-parity violation, which is a declared TRUE BLOCKER. So BOTH
arms re-tune identically by nested chronological CV inside each training fold.

`prediction_engine/eval/walk_forward.py` notes that re-tuning on its folds "would itself be
leakage/overfitting". That remark is about evaluating the FROZEN PRODUCTION ARTIFACT, where the
shipped constants are part of the thing under test. It does not apply here: Stage 2 tests a
FEATURE UNIVERSE, and both arms tune under the identical nested-CV rule using training data
only. No test-fold information reaches any hyperparameter. The champion artifact is never
written to, so CHAMPION_UNCHANGED holds.

MULTIPLICITY CONTROL -- M1 must not win on degrees of freedom
-------------------------------------------------------------
M1 has ~108 extra candidate columns against M0's 72. Without control, extra columns alone could
buy apparent skill. Controls, all frozen before any outcome:

  1. GROUPED SHRINKAGE. The LLM-derived columns are penalised as STRUCTURAL-FAMILY GROUPS, so a
     whole family must earn its way in; individual lucky columns cannot.
  2. IDENTICAL REGULARIZATION PATH. Both arms search the same (C, l1_ratio) grid under the same
     nested chronological CV and the same selection rule.
  3. NESTED IN-FOLD SELECTION ONLY. Every threshold edge, standardisation constant, profile
     band, coverage screen, feature selection and hyperparameter is fit inside the training
     fold. No OOS information may select a feature.
  4. NO PER-FAMILY CHERRY-PICKING. The primary claim is M1-universe vs M0-universe. Family
     level results are secondary and BH-FDR corrected.

Deliberately NOT used: an equal raw column cap. Forcing M1 down to 72 columns would handicap the
very thing under test. Fairness is enforced through an identical penalised-selection regime that
makes added columns pay for themselves, which is the honest test of information value.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

MODEL_SPECS_VERSION = "item6_stage2_model_specs_v1"

MODEL_CLASS = "elastic_net_logistic_regression"

#: Shared (C, l1_ratio) grid searched identically by BOTH arms.
C_GRID: Tuple[float, ...] = (0.003, 0.01, 0.03, 0.1)
L1_RATIO_GRID: Tuple[float, ...] = (0.2, 0.5, 0.8)

#: Inner nested chronological CV inside each training fold.
INNER_CV_SPLITS = 4
INNER_CV_KIND = "TimeSeriesSplit_expanding_chronological"

#: Preprocessing, identical in both arms, fit inside each tuning fold.
IMPUTATION = "median_fit_inside_tuning_fold"
SCALING = "standardize_fit_inside_tuning_fold"

#: Predeclared coverage screen. INHERITED from the champion's own declared rule
#: ("predeclared >=60% rule on outer-training period only"), not invented for Stage 2, and
#: applied identically to M0 and M1 columns.
MIN_NONMISSING_RATE = 0.60
COVERAGE_SCREEN_SCOPE = "outer_training_period_only"

#: Support floors for an LLM-derived column to be eligible at all (frozen before outcomes).
MIN_HISTORY_MATCHES = 3           # == champion MIN_CURRENT_SEASON_MATCHES
MIN_OPPONENT_PROFILE_SUPPORT = 50  # == similarity_policy.MIN_PROFILE_SUPPORT
MIN_COMPETITION_COVERAGE = 100     # min OOS predictions for a per-competition breakdown

CALIBRATION = "isotonic_fit_on_training_fold_only"

STRUCTURAL_GROUPS: Tuple[str, ...] = (
    "SF_THRESHOLD_NONLINEARITY",
    "SF_MULTIMETRIC_INTERACTION",
    "SF_HALF_OR_GAME_STATE_INTERACTION",
    "SF_TWO_AXIS_OPPONENT_PROFILE_INTERSECTION",
)


def m0_spec(m0_feature_names: Sequence[str]) -> Dict[str, object]:
    return {
        "arm": "M0",
        "role": "deterministic_baseline_feature_universe",
        "feature_universe": list(m0_feature_names),
        "n_features": len(m0_feature_names),
        "feature_source": "champion_stat_mixer_pool_unweakened",
        "model_class": MODEL_CLASS,
        "c_grid": list(C_GRID),
        "l1_ratio_grid": list(L1_RATIO_GRID),
        "inner_cv_splits": INNER_CV_SPLITS,
        "inner_cv_kind": INNER_CV_KIND,
        "imputation": IMPUTATION,
        "scaling": SCALING,
        "coverage_screen_min_nonmissing_rate": MIN_NONMISSING_RATE,
        "coverage_screen_scope": COVERAGE_SCREEN_SCOPE,
        "calibration": CALIBRATION,
        "grouped_shrinkage_groups": [],
        "uses_frozen_champion_hyperparameters": False,
        "llm_derived_features_available": False,
    }


def m1_spec(m0_feature_names: Sequence[str],
            llm_feature_names: Sequence[str]) -> Dict[str, object]:
    spec = m0_spec(m0_feature_names)
    spec.update({
        "arm": "M1",
        "role": "baseline_plus_frozen_llm_derived_feature_universe",
        "feature_universe": list(m0_feature_names) + list(llm_feature_names),
        "n_features": len(m0_feature_names) + len(llm_feature_names),
        "n_llm_derived_features": len(llm_feature_names),
        "llm_derived_feature_names": list(llm_feature_names),
        "grouped_shrinkage_groups": list(STRUCTURAL_GROUPS),
        "llm_derived_features_available": True,
    })
    return spec


def parity_assertions(m0: Dict, m1: Dict) -> Dict[str, object]:
    """Machine-checkable parity: every shared knob identical, only features differ."""
    shared_keys = ("model_class", "c_grid", "l1_ratio_grid", "inner_cv_splits", "inner_cv_kind",
                   "imputation", "scaling", "coverage_screen_min_nonmissing_rate",
                   "coverage_screen_scope", "calibration",
                   "uses_frozen_champion_hyperparameters")
    diffs = {k: (m0.get(k), m1.get(k)) for k in shared_keys if m0.get(k) != m1.get(k)}
    m0_set, m1_set = set(m0["feature_universe"]), set(m1["feature_universe"])
    return {
        "shared_knobs_identical": not diffs,
        "differing_shared_knobs": diffs,
        "m0_universe_is_subset_of_m1": m0_set <= m1_set,
        "only_difference_is_llm_feature_availability":
            (not diffs) and m0_set <= m1_set
            and (m1_set - m0_set) == set(m1.get("llm_derived_feature_names", ())),
        "n_added_features": len(m1_set - m0_set),
    }


def multiplicity_policy() -> Dict[str, object]:
    return {
        "multiplicity_policy_version": MODEL_SPECS_VERSION,
        "primary_claim": "M1_universe_vs_M0_universe",
        "controls": [
            "grouped_shrinkage_over_structural_families",
            "identical_regularization_grid_and_selection_rule_both_arms",
            "all_selection_and_tuning_nested_inside_training_folds",
            "family_level_results_secondary_and_BH_FDR_corrected",
        ],
        "equal_raw_column_cap_used": False,
        "equal_raw_column_cap_rationale":
            "Capping M1 to M0's column count would handicap the feature universe under test; "
            "fairness is enforced by an identical penalised-selection regime instead.",
        "feature_selected_using_oos_information": False,
        "hyperparameters_tuned_on_test_folds": False,
        "structural_groups": list(STRUCTURAL_GROUPS),
    }


def version_stamp() -> Dict[str, object]:
    return {"model_specs_version": MODEL_SPECS_VERSION, "model_class": MODEL_CLASS,
            "reads_outcomes": False}
