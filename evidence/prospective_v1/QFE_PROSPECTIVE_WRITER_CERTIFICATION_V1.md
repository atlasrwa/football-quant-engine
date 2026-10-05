# QFE Prospective V1 — Prediction Writer Certification

Certification hash: f5e1fb54bbdd6f78be9d27c720a37cc61f46042189d3d9afaaabae6d27121648

Status: **PASS — WRITER CERTIFIED; NO LIVE COHORT SELECTED**

The prospective writer is bound to:
- execution protocol bf5b1ba2b15be8db74618754028a34c9568dc281e2fb26a9d0e174552681ca4c
- Layer 4 V3 p_model freeze bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2
- Layer 5 V1.2 protocol ae39008016b66f27c279bd2d47093e679ff46458fb44226d2b373983d42bb46a

Historical counterfactual replay:
- fixture: THESTATSAPI:mt_585222974
- prior history rows: 5,321
- prediction rows: 19
- goals + side corners + total corners
- max raw-probability delta vs frozen Layer 4: **0.0**
- max calibrated p_model delta vs frozen Layer 4: **0.0**
- repeated bundle hash: 00d09da33020f7038ebbfaf2149477b03332ff9163dc103f2415cb3939fa88ec on both runs

Integrity:
- 28 focused tests passed
- 362 full-repository tests passed
- 89 research modules imported
- diff check passed

The writer fails closed on target outcome/stat leakage, non-cohort targets, stale post-base history, post-T6 history capture, and incomplete six-competition history coverage.

No live October cohort is selected yet. The canonical audited corpus ends on 2026-09-14, so the next required gate is an immutable live incremental football-history snapshot across all six frozen model competitions before any new cohort/prediction is frozen.
