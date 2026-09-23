# Target-Aware Market Panel V1.2 — Evaluability Repair Plan

**Status:** notes-only planning artifact. Not an execution freeze. No target outcomes, market results, model fit, calibration, or OOS are permitted by this file.

## Parent evidence

- V1 gate-decision head: `773b851650410cfeb4a3bff2f08ce3e722017ade`
- V1 support freeze head: `ac0dc462b7fec730a58e29068682464bfea3d924`
- V1 support diagnostics: 124/124 class-C templates have nonzero support, but the frozen 60% training-row screen admits none of the 116 opponent-similarity templates in any fold.
- The support runner loaded 5,640 historical matches for a 5,620-row scoring panel: effectively no dedicated pre-panel warm-up corpus.
- V1 remains immutable. Do not lower its 60% threshold, alter its 124 templates, move its folds, or run its predictive OOS stage.

## V1.2 mission

Repair **evaluability**, not predictive performance.

The first-choice repair is additional historical prehistory for feature construction. The 5,620 V1 scoring rows, Sol responses, class-C templates, target definitions, and numerical firewall are not changed merely to improve an eventual result.

A structural-maturity denominator or changed scoring folds may be considered only if provider-safe prehistory cannot solve the warm-up defect, and only in a separately frozen design before labels are read.

## Stage A — offline prehistory feasibility

No network calls.

For the six V1 panel competitions:

- `comp_0256`
- `comp_0976`
- `comp_3039`
- `comp_8321`
- `comp_8814`
- `comp_9777`

inventory the existing TheStatsAPI cache and report, without constructing any target label:

1. earliest stats-backed historical kickoff per competition;
2. seasons already cached per competition;
3. finished pre-panel fixtures and stats coverage before each competition's first V1 panel row;
4. per-team and per-venue prehistory counts at the V1 panel start;
5. whether existing cached prehistory is sufficient for the frozen similarity prerequisites;
6. the exact historical deficit by competition/team if it is not.

This stage reads only provider fixture/history data needed for feature support. It must not call settlement code, market data, OOS scoring, or model fitting.

## Stage B — bounded provider discovery

Only if Stage A confirms missing prehistory.

Use the already-verified TheStatsAPI endpoints:

- `COMPETITION_SEASONS`
- `MATCHES`

First perform a quota-bounded discovery pass only:

1. enumerate prior provider seasons for the six competitions;
2. identify the immediately preceding season(s) needed for warm-up;
3. count finished fixtures/pages before downloading per-match stats;
4. freeze an exact backfill request manifest and expected request budget.

Do not fetch odds, lineups, injuries, or market data.

## Stage C — immutable prehistory backfill

After the Stage-B manifest is frozen:

- fetch only the frozen finished fixtures and their match-stat payloads;
- store them in a separate V1.2 prehistory namespace; do not mutate the V1 cache in place;
- retain provider ids, retrieval provenance, raw payload hashes, and missingness;
- NULL remains missing; no cross-provider substitution;
- do not use gap-fetch files unless explicitly frozen in the V1.2 protocol.

## Stage D — outcome-blind evaluability rerun

Re-instantiate the same frozen 124 class-C templates on the same V1 scoring panel using the V1.2 prehistory extension.

Recompute:

- training-fold coverage under the existing 60% rule;
- per-family/fold number of eligible class-C columns;
- similarity history/neighbour support;
- exact/value duplicate structure;
- feature availability by chronological fold.

No target labels or scores are read.

The V1.2 apparatus is eligible for a new predictive experiment only after an explicit evaluability gate is frozen from support-only evidence. If the intended Sol feature class is still not materially exercised, abort again rather than weaken the rule after seeing predictive results.

## Anti-drift

V1.2 must not:

- change Sol's raw V1 responses;
- rewrite the 124 frozen class-C templates;
- make the LLM a predictor;
- use market prices or outcomes to choose prehistory;
- lower V1's threshold retroactively;
- modify CHAMPION;
- claim predictive value from support.

## Current next action

Run Stage A from a clean V1.2 worktree when the authorized Ubuntu relay is online.
