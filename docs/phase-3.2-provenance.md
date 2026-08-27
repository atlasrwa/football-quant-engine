# Phase 3.2 Provenance Chain

## Overview

The provenance chain answers: **"Exactly what data and configuration produced this result?"**

```
backtest_runs
    │ content_hash = SHA-256({model_version_id, dataset_id})
    │
    ├──→ model_versions
    │        │ content_hash = SHA-256({strategy_content_hash, feature_version_id,
    │        │                         train_window, test_window, step_size, min_odds, max_odds})
    │        │
    │        ├──→ strategy_versions.content_hash (strategy definition identity)
    │        │
    │        └──→ feature_versions
    │                 │ content_hash = SHA-256({dataset_id, xg_rolling_window,
    │                 │                         form_rolling_window, referee_min_matches,
    │                 │                         xmetric_coefficients})
    │                 │
    │                 └──→ dataset_versions
    │                          │ content_hash = SHA-256(sorted(match_ids))
    │                          │
    │                          └──→ matches (actual data)
    │
    └──→ backtest_bets (individual results)
             └──→ matches (which match each bet references)
```

## Reproducibility Guarantee

Given a `backtest_runs.id`, the system can reconstruct:

1. **WHO** ran it → `user_id`
2. **WHAT strategy** → `strategy_content_hash` → `strategy_versions.definition`
3. **WHAT data** → `dataset_id` → `dataset_versions.match_ids` → `matches`
4. **WHAT features** → `feature_version_id` → feature params (windows, thresholds)
5. **WHAT model config** → `model_version_id` → walk-forward params (train/test/step/odds)
6. **WHAT result** → `total_bets, net_roi_pct, win_rate, ...`
7. **EACH BET** → `backtest_bets` with match_id, odds, outcome, P&L

## Provenance Query

```sql
SELECT
    br.id AS run_id, br.status, br.content_hash AS run_hash,
    br.strategy_id, br.strategy_version, br.strategy_content_hash,
    br.total_bets, br.net_roi_pct, br.win_rate,
    mv.id AS model_version_id, mv.content_hash AS model_hash,
    mv.train_window, mv.test_window, mv.step_size,
    fv.id AS feature_version_id, fv.content_hash AS feature_hash,
    fv.xg_rolling_window, fv.form_rolling_window, fv.referee_min_matches,
    dv.id AS dataset_id, dv.content_hash AS dataset_hash,
    dv.source, dv.league_id, dv.season, dv.n_matches
FROM backtest_runs br
JOIN model_versions mv ON br.model_version_id = mv.id
JOIN feature_versions fv ON br.feature_version_id = fv.id
JOIN dataset_versions dv ON br.dataset_id = dv.id
WHERE br.id = <run_id>;
```

## Deduplication

| Level | Key | Behavior |
|-------|-----|----------|
| Dataset | `content_hash` (sorted match IDs) | Same matches = same dataset, returned from cache |
| Feature | `content_hash` (dataset_id + config) | Same dataset + config = same features |
| Model | `content_hash` (strategy + feature + params) | Same strategy + features + config = same model |
| Backtest | `UNIQUE(user_id, content_hash)` | Same user + same model + dataset = one run |

Different users CAN independently produce identical runs (for verification).
