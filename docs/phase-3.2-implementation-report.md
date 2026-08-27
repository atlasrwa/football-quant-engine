# Phase 3.2 Implementation Report

## PHASE 3.2 STATUS: COMPLETE

## TEST RESULTS
- Existing: 727/727 PASS
- Phase 3.1: 104/104 PASS
- Phase 3.2: 46/46 PASS
- **Total: 877/877 PASS**

---

## 1. Files Created

### Migrations (10 SQL files)
```
migrations/0013_create_market_prices.sql
migrations/0014_create_dataset_versions.sql
migrations/0015_create_feature_versions.sql
migrations/0016_create_model_versions.sql
migrations/0017_create_match_features.sql
migrations/0018_create_backtest_runs.sql
migrations/0019_create_backtest_bets.sql
migrations/0020_create_phase_3_2_indexes.sql
migrations/0021_create_phase_3_2_rls.sql
migrations/0022_create_phase_3_2_triggers.sql
```

### Repositories (4 Python files)
```
src/persistence/hashing.py
src/persistence/pg_market_price_repository.py
src/persistence/pg_provenance_repository.py
src/persistence/pg_match_features_repository.py
src/persistence/pg_backtest_repository.py
```

### Integration Tests (4 Python files)
```
tests/integration/test_market_prices.py
tests/integration/test_provenance.py
tests/integration/test_backtest_persistence.py
tests/integration/test_hashing.py
```

### Documentation (7 files)
```
docs/phase-3.2-preflight-audit.md
docs/phase-3.2-data-model.md
docs/phase-3.2-provenance.md
docs/phase-3.2-hashing.md
docs/phase-3.2-rls-model.md
docs/phase-3.2-test-matrix.md
docs/phase-3.2-migration-guide.md
```

## 2. Files Modified

**ZERO existing files modified.**

No changes to any file from Phase 3.1 or the original engine.

## 3. Files Intentionally Untouched

All files in:
- `src/models/` — Domain dataclasses
- `src/features/` — FeatureAssembler, all calculators
- `src/backtest/` — WalkForwardEngine, signal, staking
- `src/engine/` — XMetricBacktester, evaluator, FDR, settlement
- `src/domain/` — Provenance objects, PredictionEvent, Settlement
- `src/ingestion/` — Cache, pipeline, client
- `src/auth/` — Auth module
- `src/api/` — API routes and middleware
- `src/cli.py`, `src/serializer.py`
- All existing test files
- All Phase 3.1 migrations (0001-0012)

## 4. Migrations Created

10 migrations (0013-0022), applied in dependency order.

## 5. Tables Created

| Table | Rows (estimated scale) |
|-------|----------------------|
| market_prices | Millions (time-series) |
| dataset_versions | Thousands (snapshots) |
| feature_versions | Thousands (configs) |
| model_versions | Thousands (configs) |
| match_features | Hundreds of thousands |
| backtest_runs | Tens of thousands |
| backtest_bets | Millions |

## 6. Indexes Created

| Index | Table | Purpose |
|-------|-------|---------|
| idx_mp_match_market_time | market_prices | Time-series query |
| idx_mp_source_time | market_prices | Provider queries |
| idx_mp_closing | market_prices | CLV lookup |
| idx_mp_match_type | market_prices | Match+type |
| idx_dv_league_season | dataset_versions | Discovery |
| idx_dv_source | dataset_versions | Source filter |
| idx_dv_hash | dataset_versions | Dedup lookup |
| idx_fv_dataset | feature_versions | Parent lookup |
| idx_fv_hash | feature_versions | Dedup lookup |
| idx_mv_strategy | model_versions | Strategy lookup |
| idx_mv_feature | model_versions | Feature lookup |
| idx_mv_hash | model_versions | Dedup lookup |
| idx_mf_version_date | match_features | Chronological features |
| idx_mf_match | match_features | Match lookup |
| idx_br_user | backtest_runs | User's runs |
| idx_br_strategy | backtest_runs | Strategy runs |
| idx_br_model | backtest_runs | Model runs |
| idx_br_dataset | backtest_runs | Dataset runs |
| idx_br_status | backtest_runs | Active runs |
| idx_br_hash | backtest_runs | Dedup check |
| idx_br_provenance | backtest_runs | Join optimization |
| idx_bb_run | backtest_bets | Bets per run |
| idx_bb_match | backtest_bets | Bets per match |
| idx_bb_run_fold | backtest_bets | Fold-level queries |
| idx_bb_run_outcome | backtest_bets | Outcome analysis |

