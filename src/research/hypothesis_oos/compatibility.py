"""Deterministic baseline/condition compatibility rule (`baseline_compatibility_v1`).

DOWNSTREAM research layer only. This does NOT modify any frozen V3 artifact; it is a new
structural filter applied to compiled measurement specifications before the V4 statistical
stage reads any data.

WHY THIS EXISTS
---------------
V3 measurement discovered that conditioning on `venue` and then comparing against
`SUBJECT_VENUE_BASELINE` yields a conditional cohort that is the IDENTICAL match set as its
comparison cohort -- a tautology that compiles, is "measurable", but encodes no contrast.
`cohort_measurement.execute` already detects this at EXECUTION time and types it
`NOT_DISTINCT`. This module detects the same class STRUCTURALLY, before any data is read,
so the venue family's baseline-absorbing combination is excluded by construction and can
never enter the V4 candidate set or absorb the same conditioning dimension.

This is a pure, deterministic projection of the spec. It reads no data, no outcome, no
price, no probability, and no observed effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

COMPATIBILITY_VERSION = "baseline_compatibility_v1"

#: Which conditioning dimension each comparison baseline ABSORBS. A baseline that absorbs
#: the same dimension the candidate conditions on makes the conditional and comparison
#: cohorts identical by construction -> no contrast. `None` means the baseline absorbs no
#: single conditioning dimension (SUBJECT_OVERALL_BASELINE compares against the
#: unconditioned window; LEAGUE_ENVIRONMENT_BASELINE is a different population;
#: SUBJECT_RECENT_VS_LONG_BASELINE is a window contrast).
_BASELINE_ABSORBS = {
    "SUBJECT_OVERALL_BASELINE": None,
    "SUBJECT_VENUE_BASELINE": "venue",
    "SUBJECT_COMPETITION_BASELINE": "competition",
    "LEAGUE_ENVIRONMENT_BASELINE": None,
    "SUBJECT_RECENT_VS_LONG_BASELINE": None,
}

NOT_DISTINCT_BY_CONSTRUCTION = "NOT_DISTINCT_BY_CONSTRUCTION"
COMPATIBLE = "COMPATIBLE"


@dataclass(frozen=True)
class CompatibilityVerdict:
    status: str                       # COMPATIBLE | NOT_DISTINCT_BY_CONSTRUCTION
    conditioning_dimensions: tuple[str, ...]
    comparison_cohort: str
    absorbed_dimension: Optional[str]
    reason: str

    @property
    def eligible(self) -> bool:
        return self.status == COMPATIBLE

    def to_dict(self) -> dict:
        return {
            "compatibility_version": COMPATIBILITY_VERSION,
            "status": self.status,
            "eligible": self.eligible,
            "conditioning_dimensions": list(self.conditioning_dimensions),
            "comparison_cohort": self.comparison_cohort,
            "absorbed_dimension": self.absorbed_dimension,
            "reason": self.reason,
        }


def baseline_absorbs(comparison_cohort: str) -> Optional[str]:
    """Return the conditioning dimension a comparison baseline absorbs, or None.

    Unknown comparisons are treated conservatively as absorbing nothing here; the frozen
    compiler already rejects comparisons outside the closed vocabulary, so this path is a
    defence-in-depth default rather than a live case.
    """
    return _BASELINE_ABSORBS.get(comparison_cohort, None)


def conditioning_dimensions_of(spec_dict: dict) -> tuple[str, ...]:
    """The set of dimensions a measurement spec actually conditions on.

    Reads the projected `MeasurementSpec.to_dict()` fields only; introduces no new
    semantics. A field set to None or 'ANY' is not a condition.
    """
    dims: list[str] = []
    if spec_dict.get("venue") not in (None, "ANY"):
        dims.append("venue")
    if spec_dict.get("competition") not in (None, "ANY"):
        dims.append("competition")
    if spec_dict.get("own_formation_family") not in (None, "ANY"):
        dims.append("own_formation_family")
    if spec_dict.get("opponent_formation_family") not in (None, "ANY"):
        dims.append("opponent_formation_family")
    if spec_dict.get("opponent_profile_band") not in (None, "ANY"):
        dims.append("opponent_profile")
    return tuple(dims)


def check_spec(spec_dict: dict) -> CompatibilityVerdict:
    """Structural compatibility verdict for one measurement spec. Pure; reads no data."""
    comparison = spec_dict.get("comparison_cohort", "")
    conditions = conditioning_dimensions_of(spec_dict)
    absorbed = baseline_absorbs(comparison)

    if absorbed is not None and absorbed in conditions:
        return CompatibilityVerdict(
            status=NOT_DISTINCT_BY_CONSTRUCTION,
            conditioning_dimensions=conditions,
            comparison_cohort=comparison,
            absorbed_dimension=absorbed,
            reason=(f"comparison {comparison!r} absorbs conditioning dimension "
                    f"{absorbed!r}: the conditional cohort is the identical match set as "
                    f"its comparison, so the candidate encodes no contrast and is excluded "
                    f"before any data is read"))

    # Unconditioned candidate compared against its own overall baseline is also degenerate
    # (identical to the whole window). Detect it here for completeness; V3 typed these
    # NOT_DISTINCT at execution.
    if not conditions and comparison == "SUBJECT_OVERALL_BASELINE":
        return CompatibilityVerdict(
            status=NOT_DISTINCT_BY_CONSTRUCTION,
            conditioning_dimensions=conditions,
            comparison_cohort=comparison,
            absorbed_dimension=None,
            reason=("unconditioned candidate compared against SUBJECT_OVERALL_BASELINE "
                    "is the identical window; no contrast by construction"))

    return CompatibilityVerdict(
        status=COMPATIBLE,
        conditioning_dimensions=conditions,
        comparison_cohort=comparison,
        absorbed_dimension=absorbed,
        reason="conditioning dimension is not absorbed by the comparison baseline")
