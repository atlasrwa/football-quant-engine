# Phase 3.2 Preflight Audit

**Date:** 2026-08-24
**Baseline:** 831 tests passing (727 existing + 104 Phase 3.1 integration)

---

## 1. Current Architecture

### Existing Tables (Phase 3.1)
| Table | PK Type | Ownership | RLS Forced |
|-------|---------|-----------|------------|
| users | UUID | Self | Yes |
| user_wallets | UUID | User FK | Yes |
| strategies | UUID | owner_id FK | Yes |
| strategy_versions | UUID | Via strategy | Yes |
| strategy_forks | UUID | forked_by FK | Yes |
| matches | BIGSERIAL | System | Yes |
| event_log | BIGSERIAL | System (append-only) | Yes |
| idempotency_keys | (user_id, key) | User | Yes |

### Key Schema Details
- `matches.match_id` is BIGSERIAL (surrogate), `external_id` is the provider ID
- `strategy_versions.content_hash` is CHAR(64), indexed (non-unique since 0011)
- `strategy_versions` has FK composite `(strategy_id, version)` referenced by forks
- System user UUID: `00000000-0000-0000-0000-000000000001`

---

## 2. Existing Domain Objects (Provenance)

| Object | Location | Hashing Method |
|--------|----------|----------------|
| `DatasetVersion` | `src/domain/provenance.py` | `SHA-256(json.dumps(sorted(match_ids), separators=(",",":" )))` |
| `FeatureVersion` | `src/domain/provenance.py` | `SHA-256(json.dumps({dataset_id, xg_rolling_window, form_rolling_window, referee_min_matches, xmetric_coefficients}, sort_keys=True, separators=(",",":")))` |
| `ModelVersion` | `src/domain/provenance.py` | `SHA-256(json.dumps({strategy_content_hash, feature_version_id, train_window, test_window, step_size, min_odds, max_odds}, sort_keys=True, separators=(",",":")))` |
| `BacktestRun` | `src/domain/backtest_run.py` | `SHA-256(json.dumps({model_version_id, dataset_id}, sort_keys=True, separators=(",",":")))` |

### Key Observations
1. All hashing uses `json.dumps(..., sort_keys=True, separators=(",",":"))` + SHA-256
2. `DatasetVersion.content_hash` hashes **sorted match IDs** (integers) — NOT UUIDs
3. `FeatureVersion.content_hash` includes `dataset_id` (a UUID string) — links to parent
4. `ModelVersion.content_hash` includes `feature_version_id` (UUID string) and `strategy_content_hash`
5. `BacktestRun.content_hash` hashes `model_version_id` + `dataset_id` — both UUID strings

---

## 3. Existing Backtest Models

| Object | Fields | Purpose |
|--------|--------|---------|
| `XBacktestConfig` | train_window, test_window, step_size, base_stake, min_odds, max_odds | Backtest parameters |
| `XBetRecord` | match_index, strategy_name, direction, odds, stake, outcome, profit_loss, model_edge_pct, clv | Single bet |
| `XBacktestResult` | total_bets, total_staked, total_profit_loss, net_roi_pct, avg_model_edge_pct, max_drawdown_pct, win_rate, folds, bet_records, prediction_events | Aggregate result |
| `MatchFeatures` | match_id, date_unix, 5 feature columns, total_goals, over_under_line, odds | Feature vector |

---

## 4. Integration Points

| Engine Component | Persistence Adapter Needed |
|-----------------|---------------------------|
| `FeatureAssembler.assemble()` → `List[MatchFeatures]` | Output → `match_features` table |
| `XMetricBacktester.run()` → `XBacktestResult` | Output → `backtest_runs` + `backtest_bets` |
| Market price ingestion (future) | Input → `market_prices` table |
| `DatasetVersion.compute_content_hash()` | Same algorithm reused in repository |
| `FeatureVersion.compute_content_hash()` | Same algorithm reused in repository |
| `ModelVersion.compute_content_hash()` | Same algorithm reused in repository |
| `BacktestRun.compute_content_hash()` | Same algorithm reused in repository |

---

