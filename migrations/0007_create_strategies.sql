-- Migration 0007: Create strategies table
-- Phase 3.1-B: Strategy identity and ownership
-- Ownership: CLASS A (USER OWNED — each strategy has a single owner)
--
-- The strategies table is the stable identity anchor.
-- It holds ownership + lifecycle. Definition lives in strategy_versions.

BEGIN;

CREATE TABLE IF NOT EXISTS strategies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL,
    description     TEXT,
    visibility      TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'public', 'unlisted')),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- owner_id is IMMUTABLE after creation (enforced by trigger below)
-- Indexes
CREATE INDEX idx_strategies_owner ON strategies (owner_id);
CREATE INDEX idx_strategies_visibility ON strategies (visibility) WHERE visibility = 'public';
CREATE INDEX idx_strategies_status ON strategies (status) WHERE status = 'active';

-- Auto-update updated_at
CREATE TRIGGER trg_strategies_updated_at
    BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Immutability: owner_id cannot change after creation
CREATE OR REPLACE FUNCTION enforce_strategy_owner_immutability()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.owner_id != NEW.owner_id THEN
        RAISE EXCEPTION 'Strategy owner_id is immutable after creation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_strategy_owner_immutable
    BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION enforce_strategy_owner_immutability();

-- RLS: owner can read/write own strategies; public strategies readable by all
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;

-- SELECT: owner sees own; everyone sees public; admin sees all
CREATE POLICY strategies_select ON strategies
    FOR SELECT
    USING (
        owner_id = current_app_user_id()
        OR visibility = 'public'
        OR is_admin_or_system()
    );

-- INSERT: user can only create strategies they own
CREATE POLICY strategies_insert ON strategies
    FOR INSERT
    WITH CHECK (
        owner_id = current_app_user_id()
        OR is_admin_or_system()
    );

-- UPDATE: only owner or admin can update
CREATE POLICY strategies_update ON strategies
    FOR UPDATE
    USING (
        owner_id = current_app_user_id()
        OR is_admin_or_system()
    )
    WITH CHECK (
        owner_id = current_app_user_id()
        OR is_admin_or_system()
    );

COMMIT;
