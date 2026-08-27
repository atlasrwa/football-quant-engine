-- Migration 0005: Create idempotency_keys table
-- Phase 3.1-A: API write deduplication
-- Ownership: CLASS A (USER OWNED — scoped per user)

BEGIN;

CREATE TABLE IF NOT EXISTS idempotency_keys (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    endpoint        TEXT NOT NULL,              -- 'POST /api/v1/strategies', etc.
    http_method     TEXT NOT NULL DEFAULT 'POST',
    request_hash    CHAR(64) NOT NULL,         -- SHA-256 of canonical request body
    response_status SMALLINT NOT NULL,
    response_body   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
    PRIMARY KEY (user_id, idempotency_key)
);

-- Cleanup index: find expired keys efficiently by expires_at ordering
CREATE INDEX idx_idem_expires ON idempotency_keys (expires_at);

-- RLS: users can only see their own idempotency keys
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY idem_select_own ON idempotency_keys
    FOR SELECT
    USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY idem_insert_own ON idempotency_keys
    FOR INSERT
    WITH CHECK (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

-- Allow deletion of expired keys by system
CREATE POLICY idem_delete ON idempotency_keys
    FOR DELETE
    USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

COMMIT;
