-- Migration 0009: Create strategy_forks table
-- Phase 3.1-B: Fork lineage tracking
-- Ownership: CLASS A (USER OWNED — forked_by is the fork creator)
--
-- Tracks copy/evolve relationships between strategies.
-- Fork lineage is immutable: once a fork is recorded, it cannot be changed.

BEGIN;

CREATE TABLE IF NOT EXISTS strategy_forks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Source: the original strategy+version being forked
    source_strategy_id  UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    source_version      INTEGER NOT NULL,
    source_content_hash CHAR(64) NOT NULL,     -- snapshot of source hash at fork time
    -- Target: the new strategy created from the fork
    target_strategy_id  UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    -- Who forked it
    forked_by           UUID NOT NULL REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Foreign key to source version
    FOREIGN KEY (source_strategy_id, source_version)
        REFERENCES strategy_versions(strategy_id, version)
);

-- Indexes
CREATE INDEX idx_forks_source ON strategy_forks (source_strategy_id, source_version);
CREATE INDEX idx_forks_target ON strategy_forks (target_strategy_id);
CREATE INDEX idx_forks_user ON strategy_forks (forked_by);

-- IMMUTABILITY: forks cannot be modified after creation
CREATE OR REPLACE FUNCTION prevent_fork_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Strategy forks are immutable after creation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fork_no_update
    BEFORE UPDATE ON strategy_forks
    FOR EACH ROW EXECUTE FUNCTION prevent_fork_mutation();

CREATE TRIGGER trg_fork_no_delete
    BEFORE DELETE ON strategy_forks
    FOR EACH ROW EXECUTE FUNCTION prevent_fork_mutation();

-- RLS: forks are readable if either source or target strategy is visible
ALTER TABLE strategy_forks ENABLE ROW LEVEL SECURITY;

CREATE POLICY forks_select ON strategy_forks
    FOR SELECT
    USING (
        forked_by = current_app_user_id()
        OR is_admin_or_system()
        OR EXISTS (
            SELECT 1 FROM strategies s
            WHERE (s.id = strategy_forks.source_strategy_id
                   OR s.id = strategy_forks.target_strategy_id)
              AND (s.owner_id = current_app_user_id() OR s.visibility = 'public')
        )
    );

CREATE POLICY forks_insert ON strategy_forks
    FOR INSERT
    WITH CHECK (
        forked_by = current_app_user_id()
        OR is_admin_or_system()
    );

COMMIT;
