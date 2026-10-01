# QFE V3.5 — Cached market replay V1

Status: **CACHE_REPLAY_DIAGNOSTIC / NOT PROSPECTIVE VALIDATION / NO MODEL CHANGE**

Frozen test specification: `4725a5c`  
Frozen replay runner: `ab96521`  
Mixed-corner runtime dispatch fix: `0b8db36`  
V3.5 model artifact: `7c31f2fcbbab0a92d72981bfa6b79a933d61e0a8ea1d2c47715349655a010f0a`

No network calls, no Telegram publication and no ledger mutation were performed.

## Cohort

The replay mechanically selected cached fixtures whose kickoff was strictly after
the final V3.5 training/calibration kickoff (2026-09-29 16:00 UTC), with a cached
Bet365 snapshot strictly before kickoff and a cached final outcome.

- 12 diagnostic fixtures.
- 10 provider match-list `PRIMARY_FINISHED` fixtures.
- 2 supplemental finished-detail fixtures.
- 5 market disagreements passed the frozen V3 thresholds.
- 0 fixtures passed the audited V32.1 official settlement evidence gate because
  the cache did not contain two coherent finished detail snapshots at least four
  hours post-kickoff and five minutes apart.

Therefore all outcome grades below are **NON_LEDGER_DIAGNOSTIC**, not official
settlements.

## Frozen selection thresholds

- selected model probability >= 60%;
- model minus proportional no-vig market probability >= 5 percentage points;
- model probability must beat raw vig-loaded break-even.

## Qualifying disagreements

| Fixture | Market | Model | No-vig market | Delta | Price | Diagnostic result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Slovakia – Kazakhstan | Under 3.5 goals | 68.81% | 62.50% | +6.31 pp | 1.50 | WIN (3 goals) |
| San Marino – Albania | Under 3.5 goals | 77.66% | 51.47% | +26.19 pp | 1.80 | WIN (3 goals) |
| San Marino – Albania | Under 9.5 corners | 62.27% | 53.66% | +8.61 pp | 1.727 | LOSS (11 corners) |
| Czechia – England | Under 3.5 goals | 71.15% | 62.50% | +8.65 pp | 1.50 | WIN (2 goals) |
| New York Red Bulls – St. Louis City | Under 3.5 goals | 61.73% | 51.47% | +10.26 pp | 1.80 | WIN (3 goals; supplemental diagnostic) |

Primary-finished cohort: **3 wins / 1 loss**.  
Including the supplemental New York fixture: **4 wins / 1 loss**.

A normalized one-unit diagnostic grade would be +0.80 units on the primary four
selections and +1.60 units including New York. These are not official ledger P&L.

## Proper-score audit

Hit rate is not the primary quality metric. On all available line observations:

### Primary finished cohort

Goals, 18 line-observations:
- V3.5 goals log loss: **0.578464**
- no-vig market log loss: **0.575447**
- V3.5 goals Brier: **0.195968**
- no-vig market Brier: **0.195027**

The market is marginally better on aggregate proper scores in this tiny primary
sample, despite all three selected goal disagreements winning.

Corners, 10 line-observations:
- mixed V3+pressure log loss: **0.739167**
- V3 parent log loss: **0.734345**
- pressure parent log loss: **0.743667**
- no-vig market log loss: **0.706935**
- mixed Brier: **0.272727**
- V3 parent Brier: **0.269774**
- pressure parent Brier: **0.275116**
- no-vig market Brier: **0.256877**

The corner mix is not validated by this primary cached sample.

### All diagnostic observations

Goals, 22 line-observations:
- V3.5 goals log loss: **0.585768**
- no-vig market log loss: **0.588219**
- V3.5 goals Brier: **0.199072**
- no-vig market Brier: **0.200840**

Corners, 11 graded line-observations:
- mixed log loss: **0.752963**
- V3 parent: **0.753670**
- pressure parent: **0.751322**
- no-vig market: **0.709343**

The all-diagnostic goals result reverses the primary comparison slightly, which
is exactly why the sample is too small to support a model claim.

## Corner-stack counterfactual

At the frozen selection thresholds:

- V3 corner parent alone would have generated 2 qualifying cached selections,
  both diagnostic losses.
- pressure parent alone generated 0 qualifying selections.
- mixed V3+pressure generated 1 qualifying selection, a diagnostic loss.

The mix suppressed New York Red Bulls – St. Louis City O9.5, which V3 alone
would have selected and lost. But it retained San Marino – Albania U9.5, which
also lost. This is consistent with the calibration motivation for stacking but
does not establish positive OOS value.

## Threshold discipline observations

Several attractive-looking raw disagreements were correctly rejected because
the selected model probability was below 60% or the no-vig delta was below 5 pp.

Examples:
- San Marino–Albania U2.5 goals had a very large market delta but only 56.7%
  model probability; it would have lost at exactly 3 goals.
- Bulgaria–Estonia O2.5 and Slovenia–North Macedonia O2.5 had >5 pp market
  disagreement but model probability below 50%; both would have lost.
- Spain–Croatia U3.5 reached 60.5% model probability but only +4.74 pp no-vig
  disagreement, just below the frozen 5 pp gate; it lost with 5 goals.

This small replay supports retaining both gates rather than selecting on
disagreement magnitude alone.

## Support / abstention behavior

Deportivo Pereira – Independiente Santa Fe correctly abstained from the goals
model because the home-at-home / away-away venue history did not satisfy the
V3.5 support requirement. Its corner model remained supported.

Atlético Nacional – Junior Barranquilla had a supplemental final goal score but
no cached finished corner-stat payload, so its corner outcome was not graded.

## Decision

1. **Do not promote, demote or retune either model from this replay.**
2. Keep `V35_GOALS_VENUE_DEEP_POISSON` as the selected goals prospective
   shadow model.
3. Keep `V35_CORNERS_V3_PRESSURE_STACK` as a corner shadow challenger, not a
   confirmed production upgrade.
4. Keep the frozen 60% probability and +5 pp no-vig disagreement gates.
5. Require genuine future freezes and the V32.1 stable settlement gate before
   these outcomes enter the prospective ledger.
6. Evaluate new prospective evidence primarily with log loss, Brier,
   calibration and market/close comparison rather than cached hit rate.
