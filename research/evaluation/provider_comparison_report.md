# Provider Comparison Experiment — FootyStats vs TheStatsAPI

**Status: evaluation only. The champion model was not modified and nothing here
is promoted to production.**

Baseline: `main` @ `9854363` (includes PR #3 dual-provider infrastructure).
Branch: `experiment/provider-comparison`. Machine-readable results:
`provider_comparison_report.json` (same directory).

## Headline

On the available historical data, **no provider or reconciliation policy
credibly beats the FootyStats baseline** for the markets the champion supports
(corners totals, cards totals). Every head-to-head comparison is classified
**INSUFFICIENT_EVIDENCE**: the paired 95% confidence intervals for the metric
difference all span zero. This is the honest result — not a manufactured winner.

## Dataset

- League/seasons: England Premier League, 2024/2025 and 2025/2026
  (TheStatsAPI `sn_3057848`, `sn_6125938`).
- **546** fixtures canonically joined FootyStats ↔ TheStatsAPI, **100% final-score
  agreement**, **0 ambiguous** joins. ~466 evaluated after the walk-forward warm-up.
- Identity: high-confidence (≥0.9) team maps only — **18/20** EPL teams admitted;
  2 excluded (Leicester, West Ham) because the legacy crosswalk mapped them to the
  wrong TheStatsAPI team by name similarity. No fuzzy matching in the comparison.

## Point-in-time support (what the data can and cannot prove)

- **Fixture-date walk-forward: SUPPORTED.** Features use only prior completed
  fixtures (strict `date_unix < kickoff`), exactly as the champion does.
- **EARLY (T-24h) / LATE (T-60m) stat vintages: UNSUPPORTED.** Provider stat
  payloads carry no capture timestamp, so a T-24h vs T-60m assignment cannot be
  proven — it fails closed.
- **Genuine closing / CLV: UNSUPPORTED.** The only genuinely-timestamped odds
  captures (82 matches) do not overlap the fixtures that have stats. The market
  benchmark therefore uses **pre-match de-vigged odds only**; no `last_seen` value
  is treated as a genuine close.

## Provider agreement (coverage & disagreement)

Where both providers report a concept (Pearson correlation):

| concept | corr | verdict |
|---|---|---|
| total_goals | 1.00 | identical |
| possession | 0.999 | identical |
| shots_on_target | 0.994 | identical |
| total_corners | 0.996 | identical |
| total_cards | 0.988 | near-identical (22 TSA fixtures have null reds → left NULL, not 0) |
| shots | 0.80 | **genuinely different** (MAD 2.24; different shot definition) |
| xg | 0.55 | **genuinely different** (MAD 0.69; different xG models) |

Implication: for goals/corners/cards/SoT/possession the providers are
interchangeable, so provider choice can only move forecasts through **shots**
(and xG, which the corners/cards champion does not use). Small effect sizes are
therefore expected a priori.

## Predictive results (pooled arm)

Aggregate Brier over all lines (lower is better); base rates ~0.5–0.56.

| market | footystats_only | thestatsapi_only | preferred_fallback | validated_blend |
|---|---|---|---|---|
| CORNERS_TOTAL | 0.2408 | 0.2424 | 0.2408 | 0.2455 |
| CARDS_TOTAL | 0.2457 | 0.2439 | 0.2457 | 0.2474 |

Note the **direction flips by market**: FootyStats is nominally better on corners,
TheStatsAPI nominally better on cards — consistent with noise, and neither is
credible (see uncertainty).

### Paired uncertainty (block bootstrap, arm − baseline; <0 means arm better)

- Corners, TheStatsAPI-only − FootyStats: **+0.0016**, 95% CI **[−0.0010, +0.0043]** → spans zero.
- Cards, TheStatsAPI-only − FootyStats: small, 95% CI spans zero.
- All four policies × two markets: **INSUFFICIENT_EVIDENCE**.

Correlated O/U lines within a fixture are collapsed to one observation before
bootstrapping, so they are not counted as independent evidence. Blocks are over
chronological fixtures (~√n length) to respect temporal dependence.

## Market benchmark

On corners, the champion (Brier 0.2408) is **slightly worse than the de-vigged
pre-match market** (0.2380); P(model better) ≈ 0.19. Both provider arms barely
beat climatology (Brier Skill Score ≈ 0.02). Bookmaker odds were never fed into
the model.

## Provider value decomposition

- **Coverage value: ~0.** FootyStats has complete EPL coverage, so TheStatsAPI
  fills nothing (fallback rate 0.0).
- **New-feature value (FootyStats-only dangerous_attacks/attacks): not helpful**
  here (paired diff +0.0038, P(helpful) 0.03).
- **Replacement value:** swapping the provider's overlapping stats does not
  credibly change corners/cards forecasts (CIs span zero).

## Recommendations (per market / policy)

| market | comparison | classification |
|---|---|---|
| CORNERS_TOTAL | thestatsapi_only vs footystats_only | INSUFFICIENT_EVIDENCE |
| CORNERS_TOTAL | preferred_fallback vs footystats_only | INSUFFICIENT_EVIDENCE |
| CORNERS_TOTAL | validated_blend vs footystats_only | INSUFFICIENT_EVIDENCE |
| CARDS_TOTAL | thestatsapi_only vs footystats_only | INSUFFICIENT_EVIDENCE |
| CARDS_TOTAL | preferred_fallback vs footystats_only | INSUFFICIENT_EVIDENCE |
| CARDS_TOTAL | validated_blend vs footystats_only | INSUFFICIENT_EVIDENCE |

**Keep the FootyStats baseline.** No PROMOTE_CANDIDATE. TheStatsAPI remains
valuable as the dual-provider infrastructure it was built to be (cross-checking,
future closing-odds capture, coverage insurance), but this experiment provides no
empirical basis to change the champion's inputs.

## Known limitations

- Single league (EPL), two seasons — not robust across leagues/seasons.
- No genuine closing odds and no per-observation stat timestamps on this dataset.
- Effect sizes are inherently small because the providers agree on the outcome
  stats and on most feature stats.
- Team identity restricted to high-confidence maps; a fuller comparison needs a
  validated, non-fuzzy fixture/team crosswalk.

## How to reproduce

```python
from src.research.experiments.provider_comparison.runner import run_experiment
report = run_experiment()  # deterministic (fixed seed 12345)
```
