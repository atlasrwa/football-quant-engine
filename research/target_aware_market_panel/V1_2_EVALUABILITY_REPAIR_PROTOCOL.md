# Target-Aware Market Panel V1.2 — Evaluability Repair Protocol

**Status:** pre-execution, outcome-blind protocol.

**Parent V1 gate decision:** `773b851650410cfeb4a3bff2f08ce3e722017ade`

V1 remains frozen. V1.2 is a new experiment whose only purpose is to repair the structural warm-up defect discovered before outcome access.

## 1. Why V1.2 exists

The frozen V1 support run established:

- 124 / 124 class-C templates have some historical support;
- 116 / 124 are `OPPONENT_SIMILARITY_CONDITIONAL`;
- 0 / 116 similarity templates pass the frozen 60% **training-row** coverage screen in any V1 fold;
- later panel segments nevertheless show broad similarity support.

V1 predictive OOS was therefore aborted before labels/model fitting because the dominant generated feature class would not enter M1.

This is an apparatus/evaluability defect, not a predictive result.

## 2. Repair principle

V1.2 will **not** lower or redefine the 60% training-row coverage screen.

The first repair attempt is provider-consistent **prehistory extension** only.

The scored population, folds, targets and model remain unchanged. Additional TheStatsAPI history may be used only to construct PIT features before the already-frozen scoring fixtures.

This preserves the original estimand while separating genuine feature missingness from insufficient historical burn-in.

## 3. Immutable V1 inputs

V1.2 must not modify:

- the 48 frozen GPT-5.6 Sol raw responses;
- Prompt V2;
- the target universe or primary lines;
- the 124 frozen class-C templates;
- any feature-template semantics;
- similarity parameters:
  - profile window = 10 venue-matched matches;
  - minimum 5 valid observations per profile dimension;
  - minimum 15 valid prior subject matches;
  - nearest tercile;
  - minimum 5 neighbours;
  - shrinkage kappa = 5;
- the 5,620 scored panel rows;
- the five frozen walk-forward fold boundaries;
- the cohort-team exclusion / primary scoring set;
- M0 or M1 model classes;
- hyperparameter grids;
- calibration;
- the 60% training-row coverage screen;
- CHAMPION.

No Sol regeneration is permitted.

## 4. Allowed new information

Only historical TheStatsAPI fixture/stat data strictly prior to the original scoring history for the relevant competition may be added as feature-construction prehistory.

The repair uses **exactly two complete provider seasons immediately preceding the earliest scored season for each competition in the frozen panel**.

No adaptive expansion to a third season is permitted after support is observed. If two seasons are unavailable or insufficient, this V1.2 repair fails and a new version must be designed.

Allowed endpoints/data:

- competition/season metadata needed to identify the two prior seasons;
- finished fixtures in those seasons;
- the same TheStatsAPI statistical fields already allowed by V1.

Forbidden:

- FootyStats substitution;
- odds or prices;
- market results;
- lineups/injuries;
- cohort target outcomes;
- any fixture/stat observation at or after that competition's first frozen scoring fixture when collected specifically for backfill.

Raw provider payloads must be stored immutably and hashed before support recomputation.

## 5. Scope preservation

Backfill rows are **history-only**.

They may enter `PanelHistory` when computing features for a frozen scoring fixture, but they:

- are not added to the 5,620 model/scoring rows;
- receive no OOS designation;
- are not target-settled;
- are not scored;
- do not alter fold boundaries;
- do not alter competition weights or the primary scoring population.

## 6. Deterministic backfill selection

For every competition represented in `TARGET_AWARE_FOLD_MANIFEST_V1.json`:

1. determine the earliest frozen scoring fixture and its provider `season_id`;
2. use provider season metadata to identify the two immediately preceding complete seasons;
3. require every backfill fixture to have kickoff strictly before that competition's earliest frozen scoring fixture;
4. fetch/store all finished fixtures and required stats for those two seasons under a new V1.2 cache namespace;
5. freeze competition ids, season ids, request provenance and payload SHA256s before recomputing any support statistic.

If the provider cannot supply two complete prior seasons for any frozen-panel competition, V1.2 fails closed. Do not silently drop that competition and do not substitute another provider.

## 7. Recomputed support

After the prehistory manifest is frozen, rerun the same 124 templates on:

**V1.2 PanelHistory = frozen V1 history + frozen V1.2 prehistory**

while keeping the scored rows and fold manifest byte-identical to V1.

The V1.2 support artifact must report, for every template and fold, the unchanged 60% training-row coverage decision.

## 8. Evaluability gate

V1.2 predictive OOS is authorized only if, **before target-label construction**:

1. every one of the four families has at least one class-C feature passing the unchanged 60% training-row coverage screen in **every** frozen fold; and
2. every family has at least one `OPPONENT_SIMILARITY_CONDITIONAL` feature passing that screen in **every** frozen fold.

This is a logical evaluability gate, not a predictive-performance threshold. It ensures M1 can actually differ from M0 and that the dominant Sol hypothesis class is exercised throughout the experiment.

Feature-value correlations and the 44 V1 very-near duplicate pairs remain report-only in V1.2. Do not prune them in this repair; changing deduplication simultaneously would confound the warm-up repair.

If the evaluability gate fails:

- do not lower 60%;
- do not move folds;
- do not remove early rows;
- do not add a third historical season;
- do not rewrite Sol hypotheses;
- do not run OOS.

Abort V1.2 and design a separately frozen mature-history/population experiment.

## 9. Outcome firewall

Until the V1.2 evaluability gate passes and its artifacts are frozen:

- no target settlement;
- no target label construction;
- no M0/M1 fit;
- no calibration;
- no Log Loss/Brier/ECE;
- no market comparison;
- no prices;
- no prospective promotion;
- no CHAMPION modification.

Historical goals/cards/corners from backfill fixtures are permitted only as earlier feature history.

## 10. Execution sequence

1. Run `v1_2_prehistory_inventory.py` from a clean worktree at its exact authorized HEAD.
2. Freeze the local inventory before any provider backfill request.
3. Freeze the exact two-season-per-competition backfill plan.
4. Acquire and hash only that backfill.
5. Freeze a prehistory manifest.
6. Recompute support with scored rows/folds unchanged.
7. Apply the evaluability gate above.
8. Freeze PASS or ABORT.
9. Only a PASS may authorize V1.2 predictive OOS.

The objective is not to make Sol pass. The objective is to ensure the frozen hypothesis class is genuinely testable before predictive evidence is examined.
