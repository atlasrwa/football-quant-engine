# QFE V2.1 — Exploratory Calibration Protocol V1

Status: **PREREGISTERED EXPLORATORY ONLY**

The existing Layer 4 calibration selection is immutable. This experiment does not rewrite it and cannot modify production `p_model`.

Because the old CALIBRATION_SELECT outcomes were already opened in Layer 4 V1, they are development evidence here, not a new confirmatory holdout. PROTECTED outcomes remain forbidden.

Two new calibration families are frozen before scoring:

1. **Platt–isotonic shrinkage blend** — preserves monotonicity while shrinking the high-variance isotonic map toward a low-variance Platt map.
2. **Platt-centered monotone logit spline** — a smooth piecewise-linear logit calibration map with positive slope everywhere, nonlinear deviations regularized toward Platt, and curvature penalization.

Every candidate uses one monotone map per calibration group. No line-specific calibrators are allowed, so count-market ladder ordering must remain coherent.

Any improvement is only a signal for a later untouched future holdout. There is no production promotion gate in this experiment.
