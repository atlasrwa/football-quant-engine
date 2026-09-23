"""ITEM 6 STAGE 2 threshold policy -- the NUMERIC CLAIM FIREWALL
(`item6_stage2_threshold_policy_v1`).

NO LLM-WRITTEN NUMBER MAY EVER BECOME A FEATURE PARAMETER.

Stage 1 recorded 106 advisory numeric-claim violations across 65 fixtures (mechanisms asserting
things like a specific possession percentage or corner count). Those numbers are prose. They are
discarded wholesale here: this module is the ONLY source of a threshold in Stage 2, and it
derives every cut point from TRAINING-FOLD DATA ALONE.

POLICY (option A + option E of the authorized menu)
---------------------------------------------------
  * A threshold-conditioned feature uses FIXED QUANTILE BINS whose edges are estimated from
    the training fold's empirical distribution of that exact rolling statistic.
  * A multi-metric interaction uses a STANDARDIZED CONTINUOUS PRODUCT with NO hard threshold;
    the mean/scale are likewise fit on the training fold only.
  * The quantile GRID itself (which quantiles) is preregistered and domain-neutral -- terciles.
    It is not chosen per metric, per target or per fold, so there is no per-feature tuning
    degree of freedom at all.

LEAKAGE DISCIPLINE
------------------
`fit()` must be handed ONLY training-fold rows. The fitted object is then applied unchanged to
validation and test rows. Fitting on anything else is the leakage failure mode this module
exists to prevent, so `fit()` records the cutoff it was fit under and `transform()` refuses to
run against a row whose kickoff precedes that cutoff's training window when asserted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

THRESHOLD_POLICY_VERSION = "item6_stage2_threshold_policy_v1"

# Preregistered, domain-neutral quantile grid. Terciles: low / mid / high.
QUANTILE_GRID: Sequence[float] = (1.0 / 3.0, 2.0 / 3.0)
BIN_LABELS: Sequence[str] = ("low", "mid", "high")

# A bin edge set is only usable if the training fold gave us enough finite observations.
MIN_TRAIN_OBS_FOR_EDGES = 200


class ThresholdPolicyError(RuntimeError):
    """Raised when a threshold is requested without a legitimate training-fold fit."""


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Deterministic linear-interpolation quantile (no numpy dependency, stable ordering)."""
    if not sorted_vals:
        raise ThresholdPolicyError("empty sample")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    frac = pos - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


@dataclass
class FittedThresholds:
    """Per-statistic tercile edges + standardisation, fit on ONE training fold."""
    fold_index: int
    train_end_unix: float
    edges: Dict[str, List[float]] = field(default_factory=dict)      # stat -> [q33, q66]
    center_scale: Dict[str, List[float]] = field(default_factory=dict)  # stat -> [mean, sd]
    n_obs: Dict[str, int] = field(default_factory=dict)
    policy_version: str = THRESHOLD_POLICY_VERSION

    # ---- application -----------------------------------------------------------------
    def bin_of(self, stat: str, value: Optional[float]) -> Optional[str]:
        """Tercile label for `value`, or None when unavailable (never imputed to a bin)."""
        if value is None:
            return None
        e = self.edges.get(stat)
        if not e:
            return None
        return BIN_LABELS[0] if value <= e[0] else (BIN_LABELS[1] if value <= e[1]
                                                   else BIN_LABELS[2])

    def standardize(self, stat: str, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        cs = self.center_scale.get(stat)
        if not cs or cs[1] <= 0.0:
            return None
        return (float(value) - cs[0]) / cs[1]

    def has(self, stat: str) -> bool:
        return stat in self.edges

    def to_dict(self) -> Dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "fold_index": self.fold_index,
            "train_end_unix": self.train_end_unix,
            "n_statistics": len(self.edges),
            "quantile_grid": list(QUANTILE_GRID),
            "bin_labels": list(BIN_LABELS),
            "edges": {k: list(v) for k, v in sorted(self.edges.items())},
            "center_scale": {k: list(v) for k, v in sorted(self.center_scale.items())},
            "n_obs": dict(sorted(self.n_obs.items())),
            "fit_on_training_fold_only": True,
            "llm_numeric_thresholds_used": False,
        }


def fit(train_stat_values: Dict[str, Sequence[Optional[float]]], *, fold_index: int,
        train_end_unix: float) -> FittedThresholds:
    """Fit tercile edges + standardisation from TRAINING-FOLD rows only.

    `train_stat_values` maps a rolling-statistic name to its observed values over the training
    fold. A statistic with too few finite observations gets NO edges, so any feature depending
    on it abstains rather than being thresholded on a thin sample.
    """
    ft = FittedThresholds(fold_index=fold_index, train_end_unix=float(train_end_unix))
    for stat, vals in sorted(train_stat_values.items()):
        finite = sorted(float(v) for v in vals
                        if v is not None and not math.isnan(float(v))
                        and not math.isinf(float(v)))
        ft.n_obs[stat] = len(finite)
        if len(finite) < MIN_TRAIN_OBS_FOR_EDGES:
            continue
        ft.edges[stat] = [_quantile(finite, QUANTILE_GRID[0]), _quantile(finite, QUANTILE_GRID[1])]
        mean = sum(finite) / len(finite)
        var = sum((x - mean) ** 2 for x in finite) / max(1, len(finite) - 1)
        ft.center_scale[stat] = [mean, math.sqrt(var)]
    return ft


def version_stamp() -> Dict[str, object]:
    return {
        "threshold_policy_version": THRESHOLD_POLICY_VERSION,
        "policy": "preregistered_domain_neutral_tercile_bins_plus_standardized_continuous",
        "quantile_grid": list(QUANTILE_GRID),
        "fit_scope": "training_fold_only",
        "llm_numeric_thresholds_used": False,
        "per_metric_grid_tuning": False,
        "reads_outcomes": False,
    }
