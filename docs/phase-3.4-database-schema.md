# Phase 3.4 Database Schema

## Tables

### broadcast_logs

Immutable delivery audit records. One prediction → many broadcasts (one per channel/destination).

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() |
| user_id | UUID | NOT NULL, FK → users(id) |
| prediction_id | UUID | NOT NULL, FK → predictions(id) |
| channel | VARCHAR(50) | NOT NULL, CHECK IN (web, mobile, telegram, discord, email, webhook) |
| destination | VARCHAR(500) | NULL |
| status | VARCHAR(30) | NOT NULL, CHECK IN (PENDING, DISPATCHED, DELIVERED, FAILED, RETRY) |
| payload_hash | CHAR(64) | NOT NULL |
| deep_link | VARCHAR(500) | NULL |
| dispatched_at | TIMESTAMPTZ | NULL |
| error_code | VARCHAR(100) | NULL |
| error_message | TEXT | NULL |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |

### attestation_commitments

Cryptographic pre-commitments. One per prediction (1:1).

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() |
| prediction_id | UUID | NOT NULL, UNIQUE, FK → predictions(id) |
| commitment_hash | CHAR(64) | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |
| chain_id | BIGINT | NULL (future Web3) |
| contract_address | VARCHAR(42) | NULL (future Web3) |
| tx_hash | VARCHAR(66) | NULL (future Web3) |
| block_number | BIGINT | NULL (future Web3) |

### attestation_reveals

Post-settlement reveals. One per commitment/prediction/settlement (1:1:1).

| Column | Type | Constraints |
|--------|------|-------------|
| id | UUID | PRIMARY KEY, DEFAULT gen_random_uuid() |
| commitment_id | UUID | NOT NULL, UNIQUE, FK → attestation_commitments(id) |
| prediction_id | UUID | NOT NULL, UNIQUE, FK → predictions(id) |
| settlement_id | UUID | NOT NULL, UNIQUE, FK → settlements(id) |
| reveal_payload | JSONB | NOT NULL |
| reveal_hash | CHAR(64) | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |
| chain_id | BIGINT | NULL (future Web3) |
| contract_address | VARCHAR(42) | NULL (future Web3) |
| tx_hash | VARCHAR(66) | NULL (future Web3) |
| block_number | BIGINT | NULL (future Web3) |

## Indexes

### broadcast_logs
- `idx_bl_unique_pred_channel_dest` — UNIQUE ON (prediction_id, channel, COALESCE(destination, ''))
- `idx_bl_user_status` — (user_id, status, created_at DESC)
- `idx_bl_prediction` — (prediction_id, created_at DESC)
- `idx_bl_channel_status` — (channel, status)
- `idx_bl_dispatched` — (dispatched_at) WHERE dispatched_at IS NOT NULL
- `idx_bl_payload_hash` — (payload_hash)

### attestation_commitments
- `idx_ac_commitment_hash` — (commitment_hash)
- `idx_ac_prediction` — (prediction_id)
- `idx_ac_chain` — (chain_id, block_number) WHERE chain_id IS NOT NULL

### attestation_reveals
- `idx_ar_reveal_hash` — (reveal_hash)
- `idx_ar_settlement` — (settlement_id)
- `idx_ar_commitment` — (commitment_id)
- `idx_ar_chain` — (chain_id, block_number) WHERE chain_id IS NOT NULL

## Foreign Keys

- `broadcast_logs.user_id` → `users(id)`
- `broadcast_logs.prediction_id` → `predictions(id)`
- `attestation_commitments.prediction_id` → `predictions(id)`
- `attestation_reveals.commitment_id` → `attestation_commitments(id)`
- `attestation_reveals.prediction_id` → `predictions(id)`
- `attestation_reveals.settlement_id` → `settlements(id)`

## Triggers (Immutability)

All tables use `prevent_modification()` from migration 0022:

| Table | Triggers |
|-------|----------|
| broadcast_logs | trg_bl_no_update, trg_bl_no_delete |
| attestation_commitments | trg_ac_no_update, trg_ac_no_delete |
| attestation_reveals | trg_ar_no_update, trg_ar_no_delete |
