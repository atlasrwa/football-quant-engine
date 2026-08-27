# Phase 3.3 Pre-Implementation Audit

**Date:** 2026-08-24
**Baseline:** 877 tests passing (727 existing + 104 Phase 3.1 + 46 Phase 3.2)
**Highest migration:** 0022_create_phase_3_2_triggers.sql → Next: 0023

---

## 1. Current State

### Tables (16)
users, user_wallets, strategies, strategy_versions, strategy_forks, matches, event_log, idempotency_keys, market_prices, dataset_versions, feature_versions, model_versions, match_features, backtest_runs, backtest_bets, _migrations

### Domain Objects to Map

| Object | Location | DB Table (Phase 3.3) |
|--------|----------|---------------------|
| `PredictionEvent` | src/domain/prediction.py | predictions |
| `PredictionStatus` | src/domain/prediction.py | predictions.status |
| `PredictionSource` | src/domain/prediction.py | predictions.source |
| `Settlement` | src/domain/settlement.py | settlements |
| `SettlementOutcome` | src/domain/settlement.py | settlements.outcome |
| `QuarantineEntry` | src/engine/fdr.py | quarantine_entries |
| `QuarantineStatus` | src/engine/fdr.py | quarantine_entries.status |
| `ValidationVerdict` | src/engine/validator.py | validation_runs |

### Key Domain Methods (NOT to modify)
- `PredictionEvent.compute_proof_hash()` — server-side proof computation
- `SettlementFactory.settle_prediction()` — outcome resolution
- `SettlementFactory._resolve_outcome()` — WIN/LOSS/VOID/PUSH determination
- `Settlement.compute_clv()` — CLV from entry/closing odds
- `Settlement.compute_profit_loss()` — P&L calculation
- `QuarantineTracker` — 90-day lifecycle
- `StatisticalValidator.validate()` — three-gate validation

---

## 2. PredictionEvent Field Mapping

| Domain Field | DB Column | Type | Notes |
|--------------|-----------|------|-------|
| prediction_id | id | UUID PK | |
| user_id | user_id | UUID FK→users | NEW (not in domain) |
| strategy_id | strategy_id | UUID FK→strategies | |
| strategy_version | strategy_version | INTEGER | |
| strategy_content_hash | strategy_content_hash | CHAR(64) | |
| model_version_id | model_version_id | UUID FK→model_versions | nullable |
| match_id | match_id | BIGINT FK→matches | surrogate |
| match_date_unix | match_date_unix | BIGINT | |
| home_team | home_team | TEXT | |
| away_team | away_team | TEXT | |
| league_id | league_id | INTEGER | |
| market_type | market_type | TEXT | |
| market_line | market_line | DOUBLE PRECISION | nullable |
| direction | direction | TEXT | CHECK |
| entry_odds | entry_odds | DOUBLE PRECISION | CHECK >1.0 OR NULL |
| model_edge_pct | model_edge_pct | DOUBLE PRECISION | |
| confidence | confidence | DOUBLE PRECISION | CHECK [0,100] |
| recommended_stake | recommended_stake | DOUBLE PRECISION | CHECK >=0 |
| source | source | TEXT | CHECK BACKTEST/LIVE_SIGNAL/PAPER_TRADE |
| status | status | TEXT | CHECK PENDING/SETTLED_WIN/SETTLED_LOSS/SETTLED_VOID/EXPIRED |
| proof_hash | proof_hash | CHAR(64) | server-computed |
| created_at | created_at | TIMESTAMPTZ | |
| settled_at | settled_at | TIMESTAMPTZ | nullable |

---

## 3. Settlement Field Mapping

| Domain Field | DB Column | Type | Notes |
|--------------|-----------|------|-------|
| settlement_id | id | UUID PK | |
| prediction_id | prediction_id | UUID UNIQUE FK→predictions | |
| match_id | match_id | BIGINT FK→matches | |
| outcome | outcome | TEXT | CHECK WIN/LOSS/VOID/PUSH |
| actual_total_goals | actual_total_goals | SMALLINT | |
| actual_result | actual_result | TEXT | e.g. "2-1" |
| entry_odds | entry_odds | DOUBLE PRECISION | from prediction |
| closing_odds | closing_odds | DOUBLE PRECISION | from market_prices |
| clv_pct | clv_pct | DOUBLE PRECISION | nullable |
| stake | stake | DOUBLE PRECISION | CHECK >=0 |
| profit_loss | profit_loss | DOUBLE PRECISION | |
| settled_at | settled_at | TIMESTAMPTZ | |

---

## 4. Migration Plan (0023-0033)

| # | Table | Class | Depends |
|---|-------|-------|---------|
| 0023 | predictions | D (User+System) | users, strategies, strategy_versions, matches, model_versions |
| 0024 | settlements | D (User+System) | predictions, matches |
| 0025 | paper_portfolios | A (User) | users |
| 0026 | paper_ledger_entries | A (User) | paper_portfolios, predictions, settlements |
| 0027 | quarantine_entries | D (User+System) | strategies, strategy_versions, users |
| 0028 | validation_runs | D (User+System) | backtest_runs, strategies, strategy_versions |
| 0029 | follows | A (User) | users |
| 0030 | reputation_scores | B (System) | users |
| 0031 | leaderboard_snapshots | B (System) | users |
| 0032 | phase_3_3_rls | — | All Phase 3.3 tables |
| 0033 | phase_3_3_triggers | — | All Phase 3.3 tables |

---

## 5. RLS Classification

| Table | Class | Read | Write |
|-------|-------|------|-------|
| predictions | D | Owner + admin | Owner + admin |
| settlements | D | Via prediction owner | System (settlement service) |
| paper_portfolios | A | Owner + admin | Owner + admin |
| paper_ledger_entries | A | Via portfolio owner | System (ledger service) |
| quarantine_entries | D | Owner + admin + public for promoted | System (quarantine service) |
| validation_runs | D | Owner + admin | System |
| follows | A | Follower/followed + admin | Follower + admin |
| reputation_scores | B | All authenticated | System only |
| leaderboard_snapshots | B | All authenticated | System only |

---

## 6. Files That Will NOT Be Modified

All existing files remain untouched:
- src/models/, src/features/, src/backtest/, src/engine/, src/domain/
- src/ingestion/, src/serializer.py, src/cli.py
- src/auth/, src/api/ (existing routes/middleware)
- src/persistence/ (existing repositories)
- All existing test files
- All migrations 0001-0022

---

## 7. No Blocking Defects

Phase 3.1 and 3.2 are stable. 877 tests pass. No conflicts detected.
