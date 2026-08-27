-- Migration 0002: Create user_wallets table
-- Phase 3.1-A: Web3 identity (optional, no dependency on chain)
-- Ownership: CLASS A (USER OWNED)

BEGIN;

CREATE TABLE IF NOT EXISTS user_wallets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    chain           TEXT NOT NULL,              -- 'ethereum', 'polygon', 'base', 'solana'
    address         TEXT NOT NULL,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at     TIMESTAMPTZ,               -- NULL = unverified
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- A given address on a given chain belongs to exactly one user
CREATE UNIQUE INDEX idx_wallets_chain_address ON user_wallets (LOWER(chain), LOWER(address));

-- Fast lookup by user
CREATE INDEX idx_wallets_user_id ON user_wallets (user_id);

-- Only one primary wallet per user
CREATE UNIQUE INDEX idx_wallets_user_primary ON user_wallets (user_id) WHERE is_primary = TRUE;

COMMIT;
