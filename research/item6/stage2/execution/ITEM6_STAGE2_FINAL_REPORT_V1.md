# Item 6 Stage 2 — Final Execution Report

Evaluated at `f85d932` (prediction evidence freeze); evaluation artifacts committed at `51781cf`.

**Stage 2 FAILs its primary gate: the LLM-derived features made goals O/U 2.5 prediction slightly worse, not better.** All four frozen conditions fail. The frozen rule was applied unchanged: no refit, no tuning, one `predict` run. CHAMPION is unchanged and no LLM was called.

**Integrity note.** The first authorized run, at `7783893`, stopped at the executor's parity check before loading any data. That was my executor's false positive, not a design problem. I fixed it in `638f9a5`, smoke-tested it on coin-flip labels, and you re-authorized that commit. The authorized run at `638f9a5` passed every gate.

Hash key: (C) = canonical-JSON hash recorded in the manifests; (F) = file-bytes hash.

```
AUTHORIZED_EXECUTION_HEAD=638f9a5694b527e8db2119514ea0d05e179233fd
EXECUTION_START_HEAD=638f9a5694b527e8db2119514ea0d05e179233fd
EXECUTION_END_HEAD=51781cf5dbb08b560a83eed5aba25a9fc4008733 (pushed; the main checkout was fast-forwarded)

STAGE2_EXECUTION_BINDING_PATH=research/item6/stage2/execution/ITEM6_STAGE2_EXECUTION_BINDING_V1.json
STAGE2_EXECUTION_BINDING_SHA256=2cf25abcb01a13370862cad1fded8547a96dfec79640a3f5d2a5f274234bdf1e (C)
STAGE2_PROTOCOL_SHA256=77384b9b5f3374123dcd01a710c6c09f93a9b1d019a8817c16869e39d58f584f (C)
STAGE2_RUN_MANIFEST_SHA256=a5668e197f7da636e46044be0f51df907501f0a715ad7d676a78ffadf12a81f2 (C); verified by the gate
FOLD_MANIFEST_SHA256=9fc0f2b5c58210d27d57948c17538c6ff3489771473c9d2c369c29b5429141c3 (row-level); 5d5740fb… (C)
CORPUS_DIGEST_SHA256=2bb6cf981b3eaa230684b6bad6636f388cd23bc13b810b67c91a00bae2546ce7
AMBIGUOUS_TEST_FIXTURE_MAPPINGS=0

N_FOLDS_PLANNED=5
N_FOLDS_FIT_M0=5
N_FOLDS_FIT_M1=5
N_FOLDS_SCORED=5 (all 50 fit jobs across all targets and arms: status FIT)
N_OOS_FIXTURES_PLANNED=13012
N_OOS_FIXTURES_M0=13012
N_OOS_FIXTURES_M1=13012
N_PAIRED_OOS_FIXTURES=13012 (0 dropped; PAIRED_OOS_FIXTURES_ONLY=true)
N_M0_FEATURES=72 candidates; after the frozen 60% coverage screen: 48/72/72/72/72 by fold
N_M1_FEATURES=180 candidates; after the screen: 154/168/168/170/170 by fold
N_LLM_FEATURES=108

M0_SELECTED_C_BY_FOLD=0.01,0.01,0.01,0.01,0.03
M1_SELECTED_C_BY_FOLD=0.01,0.03,0.03,0.03,0.01
M0_SELECTED_L1_RATIO_BY_FOLD=0.2,0.2,0.2,0.2,0.8
M1_SELECTED_L1_RATIO_BY_FOLD=0.5,0.8,0.8,0.8,0.5
M0_C_GRID_EDGE_FOLDS=none
M1_C_GRID_EDGE_FOLDS=none (also none for either secondary target)
CONVERGENCE_WARNING_COUNTS_M0=0
CONVERGENCE_WARNING_COUNTS_M1=0 (0 across all 50 fits)
N_LLM_FEATURES_NONZERO_BY_FOLD=14,26,39,46,31
N_LLM_FEATURES_EVER_NONZERO=64 of 108

STAGE2_PREDICTION_EVIDENCE_PATH=research/item6/stage2/execution/ITEM6_STAGE2_OOS_PREDICTIONS_V1.jsonl (130106 rows)
STAGE2_PREDICTION_EVIDENCE_SHA256=75be2e57d9e36fe995b3402b0b986febaf946f87737f81c4c54cfe2482e9e2e2 (F); evidence manifest 678edab0… (C)
STAGE2_PREDICTION_EVIDENCE_FREEZE_COMMIT=f85d932d03ac59f74d64eb503c1f12a485a1e442 (committed before evaluate)

M0_OOS_LOGLOSS=0.683253
M1_OOS_LOGLOSS=0.684076
LOGLOSS_DELTA_M0_MINUS_M1=-0.000823 (negative = M1 worse)
BOOTSTRAP_CI_LOWER=-0.002725
BOOTSTRAP_CI_UPPER=+0.000978
BOOTSTRAP_PRECISION=SE 0.000935 (95 ISO-week blocks, 10000 resamples, seed 0, percentile); one-sided p(delta<=0)=0.81
S2P1_DELTA_POSITIVE=false
S2P2_CI_LOWER_GT_ZERO=false
S2P3_DELTA_GTE_0_001=false
M0_ECE=0.010896
M1_ECE=0.018488
ECE_DELTA=+0.007591 (above the +0.005 allowance)
S2P4_CALIBRATION_PASS=false
ITEM6_STAGE2_PRIMARY_GATE=FAIL

M0_BRIER=0.244610
M1_BRIER=0.244731
BRIER_DELTA=-0.000121 (M1 worse)
RESIDUAL_DEVIANCE_DELTA=-21.42
LLM_FEATURE_SELECTION_STABILITY=mean 0.29 across 108 columns; 6 selected in all 5 folds, 12 in >=80% of folds, 44 never selected

FAMILY_ABLATION_RESULTS= (secondary; BH q=0.10 across 4; all 13012 paired)
  THRESHOLD   40–44 cols  delta -0.002518  CI [-0.004330,-0.000755]  p 0.997  q 0.997  PASS=false (reliably worse)
  MULTIMETRIC 18–20 cols  delta +0.000780  CI [-0.000874,+0.002384]  p 0.166  q 0.664  PASS=false
  HALF_STATE   6–8 cols   delta -0.000102  CI [-0.000866,+0.000660]  p 0.598  q 0.997  PASS=false
  PROFILE     32–36 cols  delta -0.000929  CI [-0.002454,+0.000477]  p 0.894  q 0.997  PASS=false

SECONDARY_TARGET_RESULTS= (secondary; BH across 2)
  corners_9.5  M0 0.689115  M1 0.692783  delta -0.003668  CI [-0.006356,-0.001106]  p 0.9985  q 0.9985  (n=13005; ECE 0.0047 -> 0.0257)
  cards_3.5    M0 0.652207  M1 0.653141  delta -0.000934  CI [-0.002558,+0.000649]  p 0.8756  q 0.9985  (ECE 0.0144 -> 0.0107)

REALIZED_CI_WIDTH=0.003703
CAN_EXCLUDE_ZERO=false
CAN_EXCLUDE_NEGATIVE_0_001=false
CAN_RELIABLY_DETECT_0_001_UNDER_REALIZED_SE=false (power at a true delta of 0.001 is 0.19; 80% power needs about 0.0026)
FAIL_INTERPRETATION=FAIL_AT_FROZEN_GATE_WITH_LIMITED_POWER_AT_0.0010

CALIBRATION_BIN_TABLES=research/item6/stage2/execution/ITEM6_STAGE2_PRIMARY_EVALUATION_V1.json (primary: 2b35bfdf… C / 2c5f04aa… F; secondary: a1b63f8f… C / f43e52c7… F)
CLIPPED_TO_0_01: M0 5, M1 14
CLIPPED_TO_0_99: M0 50, M1 41

STAGE2_OUTCOMES_INSPECTED_BEFORE_FREEZE=false
LIVE_SONNET_CALLS=0
BEDROCK_PAID_CALLS=0
PASS_B_PAID_CALLS=0
NEW_LLM_SPEND_USD=0
CHAMPION_BEFORE=0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
CHAMPION_AFTER=0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9
CHAMPION_UNCHANGED=true
CHAMPION_INDEPENDENT=true

TRUE_INTEGRITY_BLOCKERS_ENCOUNTERED=1 before authorization: the executor's false-positive parity stop at 7783893, before any data access, fixed in 638f9a5 and re-authorized. None during the authorized run.
RUN_STOPPED_EARLY=false
STOP_REASON=n/a
```

