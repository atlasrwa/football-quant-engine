# QFE V2 PIT Horizon Defect — Abort / Version Report

Report hash: `b84c16041c47406b4d4410914b4d59b8966f93d39d27179a9f39b466486614d3`

**Status: CONFIRMED DESIGN DEFECT. Prior dynamic-derived model evidence is preserved but superseded. PROTECTED remains unopened.**

The Foundation PIT builder correctly used `source kickoff + 6h embargo <= target kickoff - 6h horizon`. The dynamic hierarchical walk-forward did not: it updated state immediately after each earlier kickoff.

Development impact under the same frozen configs was small in magnitude but widespread: 76.3% of goals rows and 76.5% of corner rows changed; maximum absolute event-probability changes were 0.323 pp and 0.360 pp respectively.

Scientific action: ABORT affected frozen model evidence, version the dynamic walker, rerun Layers 2–4 under the repaired horizon, and do not open the 317 protected outcomes until the repaired model plus Layer 5 policy are frozen.