## 5. Migration Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| FK from new tables to `matches.match_id` (BIGINT) | Low | All new FKs use BIGINT, matching existing PK type |
| FK from `model_versions` to `strategy_versions` | Low | Reference `strategy_versions(strategy_id, version)` composite or just `content_hash` |
| `dataset_versions.content_hash` uses match external_ids (integers) | Medium | Keep using external_ids for hashing (matches engine behavior); store as metadata |
| Large `market_prices` table (millions of rows) | Low | Proper indexing; no heavy constraints |
| RLS on system-owned tables under FORCE | Medium | Use same pattern as `matches`: SELECT for all, INSERT/UPDATE for system only |

---

## 6. RLS Classification (New Tables)

| Table | Class | Read | Write | Rationale |
|-------|-------|------|-------|-----------|
| market_prices | B (System) | All authenticated | System/admin | Market data is public; only ingestion writes |
| dataset_versions | B (System) | All authenticated | System/admin | Datasets are computed by system |
| feature_versions | B (System) | All authenticated | System/admin | Features are computed by system |
| model_versions | B (System) | All authenticated | System/admin | Models are computed by system |
| match_features | B (System) | All authenticated | System/admin | Features are computed by system |
| backtest_runs | D (User+System) | Owner + admin | Owner + admin | User-initiated; results are private |
| backtest_bets | D (User+System) | Via parent run | Via parent run | Inherits from backtest_runs |

---

## 7. Content Hash Design Decision

**Decision:** Reuse the exact hashing algorithms from `src/domain/provenance.py`.

The existing domain objects define canonical hashing. The database repositories will call these same static methods to compute content_hash before INSERT. This guarantees:
- Single source of truth for canonicalization
- Engine and database always agree on identity
- No second incompatible hashing system

---

## 8. Compatibility Risks

| Risk | Resolution |
|------|-----------|
| `MatchFeatures.match_id` is external_id (int), not surrogate | Store both: `match_id` FK (surrogate) + preserve external_id in features payload |
| `XBetRecord.match_index` is a positional index, not a match ID | Store the actual `match_id` (from the DataFrame) alongside the index |
| `BacktestRun` domain uses string UUIDs, DB uses UUID type | Repositories handle UUID↔string conversion transparently |
| Existing provenance hashing includes UUID strings | Preserve: DB stores UUIDs as UUID type but hash computation uses string representation |

---

## 9. Files That WILL Be Modified

| File | Change |
|------|--------|
| `src/persistence/repositories.py` | Add new repository interfaces |
| `src/persistence/__init__.py` | Export new modules |

---

## 10. Files That Will NOT Be Modified

All files in:
- `src/models/` — Domain dataclasses unchanged
- `src/features/` — FeatureAssembler unchanged
- `src/backtest/` — WalkForwardEngine unchanged
- `src/engine/` — XMetricBacktester, evaluator, FDR, etc. unchanged
- `src/domain/` — Provenance objects unchanged (used as-is)
- `src/ingestion/` — Cache/pipeline unchanged
- `src/cli.py` — CLI unchanged
- `src/serializer.py` — Serializer unchanged
- `tests/test_*.py` — All 27 existing test files unchanged
- `tests/conftest.py` — Existing fixtures unchanged
- `src/auth/` — Auth module unchanged
- `src/api/routes/users.py` — User routes unchanged
- `src/api/routes/strategies.py` — Strategy routes unchanged
- `migrations/0001-0012` — Historical migrations unchanged

---

## 11. Blocking Defects

**None found.** Phase 3.1 is stable with 831 tests passing. No data-integrity issues detected.

---

## 12. Proposed Implementation Order

1. `0013_create_market_prices.sql` — Independent, no deps on other new tables
2. `0014_create_dataset_versions.sql` — Independent
3. `0015_create_feature_versions.sql` — Depends on dataset_versions
4. `0016_create_model_versions.sql` — Depends on feature_versions + strategy_versions
5. `0017_create_match_features.sql` — Depends on matches + feature_versions
6. `0018_create_backtest_runs.sql` — Depends on users + model_versions + dataset_versions + feature_versions
7. `0019_create_backtest_bets.sql` — Depends on backtest_runs + matches
8. `0020_create_phase_3_2_indexes_and_constraints.sql` — Post-creation optimization
9. `0021_create_phase_3_2_rls.sql` — Security policies
10. `0022_create_phase_3_2_triggers.sql` — Immutability enforcement
