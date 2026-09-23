"""ITEM 6 STAGE 2 evaluation protocol + frozen pass/fail rule
(`item6_stage2_evaluation_v2`).

Defines -- BEFORE any outcome is observed -- the endpoint, the sign convention, the inference
method, and the conjunctive decision rule. Nothing here computes a metric; it declares how one
will be computed and what will count as success.

SIGN CONVENTION (frozen, stated once, used everywhere)
------------------------------------------------------
    DELTA_LOGLOSS = mean(logloss_M0) - mean(logloss_M1)

    POSITIVE  => M1 (with LLM-derived features) is BETTER (lower log loss).
    NEGATIVE  => M1 is WORSE.

STATISTICAL UNIT AND DEPENDENCE
-------------------------------
The unit is the out-of-sample prediction for a single fixture. Predictions are NOT iid: the same
teams recur, fixtures cluster in match-weeks and competitions, and skill drifts over time.
Treating them as iid would understate the standard error. Primary inference is therefore a
PAIRED CLUSTER (BLOCK) BOOTSTRAP resampling whole ISO match-weeks with replacement: the pairing
is preserved because M0 and M1 predict the identical fixtures, and the block captures
within-week and repeated-team dependence.

WHY PAIRED
----------
Both arms score the same fixtures from the same folds, so the per-fixture difference removes
fixture difficulty entirely and the comparison is far more precise than two independent means.

v2 PINS EVERY KNOB THE EXECUTOR WOULD OTHERWISE CHOOSE
------------------------------------------------------
v1 declared the endpoint but left the scored set, pooling, ECE binning, bootstrap CI type,
secondary-metric definitions and ablation construction to the executor. Anything unpinned could
be chosen after seeing outcomes, so v2 fixes each one below (see EXECUTION_PINS), before any
execution or outcome access.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

EVALUATION_VERSION = "item6_stage2_evaluation_v2"

PRIMARY_METRIC = "OOS_MEAN_LOGLOSS_DELTA_M0_MINUS_M1"
PRIMARY_SIGN_CONVENTION = "positive_means_M1_better"

SECONDARY_METRICS: Tuple[str, ...] = (
    "OOS_MEAN_BRIER_DELTA_M0_MINUS_M1",
    "EXPECTED_CALIBRATION_ERROR_M0",
    "EXPECTED_CALIBRATION_ERROR_M1",
    "RESIDUAL_DEVIANCE_DELTA",
    "SELECTED_FEATURE_STABILITY_ACROSS_FOLDS",
)

#: Primary inference.
INFERENCE_METHOD = "paired_cluster_block_bootstrap_over_iso_match_weeks"
BOOTSTRAP_RESAMPLES = 10000
BOOTSTRAP_CI_LEVEL = 0.95
BOOTSTRAP_SEED = 0            # frozen; the resampling is reproducible

#: Minimum practical improvement, in nats of mean log loss.
#: ANCHORED, not invented: the champion's own reported skill is ~1.2% BSS. Against a base log
#: loss of order 0.68 nats, 0.0010 nats is ~0.15% relative -- roughly an order of magnitude
#: BELOW the engine's existing measured skill. It is therefore a genuinely minimal bar that
#: still excludes numerically trivial deltas from being reported as incremental information.
MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT = 0.0010

#: Calibration must not materially deteriorate to buy sharpness.
MAX_ECE_DETERIORATION = 0.005

#: Family-level secondary analysis multiplicity control.
FAMILY_LEVEL_MULTIPLICITY_METHOD = "benjamini_hochberg_fdr"
FAMILY_LEVEL_FDR_Q = 0.10

#: Expected calibration error, identical in both arms. INHERITED from the champion fitter
#: (scripts/pilotC_stat_mixer.py:340): 10 equal-width bins on [0, 1], bin b = [b/10, (b+1)/10)
#: with the last bin closed; ECE = sum_b (n_b / N) * |mean(p_b) - mean(y_b)|; empty bins skipped.
ECE_N_BINS = 10
ECE_BINNING = "equal_width_last_bin_closed_count_weighted_abs_gap"

#: Every remaining executor choice, frozen.
EXECUTION_PINS: Dict[str, str] = {
    "scored_set":
        "all fixtures in the frozen fold manifest's test blocks whose primary-target label is "
        "resolvable (mix.outcome returns non-None) AND for which BOTH arms return a finite "
        "probability. The set is the intersection, identical for both arms; any fixture dropped "
        "is dropped from both and the drop count is reported. Missing FEATURES never drop a "
        "fixture (they are median-imputed inside the pipeline).",
    "pooling":
        "DELTA_LOGLOSS is the fixture-weighted mean of per-fixture (logloss_M0 - logloss_M1) "
        "over the pooled scored set of all folds. No per-fold averaging, no fold weights.",
    "probability_scored":
        "the final post-calibration, post-clip probability from model_specs.PROBABILITY_CLIP; "
        "logloss() eps=1e-15 is a numerical guard only.",
    "bootstrap":
        "numpy.random.default_rng(BOOTSTRAP_SEED); BOOTSTRAP_RESAMPLES replicates; each "
        "replicate draws n_blocks ISO-week blocks (iso_week_block of kickoff) with replacement "
        "from the scored set's blocks and computes the fixture-weighted mean paired delta over "
        "all fixtures in the drawn blocks (a block drawn k times counts k times).",
    "ci_type":
        "percentile: numpy.percentile(replicates, [2.5, 97.5]) with numpy's default 'linear' "
        "method. S2P2 uses the 2.5th percentile.",
    "ece":
        "ECE_BINNING with ECE_N_BINS, computed per arm on the pooled scored set.",
    "brier_delta": "fixture-weighted mean of (brier_M0 - brier_M1); positive = M1 better.",
    "residual_deviance_delta": "2 * N_scored * DELTA_LOGLOSS (deterministic transform, no test).",
    "selected_feature_stability":
        "for each column, the fraction of the 5 outer folds in which its final refit coefficient "
        "satisfies |coef| > 1e-8 (the champion's selection threshold). Descriptive only.",
    "ablation_construction":
        "M1_<FAMILY>_ONLY = M0 columns + the LLM-derived columns whose structural family is "
        "<FAMILY>, fit with the identical machinery. M1_ALL is M1.",
    "family_level_test":
        "for each single-family ablation vs M0: one-sided block-bootstrap p = fraction of "
        "replicate deltas <= 0 (same rng seed and procedure as the primary), then "
        "Benjamini-Hochberg at FAMILY_LEVEL_FDR_Q across the 4 single-family ablations. All 4 "
        "are reported whatever the outcome.",
    "secondary_target_test":
        "the full M0-vs-M1 procedure repeated per secondary target; one-sided bootstrap p as "
        "above; Benjamini-Hochberg at FAMILY_LEVEL_FDR_Q across the 2 secondary targets.",
    "fold_training_failure":
        "if either arm cannot be fit on a fold (e.g. single-class training labels), that fold's "
        "fixtures are dropped from BOTH arms and the fold is reported as skipped; no refit with "
        "altered settings is permitted.",
}

#: Pre-registered ablations. SECONDARY ONLY -- they do not create additional primary claims.
ABLATIONS: Tuple[str, ...] = (
    "M1_ALL",
    "M1_THRESHOLD_ONLY",
    "M1_MULTIMETRIC_ONLY",
    "M1_HALF_STATE_ONLY",
    "M1_PROFILE_ONLY",
)

SECONDARY_TARGET_ADJUSTMENT = "benjamini_hochberg_fdr_across_secondary_targets"


def logloss(p: float, y: float, *, eps: float = 1e-15) -> float:
    """Per-prediction log loss with symmetric clipping (declared, not tuned)."""
    q = min(max(float(p), eps), 1.0 - eps)
    return -(y * math.log(q) + (1.0 - y) * math.log(1.0 - q))


def brier(p: float, y: float) -> float:
    return (float(p) - float(y)) ** 2


def iso_week_block(kickoff_unix: float) -> str:
    """ISO year-week block label used as the bootstrap cluster."""
    import datetime as dt
    d = dt.datetime.fromtimestamp(float(kickoff_unix), dt.timezone.utc)
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def decision_rule() -> Dict[str, object]:
    """The frozen conjunctive Stage-2 pass/fail rule. ALL clauses must hold for PASS."""
    return {
        "primary_metric": PRIMARY_METRIC,
        "sign_convention": PRIMARY_SIGN_CONVENTION,
        "clauses": [
            {"id": "S2P1", "requirement": "DELTA_LOGLOSS > 0",
             "meaning": "M1 achieves lower mean OOS log loss than M0"},
            {"id": "S2P2",
             "requirement": f"lower bound of the {int(BOOTSTRAP_CI_LEVEL*100)}% paired "
                            f"block-bootstrap CI on DELTA_LOGLOSS > 0",
             "meaning": "the no-effect value is excluded under clustered uncertainty"},
            {"id": "S2P3",
             "requirement": f"DELTA_LOGLOSS >= {MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT}",
             "meaning": "the improvement is not numerically trivial"},
            {"id": "S2P4",
             "requirement": f"ECE_M1 <= ECE_M0 + {MAX_ECE_DETERIORATION}",
             "meaning": "calibration does not materially deteriorate"},
        ],
        "combination": "CONJUNCTIVE_ALL_CLAUSES_REQUIRED",
        "primary_target_only": True,
        "secondary_targets_reported_with": SECONDARY_TARGET_ADJUSTMENT,
        "subjective_override_permitted": False,
        "fail_is_a_valid_scientific_result": True,
    }


def failure_modes() -> List[str]:
    """How Stage 2 can FAIL cleanly -- enumerated so a null is interpretable, not a surprise."""
    return [
        "DELTA_LOGLOSS <= 0: the LLM-derived universe adds no information or hurts",
        "DELTA_LOGLOSS > 0 but the block-bootstrap CI includes 0: indistinguishable from noise "
        "once temporal and repeated-team dependence is respected",
        "DELTA_LOGLOSS > 0 and CI excludes 0 but below the minimum practical improvement: "
        "detectable but trivial",
        "calibration deterioration beyond the allowance: sharpness bought at the cost of "
        "probability quality",
        "elastic-net selection zeroes every LLM-derived column in every fold: the features "
        "carry no independent signal beyond the baseline",
    ]


def version_stamp() -> Dict[str, object]:
    return {
        "evaluation_version": EVALUATION_VERSION,
        "primary_metric": PRIMARY_METRIC,
        "sign_convention": PRIMARY_SIGN_CONVENTION,
        "inference_method": INFERENCE_METHOD,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "minimum_practical_improvement": MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT,
        "max_ece_deterioration": MAX_ECE_DETERIORATION,
        "ece_n_bins": ECE_N_BINS,
        "ece_binning": ECE_BINNING,
        "bootstrap_ci_type": "percentile",
        "family_level_fdr_q": FAMILY_LEVEL_FDR_Q,
        "execution_pins": dict(EXECUTION_PINS),
        "family_level_multiplicity": FAMILY_LEVEL_MULTIPLICITY_METHOD,
        "ablations": list(ABLATIONS),
        "hit_rate_used_as_primary": False,
        "market_edge_in_primary_endpoint": False,
        "reads_outcomes": False,
    }
