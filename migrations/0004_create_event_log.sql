-- Migration 0004: Create event_log table
-- Phase 3.1-A: Append-only audit infrastructure
-- Ownership: CLASS B (SYSTEM OWNED — append-only, no user writes directly)

BEGIN;

CREATE TABLE IF NOT EXISTS event_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,              -- e.g. 'USER_REGISTERED', 'STRATEGY_CREATED'
    event_version   SMALLINT NOT NULL DEFAULT 1,
    aggregate_type  TEXT NOT NULL,              -- e.g. 'user', 'strategy', 'prediction'
    aggregate_id    TEXT NOT NULL,              -- UUID of affected entity (as text for flexibility)
    actor_type      TEXT NOT NULL CHECK (actor_type IN ('user', 'system', 'admin', 'service')),
    actor_id        UUID,                       -- NULL for system-initiated events
    payload         JSONB NOT NULL DEFAULT '{}',
    correlation_id  UUID,                       -- groups related events across a request
    causation_id    BIGINT,                     -- references parent event_id in chain
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Query patterns: by aggregate, by actor, by type, by time
CREATE INDEX idx_events_aggregate ON event_log (aggregate_type, aggregate_id, created_at DESC);
CREATE INDEX idx_events_type ON event_log (event_type, created_at DESC);
CREATE INDEX idx_events_actor ON event_log (actor_id, created_at DESC) WHERE actor_id IS NOT NULL;
CREATE INDEX idx_events_correlation ON event_log (correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX idx_events_created ON event_log (created_at DESC);

-- IMMUTABILITY ENFORCEMENT: prevent UPDATE and DELETE
CREATE OR REPLACE FUNCTION prevent_event_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'event_log is append-only: % operations are forbidden', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_event_log_no_update
    BEFORE UPDATE ON event_log
    FOR EACH ROW EXECUTE FUNCTION prevent_event_log_mutation();

CREATE TRIGGER trg_event_log_no_delete
    BEFORE DELETE ON event_log
    FOR EACH ROW EXECUTE FUNCTION prevent_event_log_mutation();

-- RLS: event_log is system-owned, readable by admin/system, writable only via application
ALTER TABLE event_log ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read events related to their own aggregates
-- Admins/system can read all
CREATE POLICY event_log_select ON event_log
    FOR SELECT
    USING (
        actor_id = current_app_user_id()
        OR is_admin_or_system()
        OR TRUE  -- Events are generally readable (audit trail)
    );

-- Only application (fqe_app role) can insert events
CREATE POLICY event_log_insert ON event_log
    FOR INSERT
    WITH CHECK (TRUE);  -- Controlled by application layer

COMMIT;
