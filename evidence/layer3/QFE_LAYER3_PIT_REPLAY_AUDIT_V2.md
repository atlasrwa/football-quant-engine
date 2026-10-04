# QFE V2 Layer 3 — PIT Horizon Replay Audit V2

Audit hash: e12e052f2f4a6c2ba109810cbc77dc0d330650a3e7d20b37afe5f71c350dff2a

Status: PASS — DEVELOPMENT REPLAY ONLY

## Integrity
- Chronology reconstructed exactly: PASS
- Corpus manifest unchanged: True
- Fold manifest unchanged: True
- Smallest last-training to first-validation kickoff gap: 16.50h (required >= 12h)
- Calibration rows scored: 0
- Protected rows scored: 0
- Market odds used: False

## Model selection
- Goals intensity: hl360_inf100_tcp04, unchanged.
- Corners intensity: hl180_inf100_tcp04, unchanged.
- Goals Dixon-Coles decision: REJECT_CURRENT_CANDIDATE, unchanged.
- Corners NB2 decision: SELECT_FOR_NEXT_STAGE, unchanged.

## Distribution delta movement
- Goals joint NLL improvement: -0.000216181 -> -0.000170816.
- Goals binary-event LL improvement: -0.000056635 -> -0.000047817.
- Corners joint NLL improvement: +0.088627049 -> +0.088664232.
- Corners binary-event LL improvement: +0.003185703 -> +0.003204547.

## Component evaluation
All 8 candidate decisions are unchanged. The repaired replay preserves the original qualitative Layer 3 conclusions; no tuning, threshold change, or post-result model substitution was performed.

Next gate: replay Layer 3.1 under the repaired PIT semantics.
