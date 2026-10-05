# QFE V2 Layer 4 — Standalone p_model Freeze ABORT

Abort hash: 7bbab3206446421f3a6166c975fe224f14ac2fbf46744bf53acc5d7156b8438b

Status: **ABORT — OUTPUT-SAFETY IMPLEMENTATION DEFECT**

The repaired Layer 4 V2 calibration selection completed deterministically, but its frozen standalone p_model is not production-safe.

The selected GOALS_TOTAL isotonic calibrator emitted exactly 1.0 on three CALIBRATION rows, including one CALIBRATION_SELECT row. The protocol already declares probability_clip = 1e-6, but the implementation used that bound inside optimization/loss calculations and did not apply it to emitted p_model values.

A future wrong outcome at p=1.0 would have unbounded Log Loss.

V2 calibration-selection evidence is preserved as exposed repair evidence. The V2 model freeze is not eligible for prospective use.

Successor V3 is restricted to one deterministic repair: clamp emitted p_model to [1e-6, 1-1e-6]. Calibrator candidates, selected methods, ensemble weights, FIT/SELECT chronology, thresholds and selection rules may not change.
