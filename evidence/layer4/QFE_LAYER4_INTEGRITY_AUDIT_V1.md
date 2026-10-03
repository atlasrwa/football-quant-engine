# QFE V2 Layer 4 — Integrity Audit V1

Audit hash: `78f5925fc6cc1821e35724663da28a91a82390eab02c87cfdb03a0e07ed8b9e2`

Status: **PASS — MERGE READY / PROTECTED UNOPENED / NO MARKET**

## Repository gate

- Full pytest: **298 passed / 0 failed**.
- Research import sweep: **82 modules / 0 failures**.
- `git diff --check`: **PASS**.
- Foundation through Layer 3.1 evidence unchanged from `main`.
- Active legacy-product source references: **0**.

## Calibration selector correctness

Every CALIBRATION_SELECT metric was independently recomputed from the frozen FIT-window calibrator spec with **0 numerical discrepancy**. The frozen selection rule, Brier non-inferiority condition, LL tie tolerance and complexity ordering were reapplied independently.

- Goals: **ISOTONIC_GLOBAL** — SELECT LL 0.677879 identity → 0.671208.
- Corner sides: **PLATT_GLOBAL** — SELECT LL 0.579224 → 0.578956. Ridge L1 had a lower point LL but lay inside the frozen 0.0005 LL tie tolerance, so the simpler Platt mapping correctly wins.
- Corner totals: **PLATT_ROLE_COMP_RIDGE_L1** — SELECT LL 0.618977 → 0.613974.
- Independent final refits reproduce frozen calibrator predictions with max absolute difference **0.0**.

## Monotonicity

- 18,203 calibrated event rows checked.
- 2,874 corner ladders checked.
- Raw ladder violations: **0**.
- Calibrated ladder violations: **0**.
- Malformed ladders: **0**.

## Regeneration / idempotence

- DEVELOPMENT ensemble selection reproduced exactly: `3cf13c8e2e4c625ab8798a7f633fee58dd2ac8e1dd14e718b755c5fae47ef41f`.
- Raw calibration substrate rebuilt from the canonical 5,640-match PIT corpus and reproduced exactly: `94d29f3d396f802049e45b58b45c4115e926ba40d0e715ff27864939a4ec20c4`.
- Raw calibration gzip byte identity: **PASS** (`558f1e3e7f2d39debfa9291e113622dd88088382783797e18987be99f92e8ae8`).
- Calibration run reproduced exactly: `f3770a8bc5fe80c36cb3dcf52d3dc56671bcdfcea3097be5ef17debe278192f2`.
- Calibrated rows gzip byte identity: **PASS** (`fb8389821ac7da2ef6cad4aab9419bbd05a3bda5b50fdae5e03400993c92d7a6`).
- Standalone model freeze reproduced exactly: `e33af913f4c27ce33355c78792419ad8cee73e3f16ce7c685781a010d386b3ea`.
- Freeze code fingerprints: **6 checked / 0 mismatches**.

## Boundary

- CALIBRATION fixtures: **959** = 755 FIT + 204 SELECT.
- Protected rows scored: **0**.
- Market odds used: **0**.
- Protected remains sealed until the Layer 5 market-surface, disagreement, abstention and line-selection policy is frozen.
