# QFE V2 — PR #47 Independent Audit V1

Audit hash: `90f427a82bf215ac7ee0884e04fe78fe40502562dc362747c615868bb20da3b7`

Status: **PASS WITH RESEARCH CAVEATS — DEVELOPMENT SELECTION ONLY**

## Independent verification

- PR #47 head: `b165ef445662b13a96f3ce7a12e78204b9539b80`
- Repaired Layer 3 replay: `669a6a6e5b498858033b505f7e6dfd36af448309`
- WARMUP + DEVELOPMENT are the only model-selection stream.
- DEVELOPMENT is the only scored partition.
- CALIBRATION scored: **0**.
- Exposed former-PROTECTED scored: **0**.
- No market inputs, network calls or Layer 2 evidence artifact consumption.

## Exact regeneration

- Chronology: **BYTE-EXACT**.
- Structured-development tournament: **BYTE-EXACT**.
- Goals OOF: **BYTE-EXACT — 3,812 rows**.
- Corners OOF: **BYTE-EXACT — 3,783 rows**.
- Structured fold OOF: **BYTE-EXACT — 15,864 rows / 7,950 binary rows**.
- Component evaluation: **BYTE-EXACT**.

Focused tests: **35/35 PASS**. Full repository: **338/338 PASS**. Import sweep: **86/86 PASS**. Diff check: **PASS**.

## Anti-retuning

The chronology and bounded candidate grids existed before the repaired replay. The PIT repair changed information-availability handling, not the candidate families, grids, selection objective or thresholds.

## Research caveats

1. The 27-way intensity winner has no selection-adjusted uncertainty; its bootstrap interval is versus the anchor.
2. Both selected configs hit grid boundaries (influence 1.0, team-comp prior 4); goals also uses the maximum 360-day half-life.
3. Winner-vs-runner-up NLL gaps are tiny: about 0.000488 for goals and 0.000341 for corners.
4. Structured DEVELOPMENT OOF is not nested with respect to intensity hyperparameter selection; it is appropriate for DEVELOPMENT triage, not an unbiased estimate of the complete selection procedure.
5. Corners NB2 is mixed: side-joint likelihood and binary Log Loss/Brier improve, while fold total-count NLL worsens. It remains a binary-market candidate, not a universal distribution winner.

## Verdict

**CERTIFY PR #47 as valid DEVELOPMENT candidate-selection evidence only.**

This does not promote a final model, authorize calibration/market-edge claims, or restore the exposed 317-fixture cohort as a valid final holdout.

Next gate: **independent audit of PR #48 / Layer 3.1 before Layer 4 is accepted.**
