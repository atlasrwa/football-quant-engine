# QFE V2 Layer 2 — PR #41 Certification Audit / ABORT V3

Audit hash: `7720a60571af2dc7c2023f49936191cb274b25df63bb79e2129532ab2b07b78e`

Status: **ABORT — SCIENTIFIC BOUNDARY VIOLATION**

## What passed

- PR #41 replay commit `687fefa833a6308d22609f2bc0c907bbdd462e14` is a direct child of the repaired PR #40 merge.
- Dynamic configuration hash remained `eeeb5aee69a6a6fc34bfc91a94f6b841c86671910c8099bfdac38eb7c889a881`.
- The model version is the repaired T-6h dynamic baseline.
- No market odds are inputs.
- The replay did not change hyperparameters or selection thresholds.

## Blocking defect

`layer2_report.py` calls the dynamic walk-forward and then `target.observed_counts(match)` over the complete 5,640-fixture corpus.

Frozen chronology membership is:

- WARMUP: **552**
- DEVELOPMENT: **3,812**
- CALIBRATION: **959**
- PROTECTED: **317**

These sum to exactly **5,640**, the Layer 2 prediction count.

Therefore both the original Layer 2 V1 artifact and PR #41 V2 replay read/scored CALIBRATION and the later-designated PROTECTED outcomes. The V2 replay audit fields `calibration_outcomes_used=false` and `protected_outcomes_read=false` are contradicted by the committed code and artifact counts.

Because walk-forward receives the full corpus, earlier protected outcomes can also update dynamic state for later protected fixtures under the repaired availability gate.

## Timeline

- Layer 2 V1 committed: **2026-10-02 13:20:35 UTC**
- Chronology partitions frozen: **2026-10-02 23:21:05 UTC**
- Protected protocol V1 frozen: **2026-10-03 23:56:28 UTC**
- Repaired Layer 2 replay committed: **2026-10-04 02:48:46 UTC**

The 317-fixture cohort was designated protected only after its outcomes had already contributed to committed Layer 2 evidence. Protection cannot be retroactive.

## Scientific consequence

- PR #41 is **not certifiable** as DEVELOPMENT-only evidence.
- The original Layer 2 V1 artifact is historical/exposed evidence only.
- The 317-fixture membership may remain as an exposed diagnostic cohort, but it is **not a pristine protected holdout**.
- No final protected/OOS claim may use that cohort.
- A genuine final holdout must be a **new prospective, outcome-blind cohort created only after the complete repaired model stack is frozen**.

## Next gate

Freeze Layer 2 V3 before observing its successor metrics:

- WARMUP may update state;
- only DEVELOPMENT may be scored;
- CALIBRATION and PROTECTED must be absent from the Layer 2 replay input;
- config remains unchanged;
- no market inputs;
- no post-result retuning.
