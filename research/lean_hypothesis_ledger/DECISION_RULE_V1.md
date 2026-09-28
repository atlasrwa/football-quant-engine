# Lean Hypothesis Experiment — Decision Rule V1

## Frozen horizon

- Total declared hypotheses required before architecture decision: **40**
- Declared at freeze: **8**
- Remaining: **32**
- Current settlement state at freeze: **6 settled, 2 pending**

## Decision principle

The 40-hypothesis horizon is fixed before observing the remaining outcomes. It must not be shortened, extended, or redefined merely because interim results look favorable or unfavorable.

The experiment asks whether a lean evidence stack — focused pre-match summary statistics, deterministic shrinkage/context, and explicit market hypotheses — produces enough prospective information to justify simplifying the heavier research architecture.

## Evaluation

Raw hit rate is descriptive only and is not the promotion criterion. At the end of the 40 declarations, evaluate where data are available:

- result by market family and threshold;
- timestamped offered price and no-vig market probability;
- calibration / Brier / Log Loss for any deterministic probabilities produced;
- closing-line movement / CLV;
- prospective settlement and P&L;
- failure modes, including team-specific vs match-total hypotheses;
- dependence/correlation between hypotheses from the same fixture.

No post-result rewriting of declarations, rationales, thresholds, prices, or inclusion rules is permitted.
