# Phase 3.3 Database Schema

## New Tables (9)

### predictions
User prediction records mapped from PredictionEvent domain object.
- `id` UUID PK, `user_id` FK→users, `strategy_id`+`strategy_version` FK→strategy_versions
- `match_id` BIGINT FK→matches, `direction` CHECK(OVER/UNDER/BACK/LAY)
- `entry_odds` CHECK >1.0 OR NULL (I3), `proof_hash` CHAR(64) server-computed (I10)
- `source` CHECK(BACKTEST/LIVE_SIGNAL/PAPER_TRADE), `status` CHECK(PENDING/SETTLED_*/EXPIRED)
- Only `status`+`settled_at` mutable after creation (trigger enforced)

### settlements
Immutable settlement records. INSERT-only.
- `id` UUID PK, `prediction_id` UUID UNIQUE FK→predictions (idempotent I14)
- `outcome` CHECK(WIN/LOSS/VOID/PUSH) — computed by SettlementFactory (I11)
- `closing_odds` — from market_prices only (I9), NULL if unavailable
- `clv_pct` — NULL when closing_odds unavailable (I4)
- `profit_loss` — computed by Settlement.compute_profit_loss()
- No UPDATE/DELETE (trigger enforced)

### paper_portfolios
User-owned virtual bankrolls.
- `id` UUID PK, `user_id` FK→users, UNIQUE(user_id, name)
- `initial_balance`, `current_balance` (cached from ledger)

### paper_ledger_entries
CRITICAL TRUST COMPONENT. Append-only.
- `id` BIGSERIAL PK (monotonic audit ordering)
- `portfolio_id` FK→paper_portfolios, `prediction_id`/`settlement_id` optional FKs
- `entry_type` CHECK(OPENING_BALANCE/BET_PLACED/BET_SETTLED/ADJUSTMENT)
- `amount`, `balance_after` (running snapshot)
- No UPDATE/DELETE (trigger enforced)

### quarantine_entries
Version-specific quarantine lifecycle.
- UNIQUE(strategy_id, strategy_version), FK→strategy_versions
- `status` CHECK(PENDING_QUARANTINE/PROMOTED/REJECTED)
- `quarantine_until` = entered_at + 90 days
- Controlled state machine (trigger enforced)

### validation_runs
Persisted StatisticalValidator output. INSERT-only.
- `strategy_id`+`strategy_version`, `backtest_run_id` FK
- Full metrics: p_value, roi_pct, sample_size, effect_size, CI, FDR

### follows
Social follow relationships.
- PK(follower_id, followed_id), CHECK(follower_id != followed_id)
- Supports INSERT + DELETE (follow/unfollow)

### reputation_scores
System-computed derived metrics.
- UNIQUE(user_id, period_type, period_start)
- System-only write, all read

### leaderboard_snapshots
Pre-computed rankings. INSERT-only.
- `scope`, `period_type`, `rank`, `user_id`, metrics
- System-only write, all read

## Total Tables: 25 (16 from Phase 3.1/3.2 + 9 from Phase 3.3)
