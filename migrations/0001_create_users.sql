-- Migration 0001: Create users table
-- Phase 3.1-A: Identity foundation
-- Ownership: CLASS A (USER OWNED)

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        TEXT NOT NULL,
    email           TEXT,
    display_name    TEXT NOT NULL,
    password_hash   TEXT,                       -- NULL for wallet-only users
    role            TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'creator', 'admin', 'system')),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'suspended')),
    avatar_url      TEXT,
    bio             TEXT,
    primary_wallet_address TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

-- Case-insensitive uniqueness on username and email
CREATE UNIQUE INDEX idx_users_username_lower ON users (LOWER(username));
CREATE UNIQUE INDEX idx_users_email_lower ON users (LOWER(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX idx_users_wallet ON users (LOWER(primary_wallet_address)) WHERE primary_wallet_address IS NOT NULL;

-- updated_at auto-update trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
