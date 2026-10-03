# QFE V2 Layer 5 V1.1 — Integrity Audit

Audit hash: `3a93b1954e66515275d5965dbf833c502b5fc5849fcd1eda32c333934ebb856b`

Status: **PASS — FREEZE READY / PROTECTED OUTCOMES UNOPENED**

## Repository gate

- **327 passed / 0 failed**
- **87 research modules / 0 import failures**
- `git diff --check`: **PASS**
- Foundation through Layer 4 evidence unchanged
- Active legacy-product source refs: **0**

## Protocol integrity

V1 (`ecb72d508f421fbbcd45e4623acc50df882c178af83743365ed4be4e2dcebf65`) is preserved but aborted pre-protected because bookmaker selection was underspecified. V1.1 (`0e3928354f7da00e74c9bacd43b02cdace1556d0d8e11544f9ae0bb49fab2fe5`) fixes a deterministic hierarchy and no-fallback rule before any protected outcome was opened.

## Adversarial gate

- Isotonic cases: **8,700**
- Latest-bundle price-invariance: **1,000**
- Bookmaker-hierarchy price-invariance: **1,000**
- Random disagreement surfaces: **20,000**
- Non-max-gap selections: **500**
- Matched-market manifest regeneration: **EXACT**
- Violations: **0**

## Frozen protected market coverage

- Protected fixtures: **317**
- Goals total 2.5: **3 valid T-6h comparators**
- Match corners: **3 valid T-6h surfaces**
- Team corners: **0**
- T-6h retained source rows: **58**
- Invalid timestamp rows: **0**

The market-relative protected sample is therefore **extremely underpowered**. The T-6h horizon was not relaxed to increase coverage.

## Boundary

No protected outcome or protected market-relative score has been read. Market evidence has not changed p_model, calibration, model weights, thresholds, bookmaker selection or horizon.
