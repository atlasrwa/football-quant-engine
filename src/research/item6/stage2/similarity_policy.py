"""ITEM 6 STAGE 2 opponent-profile similarity policy (`item6_stage2_similarity_policy_v1`).

The two-axis opponent-profile-intersection family needs "teams like this opponent". Stage 1's
LLM may have proposed WHICH DIMENSIONS matter; it never supplies a similarity number. All
similarity arithmetic is deterministic and fit on training-fold data only.

FROZEN SPECIFICATION
--------------------
  input dimensions    : the canonical metric axes named by the family, each as a
                        season-to-date rolling mean (FOR or AGAINST as canonicalised).
  scaling             : z-score using training-fold mean/sd (from the threshold policy's
                        `center_scale`, so one fitted object governs both).
  missing-value policy: ABSTAIN. A row missing any axis yields no profile band and the feature
                        is absent for that fixture -- never zero-filled, never mean-imputed.
  banding             : each axis is reduced to its training-fold tercile band (low/mid/high);
                        the two-axis profile is the INTERSECTION of the two bands.
  distance metric     : none required. Banded intersection is used in preference to a
                        k-nearest-neighbour distance because it introduces no neighbour-count
                        hyperparameter and no distance-metric choice, i.e. zero extra tuning
                        degrees of freedom -- which is what keeps the M0/M1 comparison fair.
  shrinkage           : support-count driven. A band-intersection cell with fewer than
                        MIN_PROFILE_SUPPORT training observations is pooled up to the single-axis
                        band; if that also lacks support the feature abstains.

No LLM similarity score. No future data. No outcome participates in defining a band.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

SIMILARITY_POLICY_VERSION = "item6_stage2_similarity_policy_v1"

#: Minimum training-fold observations for a two-axis band-intersection cell to be used directly.
MIN_PROFILE_SUPPORT = 50
#: Minimum training-fold observations for the single-axis fallback band.
MIN_AXIS_SUPPORT = 150

ABSTAIN = None


@dataclass
class ProfileBanding:
    """Training-fold support counts for band cells, enabling deterministic shrinkage."""
    fold_index: int
    cell_support: Dict[str, int]      # "axisA=low|axisB=high" -> n
    axis_support: Dict[str, int]      # "axisA=low" -> n

    def resolve(self, axis_bands: Sequence[Tuple[str, Optional[str]]]) -> Optional[str]:
        """Deterministic profile key for an ordered list of (axis_name, band) pairs.

        Returns None (ABSTAIN) when any axis band is missing or support is insufficient at
        both the intersection and the single-axis fallback level.
        """
        if any(b is None for _, b in axis_bands):
            return ABSTAIN
        cell = "|".join(f"{a}={b}" for a, b in axis_bands)
        if self.cell_support.get(cell, 0) >= MIN_PROFILE_SUPPORT:
            return cell
        # shrink to the first (primary) axis only
        a0, b0 = axis_bands[0]
        single = f"{a0}={b0}"
        if self.axis_support.get(single, 0) >= MIN_AXIS_SUPPORT:
            return single
        return ABSTAIN

    def to_dict(self) -> Dict[str, object]:
        return {
            "similarity_policy_version": SIMILARITY_POLICY_VERSION,
            "fold_index": self.fold_index,
            "n_cells": len(self.cell_support),
            "n_axes": len(self.axis_support),
            "min_profile_support": MIN_PROFILE_SUPPORT,
            "min_axis_support": MIN_AXIS_SUPPORT,
            "fit_on_training_fold_only": True,
        }


def fit(train_band_rows: Sequence[Sequence[Tuple[str, Optional[str]]]], *,
        fold_index: int) -> ProfileBanding:
    """Count band-cell and single-axis support over TRAINING-FOLD rows only."""
    cell: Dict[str, int] = {}
    axis: Dict[str, int] = {}
    for bands in train_band_rows:
        if any(b is None for _, b in bands):
            continue
        key = "|".join(f"{a}={b}" for a, b in bands)
        cell[key] = cell.get(key, 0) + 1
        for a, b in bands:
            k = f"{a}={b}"
            axis[k] = axis.get(k, 0) + 1
    return ProfileBanding(fold_index=fold_index, cell_support=cell, axis_support=axis)


def version_stamp() -> Dict[str, object]:
    return {
        "similarity_policy_version": SIMILARITY_POLICY_VERSION,
        "method": "training_fold_tercile_band_intersection_with_support_shrinkage",
        "distance_metric": "none_banded_intersection",
        "neighbour_count_hyperparameter": False,
        "missing_value_policy": "abstain_never_impute",
        "llm_similarity_score_used": False,
        "fit_scope": "training_fold_only",
        "reads_outcomes": False,
    }
