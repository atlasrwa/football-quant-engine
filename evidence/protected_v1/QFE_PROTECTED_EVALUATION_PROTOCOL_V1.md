# QFE V2 — Protected Evaluation Protocol V1

Contract hash: `41c446b15f03ae91bcc76ab26b5b90e0a6f40cfed603d8a0f4bb08df97b0a0d7`

Status: **FROZEN BEFORE PROTECTED SCORING**

## Two-phase firewall

1. Generate and commit all protected predictions with **no own-outcome, market or settlement fields**.
2. Only after that prediction artifact is frozen may canonical protected outcomes be joined for scoring.

Earlier protected matches may update the rolling state for later fixtures only after their entire same-kickoff batch has been forecast. Same-kickoff fixtures never update one another. Layer 4 weights, common corner NB2 alpha, calibrators, OOD thresholds and calibration-support bins remain frozen.

## Global scorecard

- Goals O2.5: one event per eligible fixture.
- Corner sides: fixture-balanced, HOME/AWAY each 50%, lines equal within role.
- Corner totals: fixture-balanced, six lines equal.
- Primary metrics: Log Loss and Brier.
- Calibration/support/OOD slices are supporting diagnostics only.

## Market-relative scorecard

Only the immutable Layer 5 matched-market manifest may be used. The T-6h horizon/source/book hierarchy may not be relaxed after outcomes. Sparse market evidence must be labeled underpowered.

Any scoring defect after protected outcomes are opened aborts V1 and requires a new version.
