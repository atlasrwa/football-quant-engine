-- Migration 0010: Create the deterministic system user
-- Phase 3.1-B: System user for owning anonymous/existing strategies
--
-- The system user has a fixed UUID so it can be referenced deterministically.
-- This migration is idempotent: repeated execution does not create duplicates.

BEGIN;

INSERT INTO users (id, username, email, display_name, password_hash, role, status)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    '_system',
    NULL,
    'System',
    NULL,
    'system',
    'active'
)
ON CONFLICT (id) DO NOTHING;

COMMIT;
