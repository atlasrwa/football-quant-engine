# Phase 3.1 Migration Guide

## Prerequisites

1. PostgreSQL 16 server installed and running
2. Python 3.12+ with venv activated
3. Dependencies installed: `asyncpg`, `alembic`, `sqlalchemy`, `fastapi`, `uvicorn`, `passlib[bcrypt]`, `PyJWT`

## Database Setup

```bash
# Create role and database
sudo -u postgres psql -c "CREATE USER fqe_app WITH PASSWORD 'fqe_dev_password' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE football_quant_engine OWNER fqe_app;"
sudo -u postgres psql -d football_quant_engine -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

## Running Migrations

```bash
# From project root
.venv/bin/python migrations/run_migrations.py
```

The migration runner:
- Creates a `_migrations` tracking table on first run
- Applies migrations in numerical order (0001, 0002, ...)
- Skips already-applied migrations (idempotent)
- Reports which migrations were applied/skipped

## Migration Order (Dependency-Safe)

| # | File | Creates |
|---|------|---------|
| 0001 | `create_users.sql` | `users` table + `updated_at` trigger function |
| 0002 | `create_user_wallets.sql` | `user_wallets` table |
| 0003 | `create_rls_context.sql` | RLS helper functions + policies for users/wallets |
| 0004 | `create_event_log.sql` | `event_log` table + immutability triggers |
| 0005 | `create_idempotency_keys.sql` | `idempotency_keys` table |
| 0006 | `create_matches.sql` | `matches` table (surrogate key) |
| 0007 | `create_strategies.sql` | `strategies` table + owner immutability trigger |
| 0008 | `create_strategy_versions.sql` | `strategy_versions` table + definition immutability trigger |
| 0009 | `create_strategy_forks.sql` | `strategy_forks` table + full immutability triggers |
| 0010 | `backfill_system_user.sql` | System user (UUID `00000000-...0001`) |
| 0011 | `fix_content_hash_unique.sql` | Remove global UNIQUE on content_hash (allows forks) |
| 0012 | `force_rls.sql` | FORCE RLS on all tables (owner bypass disabled) |

## Verification

After running migrations:
```bash
# Verify tables
psql "postgresql://fqe_app:fqe_dev_password@localhost/football_quant_engine" -c "\dt"

# Verify system user
psql "..." -c "SELECT id, username, role FROM users WHERE role = 'system';"

# Verify RLS is forced
psql "..." -c "SELECT relname, relforcerowsecurity FROM pg_class WHERE relname = 'users';"

# Run tests
.venv/bin/python -m pytest tests/ -q
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `FQE_DATABASE_URL` | `postgresql://fqe_app:fqe_dev_password@localhost:5432/football_quant_engine` | Database connection |
| `JWT_SECRET_KEY` | `dev-secret-key-change-in-production` | JWT signing key |
| `JWT_EXPIRE_MINUTES` | `60` | Token expiration |

**Important**: Use `FQE_DATABASE_URL` (not `DATABASE_URL`) to avoid conflicts with other projects in the same environment.

## Running the API

```bash
.venv/bin/python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

## Backward Compatibility

- All 727 existing engine tests pass without modification
- CLI continues to work without authentication (file-based mode)
- No existing source files in `src/models/`, `src/features/`, `src/backtest/`, `src/engine/`, `src/domain/` were modified
- PostgreSQL is additive — does not replace file-based caching for CLI usage
