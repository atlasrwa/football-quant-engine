# Phase 3.2 Data Model

## New Tables (7)

### market_prices
Time-series price observations. INSERT-only (historical data never rewritten).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | BIGSERIAL PK | No | |
| match_id | BIGINT FK→matches | No | Surrogate key |
| market_type | TEXT | No | OVER_UNDER, MATCH_RESULT, etc. |
| line | DOUBLE PRECISION | Yes | e.g. 2.5 (NULL for markets without lines) |
| selection | TEXT | No | OVER, UNDER, HOME, DRAW, AWAY, YES, NO |
| price_type | TEXT | No | OPENING, ENTRY, CLOSING, LIVE |
| odds | DOUBLE PRECISION | No | CHECK > 1.0 |
| observed_at | TIMESTAMPTZ | No | Actual observation time |
| source | TEXT | No | pinnacle, bet365, etc. |
| raw_payload | JSONB | Yes | Provider-specific extra data |
| ingested_at | TIMESTAMPTZ | No | DEFAULT NOW() |

**No uniqueness constraint** — allows unlimited time-series observations.

### dataset_versions
Deterministic dataset snapshots. INSERT-only, UNIQUE(content_hash).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID PK | No | gen_random_uuid() |
| source | TEXT | No | footystats, synthetic, mock |
| league_id | INTEGER | No | |
| season | TEXT | No | |
| n_matches | INTEGER | No | CHECK > 0 |
| date_range_start | BIGINT | No | Earliest date_unix |
| date_range_end | BIGINT | No | Latest date_unix |
| content_hash | CHAR(64) | No | SHA-256 of sorted match IDs |
| match_ids | JSONB | No | Sorted array for reproducibility |
| created_by | UUID FK→users | Yes | |
| created_at | TIMESTAMPTZ | No | |

### feature_versions
Feature computation configuration. INSERT-only, UNIQUE(content_hash).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID PK | No | |
| dataset_id | UUID FK→dataset_versions | No | Parent dataset |
| xg_rolling_window | INTEGER | No | CHECK >= 1 |
| form_rolling_window | INTEGER | No | CHECK >= 1 |
| referee_min_matches | INTEGER | No | CHECK >= 1 |
| xmetric_coefficients | JSONB | Yes | NULL = xMetrics not used |
| content_hash | CHAR(64) | No | SHA-256 of config |
| created_by | UUID FK→users | Yes | |
| created_at | TIMESTAMPTZ | No | |

### model_versions
Model/evaluation configuration. INSERT-only, UNIQUE(content_hash).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID PK | No | |
| strategy_id | UUID FK→strategies | No | |
| strategy_version | INTEGER | No | |
| strategy_content_hash | CHAR(64) | No | Links to strategy definition |
| feature_version_id | UUID FK→feature_versions | No | |
| train_window | INTEGER | No | CHECK >= 1 |
| test_window | INTEGER | No | CHECK >= 1 |
| step_size | INTEGER | No | CHECK >= 1 |
| min_odds | DOUBLE PRECISION | No | CHECK > 1.0 |
| max_odds | DOUBLE PRECISION | No | CHECK > min_odds |
| content_hash | CHAR(64) | No | SHA-256 of full config |
| created_by | UUID FK→users | Yes | |
| created_at | TIMESTAMPTZ | No | |

### match_features
Computed feature vectors. INSERT-only, UNIQUE(match_id, feature_version_id).

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | BIGSERIAL PK | No | |
| match_id | BIGINT FK→matches | No | |
| feature_version_id | UUID FK→feature_versions | No | |
| date_unix | BIGINT | No | |
| home_xg_eff_delta_rolling | DOUBLE PRECISION | No | |
| away_xg_eff_delta_rolling | DOUBLE PRECISION | No | |
| home_rolling_form | DOUBLE PRECISION | No | CHECK [0,1] |
| away_rolling_form | DOUBLE PRECISION | No | CHECK [0,1] |
| referee_volatility_index | DOUBLE PRECISION | No | CHECK >= 0 |
| home_xc..away_xo | DOUBLE PRECISION | Yes | xMetric columns |
| total_goals | SMALLINT | No | |
| over_under_line | DOUBLE PRECISION | Yes | |
| over_odds/under_odds | DOUBLE PRECISION | Yes | CHECK > 1.0 or NULL |
| computed_at | TIMESTAMPTZ | No | |

### backtest_runs
User-owned backtest execution records. Lifecycle: RUNNING→COMPLETED/FAILED.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | UUID PK | No | |
| user_id | UUID FK→users | No | Owner |
| strategy_id | UUID FK→strategies | No | |
| strategy_version | INTEGER | No | |
| strategy_content_hash | CHAR(64) | No | |
| dataset_id | UUID FK→dataset_versions | No | |
| feature_version_id | UUID FK→feature_versions | No | |
| model_version_id | UUID FK→model_versions | No | |
| content_hash | CHAR(64) | No | Hash of inputs |
| status | TEXT | No | RUNNING/COMPLETED/FAILED |
| config | JSONB | No | Configuration snapshot |
| total_bets..n_folds | Various | Yes | NULL while RUNNING |
| started_at | TIMESTAMPTZ | No | |
| completed_at | TIMESTAMPTZ | Yes | |
| UNIQUE(user_id, content_hash) | | | Deduplication |

### backtest_bets
Individual bet records. INSERT-only.

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| id | BIGSERIAL PK | No | |
| run_id | UUID FK→backtest_runs | No | ON DELETE CASCADE |
| match_id | BIGINT FK→matches | No | |
| fold_index | INTEGER | No | |
| strategy_name | TEXT | No | |
| direction | TEXT | No | CHECK OVER/UNDER/BACK/LAY |
| odds | DOUBLE PRECISION | No | CHECK > 1.0 |
| stake | DOUBLE PRECISION | No | CHECK > 0 |
| outcome | TEXT | No | CHECK WIN/LOSS/VOID |
| profit_loss | DOUBLE PRECISION | No | |
| model_edge_pct | DOUBLE PRECISION | No | |
| clv_pct | DOUBLE PRECISION | Yes | NULL = unavailable |
| source | TEXT | No | DEFAULT 'BACKTEST' |
| created_at | TIMESTAMPTZ | No | |
