# Target-Aware Market Panel V1.2 — Evaluability Repair Protocol

**Status:** pre-execution freeze.  
**Parent V1 decision:** `773b851650410cfeb4a3bff2f08ce3e722017ade`  
**V1 support freeze:** `ac0dc462b7fec730a58e29068682464bfea3d924`

## Purpose

V1.2 repairs one outcome-blind apparatus defect discovered by the frozen V1 support diagnostics: the historical corpus contained effectively no pre-panel feature history (5,640 loaded matches for a 5,620-row scoring panel), while the dominant Sol templates require nested historical warm-up. The frozen 60% training-row coverage gate therefore excluded all 116 opponent-similarity templates in every fold.

V1.2 asks only whether the already-frozen Sol feature family can be **structurally evaluated** when feature construction receives adequate prehistory. It does not change the hypotheses or weaken the predictive protocol.

## Immutable V1 scientific inputs

V1.2 reuses unchanged:

- all 48 raw GPT-5.6 Sol responses;
- the frozen 124 class-C template registry;
- Prompt V2 and output schema;
- target universe and primary lines;
- the exact 5,620 scoring-panel fixture IDs;
- the exact five walk-forward folds and cohort-team flags;
- M0 and M1 model definitions;
- the 60% feature-coverage screen computed on training rows only;
- nested tuning, imputation, scaling, calibration and primary scoring rules;
- CHAMPION.

There are **no new Sol calls** and no hypothesis rewriting.

The 44 V1 value-near-duplicate pairs remain report-only. V1.2 does not add a new deduplication rule, so the repair has one scientific degree of freedom: feature-history prehistory.

## Fixed prehistory buffer

Feature history is extended by exactly **1,095 days** before the earliest frozen panel kickoff.

- Frozen earliest panel kickoff: `2023-08-04T19:00:00Z` (`1691175600`).
- Prehistory start: `2020-08-04T19:00:00Z` (`1596567600`).
- Prehistory end is exclusive at the earliest panel kickoff.
- Provider: **TheStatsAPI only**.
- Competition scope: exactly the unique competition IDs already present in `TARGET_AWARE_FOLD_MANIFEST_V1.json`.
- Fixtures: completed matches only.
- Data types: fixture identity/result fields and historical match statistics required by the already-frozen panel compiler.
- No odds, market prices, lineups, injuries, news or external football information.
- No FootyStats fallback and no cross-provider substitution.
- No dynamic horizon extension inside V1.2.

Every raw prehistory payload must be stored immutably with provider identifiers, retrieval timestamp and SHA256. Conflicting fixture identities or conflicting normalized statistics fail closed.

Historical goals in prehistory are permitted only as historical feature inputs and the frozen strength covariate. They are not V1.2 scoring labels.

## PIT construction

The V1.2 `PanelHistory` may contain:

1. the new frozen prehistory rows; and
2. the original V1 panel-history rows.

For every scored historical fixture at time `t`, every feature calculation may use only rows with kickoff strictly before `t`.

The 5,620 scoring rows themselves do not change. Prehistory rows are **context-only**:

- never assigned an OOS fold;
- never scored;
- never enter Log Loss, Brier or ECE denominators;
- never alter the cohort exclusion set.

## Frozen evaluability preflight

Before any target label is constructed or model is fit, instantiate the unchanged 124 class-C templates using the augmented PIT history and reapply the unchanged 60% training-row coverage rule.

For each family × fold define:

- `active_class_c`: templates passing >=60% non-null coverage on that fold's training rows;
- `active_similarity`: active templates whose type is `OPPONENT_SIMILARITY_CONDITIONAL`;
- `primary_test_exposure`: fraction of that fold's frozen primary-OOS rows on which at least one active class-C feature has a non-null value.

**V1.2 evaluability PASS requires all of the following:**

1. Every one of the four families has at least one active class-C feature in every fold.
2. Every one of the four families has at least one active opponent-similarity feature in every fold.
3. For every family × fold, `primary_test_exposure >= 0.60`.
4. No family × fold has an M1 design that is structurally identical to M0.
5. All frozen upstream hashes, panel IDs, fold assignments and CHAMPION hash match.
6. No target outcome, market result, model fit or OOS score has been accessed.

These are apparatus/evaluability criteria only. They contain no predictive-performance threshold.

If any criterion fails, V1.2 is **ABORTED before outcome access**. The 1,095-day horizon, 60% threshold, folds or pass criteria must not be changed inside V1.2 after observing the preflight.

## Preflight outputs

Freeze before any OOS work:

- `V1_2_PREHISTORY_MANIFEST_V1.json`
- `V1_2_EVALUABILITY_DIAGNOSTICS_V1.json`
- `V1_2_EVALUABILITY_AUDIT_V1.md`
- `V1_2_EVALUABILITY_FREEZE_MANIFEST_V1.json`

The freeze manifest must record whether the gate is PASS or ABORT.

## Outcome firewall

Until the evaluability freeze is committed, V1.2 must not:

- construct or read the frozen panel target labels;
- read market results or prices;
- fit M0 or M1;
- calibrate probabilities;
- score Log Loss, Brier or ECE;
- run prospective/market evaluation;
- change CHAMPION.

## Next gate

Only a frozen `EVALUABILITY_PASS` permits implementation/execution of the already-frozen M0-versus-M1 walk-forward experiment using the same scoring panel and folds.

A PASS means only that the experiment can actually test the Sol feature family. It is not evidence that the features predict outcomes.
