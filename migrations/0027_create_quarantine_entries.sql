-- Migration 0027: Create quarantine_entries table
-- Phase 3.3: Version-specific quarantine lifecycle
-- Ownership: CLASS D (User+System — user-initiated, system manages transitions)
--
-- PK is (strategy_id, strategy_version): each version has independent quarantine.
-- Strategy A v1 rejected does NOT affect Strategy A v2.
-- Maps from src/engine/fdr.py QuarantineEntry/QuarantineStatus.
-- 90-day minimum quarantine enforced by application (QuarantineTracker).

BEGIN;

CREATE TABLE IF NOT EXISTS quarantine_entries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Strategy version (one quarantine per version)
    strategy_id         UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    strategy_version    INTEGER NOT NULL,
    -- Owner
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Lifecycle state machine: PENDING_QUARANTINE → PROMOTED | REJECTED
    status              TEXT NOT NULL DEFAULT 'PENDING_QUARANTINE'
                        CHECK (status IN ('PENDING_QUARANTINE', 'PROMOTED', 'REJECTED')),
    -- Dates
    entered_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quarantine_until    TIMESTAMPTZ NOT NULL,   -- entered_at + 90 days
    promoted_at         TIMESTAMPTZ,
    rejected_at         TIMESTAMPTZ,
    -- Paper trading performance during quarantine
    paper_pnl           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    paper_bets          INTEGER NOT NULL DEFAULT 0,
    -- Metadata
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One active quarantine per strategy version
    UNIQUE (strategy_id, strategy_version),
    -- FK to strategy_versions
    FOREIGN KEY (strategy_id, strategy_version)
        REFERENCES strategy_versions(strategy_id, version)
);

-- Lookup by user
CREATE INDEX idx_qe_user ON quarantine_entries (user_id);
-- Status filter
CREATE INDEX idx_qe_status ON quarantine_entries (status);
-- Promotion eligibility check
CREATE INDEX idx_qe_pending ON quarantine_entries (quarantine_until)
    WHERE status = 'PENDING_QUARANTINE';

-- Auto-update updated_at
CREATE TRIGGER trg_qe_updated_at
    BEFORE UPDATE ON quarantine_entries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
