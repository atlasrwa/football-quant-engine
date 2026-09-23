"""ITEM 6 STAGE 2 sample-size / sensitivity analysis (`item6_stage2_power_v2`).

This is a SENSITIVITY analysis, NOT a classical power calculation.

A classical power figure would require the standard deviation of the per-fixture paired log-loss
difference. That quantity cannot be known without fitting both arms and scoring them against
outcomes -- which is precisely what Stage 2 must not do during design. Asserting a single power
number here would mean either fabricating that SD or peeking. So instead the precision and the
detectable effect are tabulated ACROSS a range of plausible paired SDs, and the range itself is
reported as an assumption rather than a result.

TWO DEPENDENCE BOUNDS (v2)
--------------------------
The standard error of the pooled paired mean depends on within-week correlation, which is also
unknowable before scoring. v1 reported only the worst case and phrased its verdict as if it were
the expected case. v2 brackets it:

    SE_conservative = SD_paired / sqrt(N_blocks)     perfect within-week correlation
    SE_independent  = SD_paired / sqrt(N_fixtures)   independent fixtures

The realised block-bootstrap SE lies between the two (positive within-week correlation assumed;
the bootstrap is what will actually be used, this only plans for it).

WHAT "DETECTABLE" MEANS UNDER THE CONJUNCTIVE RULE (v2)
-------------------------------------------------------
PASS needs the 95% CI lower bound > 0 (S2P2) AND the point estimate >= the minimum practical
improvement MPI (S2P3). With the estimate ~ Normal(delta, SE):

    ci_half_width                     = z_0.975 * SE
    true delta needed for 80% power   = max(z_0.975 * SE, MPI) + z_0.80 * SE
    power at a true delta equal to MPI = 1 - Phi((max(z_0.975 * SE, MPI) - MPI) / SE)  (<= 0.5)

So a true effect of exactly MPI can never be passed with more than 50% probability. That is a
property of requiring the point estimate to clear MPI, and it is stated here before execution.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

POWER_VERSION = "item6_stage2_power_v2"

Z_95 = 1.959963985
Z_80 = 0.841621234

#: Plausible per-fixture paired log-loss-difference SDs. Declared as an ASSUMPTION RANGE.
#: The paired difference is far less variable than either arm's log loss because fixture
#: difficulty cancels; these span "nearly identical arms" to "substantially different arms".
ASSUMED_PAIRED_SD: Sequence[float] = (0.005, 0.010, 0.020, 0.050, 0.100, 0.200)


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def standard_error(paired_sd: float, n_eff: int) -> float:
    if n_eff <= 0:
        return float("inf")
    return float(paired_sd) / math.sqrt(n_eff)


def mde(paired_sd: float, n_blocks: int, *, z: float = Z_95) -> float:
    """95% CI half-width at the conservative (block-count) bound. Kept for v1 compatibility."""
    return z * standard_error(paired_sd, n_blocks)


def _bound_row(sd: float, n_eff: int, mpi: float) -> Dict[str, object]:
    se = standard_error(sd, n_eff)
    bar = max(Z_95 * se, mpi)
    return {
        "standard_error": round(se, 6),
        "ci_half_width_95": round(Z_95 * se, 6),
        "true_delta_for_80pct_power": round(bar + Z_80 * se, 6),
        "power_at_true_delta_equal_mpi": round(1.0 - _phi((bar - mpi) / se), 4),
        "ci_half_width_at_or_below_mpi": bool(Z_95 * se <= mpi),
    }


def sensitivity_table(n_blocks: int, n_fixtures: int,
                      assumed_sds: Sequence[float] = ASSUMED_PAIRED_SD) -> List[Dict]:
    from src.research.item6.stage2.evaluation import MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT as MPI
    return [{"assumed_paired_sd": sd,
             "conservative_bound_n_blocks": _bound_row(sd, n_blocks, MPI),
             "independent_bound_n_fixtures": _bound_row(sd, n_fixtures, MPI)}
            for sd in assumed_sds]


def build_power_sensitivity(*, n_oos_predictions: int, n_blocks: int, n_folds: int,
                            median_feature_coverage: float,
                            n_columns_below_coverage_screen: int) -> Dict[str, object]:
    from src.research.item6.stage2.evaluation import (BOOTSTRAP_CI_LEVEL,
                                                      MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT)
    mpi = MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT
    sd_max_cons = round(mpi * math.sqrt(n_blocks) / Z_95, 6)
    sd_max_ind = round(mpi * math.sqrt(n_oos_predictions) / Z_95, 6)
    return {
        "power_version": POWER_VERSION,
        "analysis_kind": "SENSITIVITY_NOT_CLASSICAL_POWER",
        "why_not_classical_power":
            "The SD of the paired per-fixture log-loss difference is unknowable without fitting "
            "and scoring both arms against outcomes, which Stage-2 design must not do. A single "
            "power number would require fabricating that SD or peeking at outcomes.",
        "n_oos_predictions_planned": n_oos_predictions,
        "n_oos_predictions_is_upper_bound": True,
        "n_bootstrap_blocks_iso_weeks": n_blocks,
        "n_folds": n_folds,
        "effective_n_bounds": {
            "conservative": "n_blocks (perfect within-week correlation)",
            "independent": "n_oos_predictions (independent fixtures)",
            "realised": "the frozen block bootstrap; expected between the two bounds"},
        "ci_level": BOOTSTRAP_CI_LEVEL,
        "minimum_practical_improvement": mpi,
        "assumed_paired_sd_range": list(ASSUMED_PAIRED_SD),
        "sensitivity_table": sensitivity_table(n_blocks, n_oos_predictions),
        "max_paired_sd_with_ci_half_width_at_or_below_mpi": {
            "conservative_bound": sd_max_cons, "independent_bound": sd_max_ind},
        # v1 key, retained with its v1 (conservative-bound) meaning for traceability.
        "max_paired_sd_detectable_at_minimum_practical_improvement": sd_max_cons,
        "conjunctive_rule_power_ceiling_at_mpi":
            "A true effect of exactly MPI passes S2P3 with probability <= 0.5 at any sample size, "
            "because S2P3 requires the point estimate itself to reach MPI. 80%-power effect sizes "
            "are tabulated per bound.",
        "sensitivity_verdict":
            "Precision is bracketed, not known. The 95% CI half-width is at or below MPI when the "
            f"per-fixture paired SD is <= {sd_max_cons} (conservative bound, perfect within-week "
            f"correlation) or <= {sd_max_ind} (independent-fixture bound); the realised block "
            "bootstrap will fall between. After execution the realised paired SD and "
            "block-bootstrap SE are reported, and a FAIL is interpreted with them: if the "
            "realised SE makes the 80%-power effect size larger than the effect of interest, the "
            "FAIL is INCONCLUSIVE AT THAT EFFECT SIZE; otherwise it is evidence against an effect "
            "of that size. This reading rule is fixed now, before any outcome.",
        "feature_coverage_sensitivity": {
            "median_llm_feature_coverage": median_feature_coverage,
            "n_columns_below_coverage_screen": n_columns_below_coverage_screen,
            "note": "Columns below the inherited >=0.60 training-period coverage screen are "
                    "dropped inside each training fold, identically to how M0 columns are "
                    "screened. Lower coverage reduces M1's effective information and biases the "
                    "comparison TOWARD the null, never toward a false positive.",
        },
        "reads_outcomes": False,
    }


def version_stamp() -> Dict[str, object]:
    return {"power_version": POWER_VERSION, "analysis_kind": "sensitivity",
            "fabricates_classical_power": False, "reads_outcomes": False}
