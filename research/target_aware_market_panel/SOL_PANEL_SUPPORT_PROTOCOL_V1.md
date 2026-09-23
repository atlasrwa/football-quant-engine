# Sol V1 Panel Support Protocol

**Status:** pre-execution freeze. This protocol is registered after the raw Sol responses and exact-template novelty registry were frozen, and before any panel support result, target label, model fit, OOS score or market result is read.

## Purpose

Instantiate the 124 frozen class-C templates from `SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json` across the already-frozen 5,620-row TheStatsAPI PIT panel and measure only operational support properties:

- non-null feature coverage;
- coverage by competition and frozen time/fold bucket;
- primary-OOS coverage excluding cohort teams;
- similarity-history and neighbour counts;
- neighbour-opponent strength balance relative to all prior opponents;
- style-dimension correlation with separately computed prior team strength;
- feature-feature near-duplicate correlation within model family.

This stage does **not** ask whether a feature predicts an outcome.

## Frozen inputs

- Novelty freeze commit: `b068780497ea59713e268fb272bf44939f83f23e`
- Class-C registry SHA256: `2367b9ea5b3bad10b66c2958599069d574d5bc8c829d6066dc04b75aa069bf1b`
- Sol response manifest SHA256: `79edc665876aca82ba9425eb741d74fa5252722b9b017dd10bf8f37744b46c6a`
- Fold rows SHA256: `9fca0ec2860ed13cda0368502978445b9444419eece690cba685449c26bf3270`
- Panel rows expected: `5620`
- Panel end: `2026-09-14T23:59:59Z`
- Provider cache: `/home/ubuntu/data/thestatsapi/championship`
- Gap-fetch files: excluded from panel support execution, matching the original panel freeze.

## No new feature-selection rule

This stage must not create a post-generation support threshold.

The 124 exact-unique class-C templates remain the frozen candidate family. Diagnostics may label a template `ZERO_SUPPORT`, `GLOBAL_COVERAGE_LT_60_DIAGNOSTIC` or `GLOBAL_COVERAGE_GE_60_DIAGNOSTIC`, but these labels do not alter the registry.

The predictive protocol already froze the actual availability rule:

> a 60% coverage screen fit on the **training rows of each walk-forward fold only**.

That remains the sole coverage gate during M0/M1 fitting. A feature can therefore be available in some folds and unavailable in others without any retrospective whole-panel pruning.

## Similarity support

The frozen panel semantics remain unchanged:

- opponent style profile: last 10 venue-matched matches;
- at least 5 non-null values per style dimension;
- at least 15 prior subject matches with valid candidate profiles/output;
- nearest tercile;
- minimum 5 neighbours;
- shrinkage kappa = 5;
- strength never enters the style distance.

For each similarity template, report the distribution of `n_history` and `n_neighbors` across supported rows.

## Style versus strength

For every opponent-similarity template, report Pearson correlation between each style profile dimension and the separately computed prior same-competition goal-difference strength measure when at least 10 paired observations exist.

Also report, for supported similarity rows, the distribution of:

`mean strength of neighbour opponents - mean strength of all candidate prior opponents`.

These diagnostics are **report-only** and cannot remove or alter a feature at this stage.

## Redundancy

Exact canonical duplicates were already removed by the novelty compiler.

This stage additionally reports feature-value near-duplicates, within model family only:

- minimum overlapping non-null rows: 200;
- report if `|Pearson r| >= 0.95`;
- mark very-near if `|Pearson r| >= 0.99`.

These are report-only. Do not merge, remove, average or rewrite templates after observing these correlations. Regularization and the frozen training-fold coverage screen handle the subsequent model stage.

## Outcome firewall

The support runner must not:

- call target settlement code;
- construct target labels;
- read cohort target outcomes;
- read market results or prices;
- fit M0 or M1;
- run calibration;
- score Log Loss, Brier or ECE;
- execute OOS comparison;
- modify CHAMPION.

Historical provider statistics used to construct PIT features, including historical goals used by the already-frozen strength covariate, are permitted. They are feature history, not the future target labels being evaluated.

## Execution gate

Run once from a clean worktree at the exact support-apparatus commit, supplying that SHA through `--authorized-head`.

The runner fails closed if:

- HEAD differs;
- the worktree is dirty before execution;
- CHAMPION hash differs;
- class-C registry hash differs;
- fold manifest row count/hash differs;
- an expected panel fixture is absent;
- support output files already exist.

No network call or LLM call is required.

## Frozen outputs

The run writes exactly:

- `SOL_PANEL_SUPPORT_DIAGNOSTICS_V1.json`
- `SOL_PANEL_SUPPORT_AUDIT_V1.md`
- `SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1.json`

Commit those generated files unchanged immediately after the run and before any OOS/model execution.

## Next gate

Only after the support outputs are committed and reviewed may the project proceed to the already-frozen walk-forward M0-versus-M1 experiment. No support result may be used to invent a new pruning threshold or modify Sol hypotheses.
