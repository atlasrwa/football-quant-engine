# QFE V2 Layer 3 — Certification V3

Certification hash: bcceda21ae88e3a94900b07bf973e3286ad3a3de82ef8c3536055609ef4286e5

Status: **PASS — VALID DEVELOPMENT SELECTION EVIDENCE**

## Independence from aborted Layer 2

PR #42 is based historically on the PR #41 merge, but its scientific computation does not consume the Layer 2 evidence artifact. It rebuilds from the canonical corpus, frozen chronology and its own DEVELOPMENT-only selection code.

Layer 2 artifact references in the Layer 3 implementation: **0**.

## Boundary

- WARMUP may update state.
- DEVELOPMENT is the only scored/selection partition.
- CALIBRATION rows scored: **0**.
- Exposed former-PROTECTED rows scored: **0**.
- Market inputs: **none**.
- Network calls: **none**.

## Exact independent regeneration

- Chronology: **EXACT**
- Structured-development tournament: **EXACT**
- Goals DEVELOPMENT OOF: **EXACT — 3,812 rows**
- Corners DEVELOPMENT OOF: **EXACT — 3,783 rows**
- Structured fold OOF: **EXACT — 15,864 rows / 7,950 binary rows**
- Component evaluation: **EXACT**

## Selected intensities

- Goals: hl360_inf100_tcp04, config hash 5d00fdc418b6b66e29253a15acaa091b0e20f4e021a5884d2b75764820bc9e9b
- Corners: hl180_inf100_tcp04, config hash ae4462b7b35b2fb071e9ad0b52c7566988837a1a73d6fb72d5dbae0008e01632

Both selections are unchanged from the pre-repair Layer 3 result. PR #42 did not alter the frozen candidate grid or decision rules after observing repaired outputs.

## Scientific status

Layer 3 is certified for DEVELOPMENT candidate selection only. This does not promote the final model, calibrate probabilities, establish market edge, or restore the exposed 317-fixture cohort as a final holdout.

Next gate: independent audit of merged PR #43 / Layer 3.1.
