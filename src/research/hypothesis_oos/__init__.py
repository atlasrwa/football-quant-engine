"""V4 hypothesis-derived OOS validation — DOWNSTREAM research layer.

This package is the downstream statistical-validation layer for the frozen V3
hypothesis-derived deterministic measurements. It is intentionally separate from the
frozen V3 modules (`query_plan`, `cohort_measurement`, `similarity`, `vocabulary`), which
it USES but never edits.

Hard invariants (enforced by tests/research/hypothesis_oos/):
  * ZERO SPEND: no Bedrock client, no LLM call, no network read is importable here.
  * CHAMPION read-only: no module here writes the champion artifact.
  * No p_model / production-prediction import.
  * Structural eligibility only: no code path selects a candidate on an observed
    difference, sign, magnitude, |diff|/SE, or significance.

Nothing in this package runs the final OOS scoring on import; the design must be frozen
first (see research/hypothesis_engine/V4_HYPOTHESIS_DERIVED_OOS_PREREGISTRATION.md).
"""
from __future__ import annotations

HYPOTHESIS_OOS_VERSION = "hypothesis_derived_oos_v4_design"
