# QFE V2 Layer 2 — Development Protocol V3

Protocol hash: c86958120caa0770dd995efa0c4fff59ca648b0f03bfd0727c23dbe0d3bd8661

Status: **FROZEN BEFORE REAL-CORPUS V3 METRICS**

This successor exists because PR #41 was aborted for scoring the entire corpus while claiming DEVELOPMENT-only evidence.

## Frozen model

- Dynamic model: repaired T-6h hierarchical baseline.
- Config hash: eeeb5aee69a6a6fc34bfc91a94f6b841c86671910c8099bfdac38eb7c889a881
- Hyperparameters: unchanged from Layer 2 V1/V2.
- Control: identical config with team influence forced to zero.
- No odds, no network calls, no tuning after results.

## Frozen partition contract

- WARMUP: 552 fixtures; state updates allowed; never scored.
- DEVELOPMENT: 3,812 fixtures; state updates allowed; only scored partition.
- CALIBRATION: 959 fixtures; absent from replay model input.
- Exposed former-PROTECTED: 317 fixtures; absent from replay model input.

The model call itself is regression-tested to receive only WARMUP + DEVELOPMENT rows.

## Metrics

The metric family is unchanged: side-count Poisson NLL, MAE, and dynamic-vs-competition-climatology slices.

## Abort rule

If CALIBRATION or the exposed former-PROTECTED cohort enters the real replay input, V3 is aborted. The protocol is not amended after seeing successor metrics.
