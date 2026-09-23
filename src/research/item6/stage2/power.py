"""ITEM 6 STAGE 2 sample-size / sensitivity analysis (`item6_stage2_power_v1`).

This is a SENSITIVITY analysis, NOT a classical power calculation.

A classical power figure would require the standard deviation of the per-fixture paired log-loss
difference. That quantity cannot be known without fitting both arms and scoring them against
outcomes -- which is precisely what Stage 2 must not do during design. Asserting a single power
number here would mean either fabricating that SD or peeking. So instead the minimum detectable
effect (MDE) is tabulated ACROSS a range of plausible paired SDs, and the range itself is
reported as an assumption rather than a result.

MDE for a paired mean under cluster (match-week) resampling, at the frozen 95% level:

    MDE  ~=  z * SD_paired / sqrt(N_effective)

N_effective is taken as the NUMBER OF BLOCKS (match-weeks), not the number of fixtures. That is
deliberately conservative: it assumes perfect within-week correlation, so the true MDE is no
worse than the tabulated one.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence

POWER_VERSION = "item6_stage2_power_v1"

Z_95 = 1.959963985

#: Plausible per-fixture paired log-loss-difference SDs. Declared as an ASSUMPTION RANGE.
#: The paired difference is far less variable than either arm's log loss because fixture
#: difficulty cancels; these span "nearly identical arms" to "substantially different arms".
ASSUMED_PAIRED_SD: Sequence[float] = (0.005, 0.010, 0.020, 0.050, 0.100, 0.200)


def mde(paired_sd: float, n_blocks: int, *, z: float = Z_95) -> float:
    if n_blocks <= 0:
        return float("inf")
    return z * float(paired_sd) / math.sqrt(n_blocks)


def sensitivity_table(n_blocks: int,
                      assumed_sds: Sequence[float] = ASSUMED_PAIRED_SD) -> List[Dict]:
    from src.research.item6.stage2.evaluation import MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT as MPI
    rows = []
    for sd in assumed_sds:
        m = mde(sd, n_blocks)
        rows.append({
            "assumed_paired_sd": sd,
            "minimum_detectable_delta_logloss": round(m, 6),
            "detectable_at_minimum_practical_improvement": bool(m <= MPI),
            "n_blocks_required_for_minimum_practical_improvement":
                int(math.ceil((Z_95 * sd / MPI) ** 2)),
        })
    return rows


def build_power_sensitivity(*, n_oos_predictions: int, n_blocks: int, n_folds: int,
                            median_feature_coverage: float,
                            n_columns_below_coverage_screen: int) -> Dict[str, object]:
    from src.research.item6.stage2.evaluation import (BOOTSTRAP_CI_LEVEL,
                                                      MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT)
    table = sensitivity_table(n_blocks)
    return {
        "power_version": POWER_VERSION,
        "analysis_kind": "SENSITIVITY_NOT_CLASSICAL_POWER",
        "why_not_classical_power":
            "The SD of the paired per-fixture log-loss difference is unknowable without fitting "
            "and scoring both arms against outcomes, which Stage-2 design must not do. A single "
            "power number would require fabricating that SD or peeking at outcomes.",
        "n_oos_predictions_planned": n_oos_predictions,
        "n_bootstrap_blocks_iso_weeks": n_blocks,
        "n_folds": n_folds,
        "effective_n_used_for_mde": "n_blocks (conservative: assumes perfect within-week "
                                    "correlation)",
        "ci_level": BOOTSTRAP_CI_LEVEL,
        "minimum_practical_improvement": MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT,
        "assumed_paired_sd_range": list(ASSUMED_PAIRED_SD),
        "sensitivity_table": table,
        "precision_of_paired_difference": [
            {"assumed_paired_sd": sd, "half_width_95ci": round(mde(sd, n_blocks), 6)}
            for sd in ASSUMED_PAIRED_SD
        ],
        "max_paired_sd_detectable_at_minimum_practical_improvement": round(
            MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT * math.sqrt(n_blocks) / Z_95, 6),
        "sensitivity_verdict":
            "The design detects the minimum practical improvement ONLY IF the per-fixture "
            "paired log-loss SD is at or below the figure above. If the realised paired SD "
            "exceeds it, a true effect of exactly the minimum practical size would not be "
            "separable from noise, and a FAIL must be read as INCONCLUSIVE AT THAT EFFECT SIZE "
            "rather than as evidence of no effect. The realised paired SD will be reported "
            "alongside the result so this distinction is auditable after the fact.",
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
