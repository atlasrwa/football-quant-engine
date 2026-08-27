# Phase 3.3 Migration Guide

## Prerequisites
Phase 3.1 (migrations 0001-0012) and Phase 3.2 (0013-0022) must be applied.

## Running Migrations
```bash
.venv/bin/python migrations/run_migrations.py
```

## Migration Order

| # | File | Creates |
|---|------|---------|
| 0023 | create_predictions.sql | predictions table |
| 0024 | create_settlements.sql | settlements table |
| 0025 | create_paper_portfolios.sql | paper_portfolios table |
| 0026 | create_paper_ledger_entries.sql | paper_ledger_entries table |
| 0027 | create_quarantine_entries.sql | quarantine_entries table |
| 0028 | create_validation_runs.sql | validation_runs table |
| 0029 | create_follows.sql | follows table |
| 0030 | create_reputation_scores.sql | reputation_scores table |
| 0031 | create_leaderboard_snapshots.sql | leaderboard_snapshots table |
| 0032 | create_phase_3_3_rls.sql | RLS policies for all Phase 3.3 tables |
| 0033 | create_phase_3_3_triggers.sql | Immutability triggers |

## Verification
```bash
# Check all 25 tables exist
psql "..." -c "\dt" | wc -l  # Should show 25 tables + header

# Check RLS forced
psql "..." -c "SELECT relname, relforcerowsecurity FROM pg_class WHERE relname IN ('predictions','settlements','paper_portfolios','paper_ledger_entries','quarantine_entries','validation_runs','follows','reputation_scores','leaderboard_snapshots');"

# Run tests
.venv/bin/python -m pytest tests/ -q
# Expected: 904 passed
```

## Total Migrations: 33
