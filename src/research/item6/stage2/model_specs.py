"""ITEM 6 STAGE 2 model arm specifications + multiplicity policy
(`item6_stage2_model_specs_v2`).

M0 = the deterministic baseline feature universe (the champion's stat-mixer pool).
M1 = M0 + the frozen Stage-2-feasible LLM-derived feature universe.

THE ONLY SCIENTIFIC DIFFERENCE BETWEEN THE ARMS IS FEATURE AVAILABILITY.
Everything else is shared by construction: identical fixtures, identical target labels,
identical folds, identical preprocessing, identical model class, identical regularization
selection machinery, identical calibration, identical missing-value handling, identical
coverage screening, identical hyperparameter search grid and selection rule, identical
solver and convergence settings, identical output probability clip.

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

  1. ELASTIC-NET SHRINKAGE, UNIFORM PER COEFFICIENT. Every column in either arm -- baseline or
     LLM-derived -- faces the same L1+L2 penalty. An added column enters only if it lowers inner
     chronological CV log loss by more than its penalty costs; the L1 part zeroes the rest.
     (v1 declared "grouped shrinkage over structural families" but specified no group penalty
     and no solver. That was an unpinned free parameter for the executor AND the one declared
     machinery difference between the arms, so v2 removes it. Structural families are used
     only for the secondary ablations.)
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

MODEL_SPECS_VERSION = "item6_stage2_model_specs_v2"

MODEL_CLASS = "elastic_net_logistic_regression"

#: Penalty structure, identical in both arms: no group terms, no per-column penalty weights.
PENALTY_STRUCTURE = "elastic_net_uniform_per_coefficient_no_group_terms"

#: Estimator settings, INHERITED from the champion fitter (scripts/pilotC_stat_mixer.py:311),
#: identical in both arms. Pinned so the executor has nothing left to choose.
ESTIMATOR = {"sklearn_class": "LogisticRegression", "penalty": "elasticnet", "solver": "saga",
             "max_iter": 4000, "tol": 1e-4, "random_state": 0, "fit_intercept": True,
             "class_weight": None}

#: Hyperparameter selection rule, identical in both arms: sklearn GridSearchCV over the grid
#: below with cv=TimeSeriesSplit(n_splits=INNER_CV_SPLITS), scoring="neg_log_loss",
#: refit=True, on the (imputer -> scaler -> model) pipeline. Winner = best mean inner-fold
#: score; ties resolve to the first grid point in GridSearchCV's order (deterministic).
SELECTION_RULE = ("GridSearchCV_best_mean_inner_neg_log_loss_refit_true_"
                  "ties_to_first_grid_point")

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

#: Calibration, identical in both arms. NOT fit on in-sample predictions (those are
#: optimistically sharp and would bias both log loss and the S2P4 ECE clause). Procedure:
#:   1. with the selected (C, l1_ratio), refit the full pipeline on each inner
#:      TimeSeriesSplit(4) training split of the outer training block and predict its inner
#:      validation split -> chronological out-of-fold (OOF) predictions for the later 4/5 of the
#:      training block;
#:   2. fit IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1, increasing=True) on the
#:      pooled (OOF prediction, training label) pairs;
#:   3. apply it to the final refit model's test-block predictions.
#: The test block never touches the calibrator.
CALIBRATION = "isotonic_fit_on_inner_timeseries_oof_predictions_of_training_block"

#: Final probability clip applied after calibration, identical in both arms. INHERITED from the
#: champion fitter (np.clip(p, 0.01, 0.99)). It is required because isotonic regression can emit
#: exactly 0 or 1; unclipped, a single confident miss would cost ~34.5 nats at eps=1e-15 and a
#: handful of fixtures could dominate the primary endpoint.
PROBABILITY_CLIP = (0.01, 0.99)

#: Structural families of the LLM-derived columns. Used ONLY to define the secondary ablations
#: (M0 + one family's columns). They play no role in the M1 penalty.
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
        "penalty_structure": PENALTY_STRUCTURE,
        "estimator": dict(ESTIMATOR),
        "selection_rule": SELECTION_RULE,
        "c_grid": list(C_GRID),
        "l1_ratio_grid": list(L1_RATIO_GRID),
        "inner_cv_splits": INNER_CV_SPLITS,
        "inner_cv_kind": INNER_CV_KIND,
        "imputation": IMPUTATION,
        "scaling": SCALING,
        "coverage_screen_min_nonmissing_rate": MIN_NONMISSING_RATE,
        "coverage_screen_scope": COVERAGE_SCREEN_SCOPE,
        "calibration": CALIBRATION,
        "probability_clip": list(PROBABILITY_CLIP),
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
        "llm_derived_features_available": True,
    })
    return spec


def parity_assertions(m0: Dict, m1: Dict) -> Dict[str, object]:
    """Machine-checkable parity: every shared knob identical, only features differ."""
    shared_keys = ("model_class", "penalty_structure", "estimator", "selection_rule", "c_grid",
                   "l1_ratio_grid", "inner_cv_splits", "inner_cv_kind", "imputation", "scaling",
                   "coverage_screen_min_nonmissing_rate", "coverage_screen_scope",
                   "calibration", "probability_clip",
                   "uses_frozen_champion_hyperparameters")
    diffs = {k: (m0.get(k), m1.get(k)) for k in shared_keys if m0.get(k) != m1.get(k)}
    # Any key outside the declared per-arm fields must also be shared, so a new machinery knob
    # cannot silently differ between arms by being left off the list above.
    per_arm = {"arm", "role", "feature_universe", "n_features", "n_llm_derived_features",
               "llm_derived_feature_names", "llm_derived_features_available"}
    for k in (set(m0) | set(m1)) - per_arm - set(shared_keys):
        if m0.get(k) != m1.get(k):
            diffs[k] = (m0.get(k), m1.get(k))
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
            "elastic_net_uniform_per_coefficient_penalty_both_arms",
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
        "grouped_shrinkage_used": False,
        "grouped_shrinkage_removed_in_v2":
            "v1 declared grouped shrinkage over structural families without a group penalty or "
            "solver, leaving the executor free to choose one and making it the only declared "
            "machinery difference between arms. v2 removes it before any execution or outcome "
            "access; elastic net under an identical grid and nested chronological CV is the "
            "penalised-selection control.",
        "structural_groups_role": "secondary_ablation_definition_only",
        "structural_groups": list(STRUCTURAL_GROUPS),
    }


def version_stamp() -> Dict[str, object]:
    return {"model_specs_version": MODEL_SPECS_VERSION, "model_class": MODEL_CLASS,
            "reads_outcomes": False}
