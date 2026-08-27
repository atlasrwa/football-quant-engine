-- Migration 0011: Remove global UNIQUE on content_hash
-- The global unique was too strict — forks legitimately create
-- versions with the same definition under different strategies.
-- Deduplication is handled at the API layer (check before insert).

BEGIN;

ALTER TABLE strategy_versions DROP CONSTRAINT IF EXISTS strategy_versions_content_hash_key;

-- Add a non-unique index for lookups
CREATE INDEX IF NOT EXISTS idx_sv_content_hash ON strategy_versions (content_hash);

COMMIT;