## 7. RLS Policies

| Table | SELECT | INSERT | UPDATE |
|-------|--------|--------|--------|
| market_prices | All | System | — |
| dataset_versions | All | System | — |
| feature_versions | All | System | — |
| model_versions | All | System | — |
| match_features | All | System | — |
| backtest_runs | Owner/admin | Owner/admin | Owner/admin |
| backtest_bets | Via parent run | Via parent run | — |

All tables: FORCE ROW LEVEL SECURITY enabled.

## 8. Triggers

| Trigger | Table | Action |
|---------|-------|--------|
| trg_mp_no_update/delete | market_prices | INSERT-only |
| trg_dv_no_update/delete | dataset_versions | INSERT-only |
| trg_fv_no_update/delete | feature_versions | INSERT-only |
| trg_mv_no_update/delete | model_versions | INSERT-only |
| trg_mf_no_update/delete | match_features | INSERT-only |
| trg_bb_no_update/delete | backtest_bets | INSERT-only |
| trg_br_lifecycle | backtest_runs | Controlled transitions |
| trg_br_no_delete | backtest_runs | No deletion |

## 9. Repository Implementations

| Repository | Pattern | Key Feature |
|-----------|---------|-------------|
| PgMarketPriceRepository | INSERT-only | Time-series, closing price lookup |
| PgDatasetVersionRepository | INSERT + dedup | ON CONFLICT DO NOTHING, returns existing |
| PgFeatureVersionRepository | INSERT + dedup | Same pattern |
| PgModelVersionRepository | INSERT + dedup | Same pattern |
| PgMatchFeaturesRepository | INSERT + dedup | UNIQUE(match_id, feature_version_id) |
| PgBacktestRunRepository | Lifecycle | RUNNING→COMPLETED/FAILED, provenance query |
| PgBacktestBetRepository | INSERT-only batch | Batch insert for performance |

## 10. Engine Adapters

No direct engine adapters were needed for Phase 3.2. The repositories consume engine output types (`MatchFeatures`, `XBetRecord`) through their public APIs. The engine continues operating unchanged — persistence wraps it from the outside.

## 11. Hashing Implementation

`src/persistence/hashing.py` — single canonical implementation producing results identical to:
- `DatasetVersion.compute_content_hash()`
- `FeatureVersion.compute_content_hash()`
- `ModelVersion.compute_content_hash()`
- `BacktestRun.compute_content_hash()`

Verified by 15 dedicated hashing tests including domain object compatibility checks.

## 12. Provenance Implementation

Full provenance chain queryable via `PgBacktestRunRepository.get_provenance()`:
- Single JOIN query from backtest_run → model → features → dataset
- Returns complete reproducibility metadata
- Tested end-to-end

## 13. Tests Added

46 integration tests across 4 files.

## 14. Existing Tests Executed

877 total (727 existing + 104 Phase 3.1 + 46 Phase 3.2).

## 15. Existing Tests Passed

877/877 (100%).

## 16. Performance Observations

- All 877 tests run in ~34 seconds (including real PostgreSQL I/O)
- Provenance dedup uses content_hash UNIQUE constraints — O(1) lookup
- Time-series queries on market_prices use composite index — efficient range scans
- Backtest bet batch inserts are sequential (could be optimized with COPY in future)

## 17. Compatibility Concerns

- None. All existing engine behavior preserved.
- Hashing utility produces byte-identical results to domain object methods.
- Match features table uses surrogate match_id FK (not external_id) — adapter handles mapping.

## 18. Security Concerns

- All new tables have FORCE RLS — no bypass possible by table owner
- Cross-user isolation verified for backtest_runs and backtest_bets
- INSERT-only enforcement prevents history rewriting
- Content hashes computed server-side only — never client-supplied

## 19. Assumptions

- market_prices are INSERT-only with no operational correction mechanism (corrections = new observation with metadata)
- Dataset version identity is determined solely by sorted match external IDs
- Feature version identity includes dataset_id (UUID string) — changing the dataset UUID changes the feature hash
- Backtest run dedup is per-user: UNIQUE(user_id, content_hash)

## 20. Unresolved Issues

None. All acceptance criteria met.
