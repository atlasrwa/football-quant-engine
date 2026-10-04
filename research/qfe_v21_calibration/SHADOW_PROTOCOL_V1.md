# QFE V2.1 — Corner-Side Calibration Prospective Shadow V1

Status: **PREREGISTERED PROSPECTIVE SHADOW**

The only challenger is fixed: **75% Platt + 25% isotonic** on the frozen raw QFE corner-side probabilities.

The frozen V2 corner-side `PLATT_GLOBAL` calibrator remains production/reference. Goals and corner totals are unchanged.

The candidate is refit once on all old Layer 4 CALIBRATION data, frozen, and then evaluated only on new post-freeze immutable prediction records. No market prices enter either calibrator.

Primary stopping rule: at least **250 settled unique fixtures**, **500 event cells**, and **8 distinct UTC calendar weeks**. The first snapshot meeting all three is the evaluation snapshot; the experiment cannot be extended after seeing results.

Evidence gate: paired weekly-block 95% CI lower bound must be above zero for both Log Loss and Brier, with no HOME/AWAY role LL regression worse than 0.001. Passing does not automatically modify production.
