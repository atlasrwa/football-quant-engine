# Phase 3.2 Migration Guide

## Prerequisites

Phase 3.1 must be fully applied (migrations 0001-0012).

## Running Migrations

```bash
cd /home/ubuntu
.venv/bin/python migrations/run_migrations.py
```

## Migration Order

| # | File | Creates | Depends On |
|---|------|---------|------------|
| 0013 | create_market_prices.sql | market_prices | matches |
| 0014 | create_dataset_versions.sql | dataset_versions | users |
| 0015 | create_feature_versions.sql | feature_versions | dataset_versions |
| 0016 | create_model_versions.sql | model_versions | feature_versions, strategy_versions |
| 0017 | create_match_features.sql | match_features | matches, feature_versions |
| 0018 | create_backtest_runs.sql | backtest_runs | users, strategies, dataset/feature/model_versions |
| 0019 | create_backtest_bets.sql | backtest_bets | backtest_runs, matches |
| 0020 | create_phase_3_2_indexes.sql | Performance indexes | All Phase 3.2 tables |
| 0021 | create_phase_3_2_rls.sql | RLS policies | All Phase 3.2 tables |
| 0022 | create_phase_3_2_triggers.sql | Immutability triggers | All Phase 3.2 tables |

## Verification

```bash
# Check tables exist
psql "postgresql://fqe_app:fqe_dev_password@localhost/football_quant_engine" -c "\dt"

# Expect 16 tables: 9 from Phase 3.1 + 7 from Phase 3.2

# Check RLS is forced on new tables
psql "..." -c "SELECT relname, relforcerowsecurity FROM pg_class
               WHERE relname IN ('market_prices','dataset_versions','feature_versions',
                                  'model_versions','match_features','backtest_runs','backtest_bets');"

# Run all tests
.venv/bin/python -m pytest tests/ -q
# Expected: 877 passed
```

## Rollback Considerations

Migrations are forward-only. To rollback Phase 3.2:

```sql
-- WARNING: This drops all Phase 3.2 data permanently
DROP TABLE IF EXISTS backtest_bets CASCADE;
DROP TABLE IF EXISTS backtest_runs CASCADE;
DROP TABLE IF EXISTS match_features CASCADE;
DROP TABLE IF EXISTS model_versions CASCADE;
DROP TABLE IF EXISTS feature_versions CASCADE;
DROP TABLE IF EXISTS dataset_versions CASCADE;
DROP TABLE IF EXISTS market_prices CASCADE;
DELETE FROM _migrations WHERE filename LIKE '001[3-9]%' OR filename LIKE '002[0-2]%';
```

## Performance Considerations

- `market_prices` may grow to millions of rows. Indexed by `(match_id, market_type, selection, observed_at)` for efficient time-series queries.
- `backtest_bets` may grow to millions of rows. Primary access pattern is by `run_id` (indexed).
- `match_features` has UNIQUE(match_id, feature_version_id) preventing accidental re-computation.
- Provenance tables (dataset/feature/model_versions) are small (thousands of rows) — UNIQUE on content_hash provides fast dedup.
- No table partitioning needed at current scale. Consider partitioning `market_prices` and `backtest_bets` by date if exceeding 10M rows.
