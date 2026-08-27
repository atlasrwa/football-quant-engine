-- Migration 0008: Create strategy_versions table
-- Phase 3.1-B: Immutable strategy version definitions
-- Ownership: CLASS A (USER OWNED via parent strategy)
--
-- Each version is an immutable snapshot of a strategy definition.
-- content_hash is computed server-side using the canonical algorithm
-- from StrategyRegistry._compute_hash() — NEVER client-provided.
--
-- Definition is stored as JSONB matching the Strategy dataclass structure:
-- {name, metric, market, conditions: [{field, op, value}], logic, direction, min_odds}

BEGIN;

CREATE TABLE IF NOT EXISTS strategy_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id     UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    version         INTEGER NOT NULL,
    -- Immutable definition
    definition      JSONB NOT NULL,            -- canonical strategy definition
    content_hash    CHAR(64) NOT NULL,         -- SHA-256 computed server-side
    -- Metadata
    created_by      UUID NOT NULL REFERENCES users(id),
    schema_version  TEXT NOT NULL DEFAULT '1.0.0',
    -- Lifecycle (only these fields are mutable)
    is_deprecated   BOOLEAN NOT NULL DEFAULT FALSE,
    deprecated_at   TIMESTAMPTZ,
    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Constraints
    UNIQUE (strategy_id, version),
    UNIQUE (content_hash)
);

-- Version numbering: monotonically increasing per strategy
CREATE INDEX idx_sv_strategy ON strategy_versions (strategy_id, version DESC);
CREATE INDEX idx_sv_hash ON strategy_versions (content_hash);
CREATE INDEX idx_sv_created_by ON strategy_versions (created_by);

-- IMMUTABILITY TRIGGER: only is_deprecated + deprecated_at can change
CREATE OR REPLACE FUNCTION enforce_strategy_version_immutability()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow changes only to lifecycle fields
    IF OLD.id != NEW.id
       OR OLD.strategy_id != NEW.strategy_id
       OR OLD.version != NEW.version
       OR OLD.definition != NEW.definition
       OR OLD.content_hash != NEW.content_hash
       OR OLD.created_by != NEW.created_by
       OR OLD.schema_version != NEW.schema_version
       OR OLD.created_at != NEW.created_at THEN
        RAISE EXCEPTION 'Strategy version definition is immutable — only is_deprecated/deprecated_at may change';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_strategy_version_immutable
    BEFORE UPDATE ON strategy_versions
    FOR EACH ROW EXECUTE FUNCTION enforce_strategy_version_immutability();

-- RLS: inherits visibility from parent strategy
ALTER TABLE strategy_versions ENABLE ROW LEVEL SECURITY;

-- SELECT: visible if parent strategy is visible to the user
CREATE POLICY sv_select ON strategy_versions
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM strategies s
            WHERE s.id = strategy_versions.strategy_id
              AND (s.owner_id = current_app_user_id()
                   OR s.visibility = 'public'
                   OR is_admin_or_system())
        )
    );

-- INSERT: only strategy owner or admin can create versions
CREATE POLICY sv_insert ON strategy_versions
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM strategies s
            WHERE s.id = strategy_versions.strategy_id
              AND (s.owner_id = current_app_user_id()
                   OR is_admin_or_system())
        )
    );

-- UPDATE: only strategy owner or admin (for deprecation only)
CREATE POLICY sv_update ON strategy_versions
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM strategies s
            WHERE s.id = strategy_versions.strategy_id
              AND (s.owner_id = current_app_user_id()
                   OR is_admin_or_system())
        )
    );

COMMIT;
