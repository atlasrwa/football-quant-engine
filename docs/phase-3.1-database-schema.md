# Phase 3.1 Database Schema

## Overview

- **Database**: `football_quant_engine`
- **PostgreSQL version**: 16
- **Extensions**: `pgcrypto` (for `gen_random_uuid()`)
- **Tables**: 9 (+ `_migrations` tracking table)
- **RLS**: Enabled and FORCED on all tables

## Tables

### users
```
id              UUID PRIMARY KEY (gen_random_uuid)
username        TEXT NOT NULL (UNIQUE case-insensitive)
email           TEXT (UNIQUE case-insensitive, nullable)
display_name    TEXT NOT NULL
password_hash   TEXT (nullable for wallet-only)
role            TEXT NOT NULL DEFAULT 'user' CHECK (user/creator/admin/system)
status          TEXT NOT NULL DEFAULT 'active' CHECK (active/disabled/suspended)
avatar_url      TEXT
bio             TEXT
primary_wallet_address TEXT (UNIQUE case-insensitive, nullable)
created_at      TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW() (auto-updated by trigger)
last_login_at   TIMESTAMPTZ
```

### user_wallets
```
id              UUID PRIMARY KEY
user_id         UUID NOT NULL FK→users
chain           TEXT NOT NULL
address         TEXT NOT NULL
is_primary      BOOLEAN NOT NULL DEFAULT FALSE
verified_at     TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT NOW()
UNIQUE (chain, address) case-insensitive
UNIQUE (user_id) WHERE is_primary = TRUE
```

### strategies
```
id              UUID PRIMARY KEY
owner_id        UUID NOT NULL FK→users (IMMUTABLE after creation)
name            TEXT NOT NULL
description     TEXT
visibility      TEXT NOT NULL DEFAULT 'private' CHECK (private/public/unlisted)
status          TEXT NOT NULL DEFAULT 'active' CHECK (active/archived)
created_at      TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW() (auto-updated)
```

### strategy_versions
```
id              UUID PRIMARY KEY
strategy_id     UUID NOT NULL FK→strategies
version         INTEGER NOT NULL
definition      JSONB NOT NULL (canonical strategy definition)
content_hash    CHAR(64) NOT NULL (SHA-256, server-computed)
created_by      UUID NOT NULL FK→users
schema_version  TEXT NOT NULL DEFAULT '1.0.0'
is_deprecated   BOOLEAN NOT NULL DEFAULT FALSE
deprecated_at   TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT NOW()
UNIQUE (strategy_id, version)
INDEX (content_hash) — non-unique, allows forks
```

### strategy_forks
```
id                  UUID PRIMARY KEY
source_strategy_id  UUID NOT NULL FK→strategies
source_version      INTEGER NOT NULL
source_content_hash CHAR(64) NOT NULL
target_strategy_id  UUID NOT NULL FK→strategies
forked_by           UUID NOT NULL FK→users
created_at          TIMESTAMPTZ DEFAULT NOW()
FK (source_strategy_id, source_version) → strategy_versions
IMMUTABLE (trigger blocks UPDATE/DELETE)
```

### matches
```
match_id        BIGSERIAL PRIMARY KEY (surrogate)
external_id     INTEGER NOT NULL
external_source TEXT NOT NULL DEFAULT 'footystats'
date_unix       BIGINT NOT NULL
league_id       INTEGER NOT NULL
season          TEXT NOT NULL
home_team       TEXT NOT NULL
away_team       TEXT NOT NULL
home_goals      SMALLINT CHECK (>=0)
away_goals      SMALLINT CHECK (>=0)
total_goals     SMALLINT GENERATED ALWAYS AS (home_goals + away_goals) STORED
home_xg         DOUBLE PRECISION CHECK (>=0 or NULL)
away_xg         DOUBLE PRECISION CHECK (>=0 or NULL)
referee         TEXT
over_under_line DOUBLE PRECISION CHECK (>0 or NULL)
over_odds       DOUBLE PRECISION CHECK (>1.0 or NULL)
under_odds      DOUBLE PRECISION CHECK (>1.0 or NULL)
raw_data        JSONB
status          TEXT NOT NULL DEFAULT 'completed'
ingested_at     TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW() (auto-updated)
UNIQUE (external_source, external_id)
```

### event_log
```
id              BIGSERIAL PRIMARY KEY
event_type      TEXT NOT NULL
event_version   SMALLINT NOT NULL DEFAULT 1
aggregate_type  TEXT NOT NULL
aggregate_id    TEXT NOT NULL
actor_type      TEXT NOT NULL CHECK (user/system/admin/service)
actor_id        UUID (nullable)
payload         JSONB NOT NULL DEFAULT '{}'
correlation_id  UUID
causation_id    BIGINT
created_at      TIMESTAMPTZ DEFAULT NOW()
APPEND-ONLY (triggers block UPDATE/DELETE)
```

### idempotency_keys
```
user_id         UUID NOT NULL FK→users
idempotency_key TEXT NOT NULL
endpoint        TEXT NOT NULL
http_method     TEXT NOT NULL DEFAULT 'POST'
request_hash    CHAR(64) NOT NULL
response_status SMALLINT NOT NULL
response_body   JSONB NOT NULL
created_at      TIMESTAMPTZ DEFAULT NOW()
expires_at      TIMESTAMPTZ DEFAULT NOW() + 24h
PRIMARY KEY (user_id, idempotency_key)
```

## Indexes

| Table | Index | Purpose |
|-------|-------|---------|
| users | `idx_users_username_lower` | Case-insensitive username lookup |
| users | `idx_users_email_lower` | Case-insensitive email lookup |
| users | `idx_users_wallet` | Wallet address lookup |
| strategies | `idx_strategies_owner` | Owner's strategies |
| strategies | `idx_strategies_visibility` | Public strategy discovery |
| strategy_versions | `idx_sv_strategy` | Versions per strategy |
| strategy_versions | `idx_sv_content_hash` | Deduplication lookup |
| strategy_forks | `idx_forks_source` | Forks of a strategy |
| strategy_forks | `idx_forks_target` | Fork origin lookup |
| matches | `idx_matches_league_season` | League/season queries |
| matches | `idx_matches_date` | Chronological ordering |
| matches | `idx_matches_external` | External ID lookup |
| event_log | `idx_events_aggregate` | Events per entity |
| event_log | `idx_events_type` | Events by type |
| event_log | `idx_events_actor` | Events by actor |
| event_log | `idx_events_correlation` | Correlated events |
| idempotency_keys | `idx_idem_expires` | Expired key cleanup |

## Triggers

| Trigger | Table | Action | Purpose |
|---------|-------|--------|---------|
| `trg_users_updated_at` | users | BEFORE UPDATE | Auto-update timestamp |
| `trg_strategies_updated_at` | strategies | BEFORE UPDATE | Auto-update timestamp |
| `trg_strategy_owner_immutable` | strategies | BEFORE UPDATE | Prevent owner_id change |
| `trg_strategy_version_immutable` | strategy_versions | BEFORE UPDATE | Prevent definition change |
| `trg_fork_no_update` | strategy_forks | BEFORE UPDATE | Full immutability |
| `trg_fork_no_delete` | strategy_forks | BEFORE DELETE | Full immutability |
| `trg_event_log_no_update` | event_log | BEFORE UPDATE | Append-only enforcement |
| `trg_event_log_no_delete` | event_log | BEFORE DELETE | Append-only enforcement |
| `trg_matches_updated_at` | matches | BEFORE UPDATE | Auto-update timestamp |