1. **Did the LLM-discovered feature universe improve OOS prediction?** No. The gate is FAIL: M1 did worse than M0 on log loss, on Brier and on calibration.

2. **How large was the effect?** The effect was small and in the wrong direction: log loss worsened by 0.00082 nats, about 0.12% of M0's 0.683. For scale, the minimum improvement that would count was +0.0010.

3. **Was it statistically precise?** Not precise enough to rule out zero. The CI is [−0.00272, +0.00098]; it can't exclude a harm of 0.001 nats, and the frozen label is limited power at 0.0010.
   - One further reading, which doesn't change the gate: the CI's upper end (+0.00098) sits just below the 0.0010 minimum. So at 95% the data barely rule out a true benefit of the size that would have counted.

4. **Which structural families contributed?** This is secondary evidence only. No family passes the BH correction.
   - Multimetric interactions are the only family with a positive point estimate (+0.00078), but their CI includes zero (q 0.66).
   - Threshold/nonlinearity features, the largest family, made predictions reliably worse, with a CI entirely below zero.
   - Profile and half-state features were roughly neutral to negative.

5. **Did elastic net actually use the LLM features?** Yes. It kept 14–46 LLM coefficients per fold, 64 distinct columns overall, and 6 in every fold. M1 also picked weaker regularization (C = 0.03 in 3 folds, against M0's 0.01). So the features weren't zeroed out: they were used, and what they added during inner cross-validation didn't carry over out of sample.

6. **Did calibration improve or deteriorate?** It deteriorated. ECE rose from 0.0109 to 0.0185, beyond the frozen +0.005 allowance. M1's predictions are more spread out and overconfident at the extremes: in the top bin they average 0.971 while the observed rate is 0.84. Corners calibration also got much worse (0.0047 to 0.0257); cards improved slightly.

7. **What does this say about the LLM layer?** Stage 1 showed the LLM widens the hypothesis space. Stage 2 finds no incremental predictive value from that widened space for goals O/U 2.5 beyond the champion's baseline features, under this frozen design. This tests only the measurable part of the search space: 90 of 595 mechanisms. 299 of the excluded ones need statistics the FootyStats corpus doesn't record, such as crosses and blocks. The FAIL therefore covers what this data can express, not every idea the LLM proposed.

8. **Next scientific decision:** freeze the failure, with no tuning, feature changes or prompt changes on this cohort. Prospective shadow validation is not eligible on this result. Any new attempt would need a fresh design and a new cohort.

Stopping here.