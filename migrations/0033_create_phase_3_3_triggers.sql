-- Migration 0033: Immutability triggers for Phase 3.3 tables
--
-- Immutability rules:
--   predictions: only status + settled_at mutable after creation
--   settlements: INSERT-only (no UPDATE, no DELETE)
--   paper_ledger_entries: INSERT-only (CRITICAL TRUST COMPONENT)
--   quarantine_entries: controlled transitions only
--   validation_runs: INSERT-only
--   reputation_scores: system can UPDATE (recalculate)
--   leaderboard_snapshots: INSERT-only
--   follows: INSERT + DELETE allowed (follow/unfollow)
--   paper_portfolios: current_balance updatable (cached value)

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- PREDICTIONS: only status + settled_at may change
-- ═══════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION enforce_prediction_immutability()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.id != NEW.id
       OR OLD.user_id != NEW.user_id
       OR OLD.strategy_id != NEW.strategy_id
       OR OLD.strategy_version != NEW.strategy_version
       OR OLD.strategy_content_hash != NEW.strategy_content_hash
       OR OLD.match_id != NEW.match_id
       OR OLD.direction != NEW.direction
       OR OLD.entry_odds IS DISTINCT FROM NEW.entry_odds
       OR OLD.source != NEW.source
       OR OLD.proof_hash != NEW.proof_hash
       OR OLD.created_at != NEW.created_at THEN
        RAISE EXCEPTION 'Prediction fields are immutable after creation (only status/settled_at may change)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pred_immutability
    BEFORE UPDATE ON predictions
    FOR EACH ROW EXECUTE FUNCTION enforce_prediction_immutability();

-- ═══════════════════════════════════════════════════════════════
-- SETTLEMENTS: INSERT-only (no UPDATE, no DELETE)
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_settle_no_update
    BEFORE UPDATE ON settlements
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_settle_no_delete
    BEFORE DELETE ON settlements
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- PAPER LEDGER ENTRIES: INSERT-only (CRITICAL TRUST)
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_ple_no_update
    BEFORE UPDATE ON paper_ledger_entries
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_ple_no_delete
    BEFORE DELETE ON paper_ledger_entries
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- QUARANTINE: controlled state transitions
-- ═══════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION enforce_quarantine_lifecycle()
RETURNS TRIGGER AS $$
BEGIN
    -- Immutable fields
    IF OLD.strategy_id != NEW.strategy_id
       OR OLD.strategy_version != NEW.strategy_version
       OR OLD.user_id != NEW.user_id
       OR OLD.entered_at != NEW.entered_at
       OR OLD.quarantine_until != NEW.quarantine_until
       OR OLD.created_at != NEW.created_at THEN
        RAISE EXCEPTION 'Quarantine provenance fields are immutable';
    END IF;

    -- Once PROMOTED or REJECTED, no further state changes
    IF OLD.status IN ('PROMOTED', 'REJECTED') AND OLD.status != NEW.status THEN
        RAISE EXCEPTION 'Quarantine entry is % and cannot change status', OLD.status;
    END IF;

    -- Valid transitions from PENDING_QUARANTINE only
    IF OLD.status = 'PENDING_QUARANTINE' AND NEW.status NOT IN ('PENDING_QUARANTINE', 'PROMOTED', 'REJECTED') THEN
        RAISE EXCEPTION 'Invalid quarantine transition from % to %', OLD.status, NEW.status;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_qe_lifecycle
    BEFORE UPDATE ON quarantine_entries
    FOR EACH ROW EXECUTE FUNCTION enforce_quarantine_lifecycle();

-- Prevent deletion of quarantine history
CREATE TRIGGER trg_qe_no_delete
    BEFORE DELETE ON quarantine_entries
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- VALIDATION RUNS: INSERT-only
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_vr_no_update
    BEFORE UPDATE ON validation_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_vr_no_delete
    BEFORE DELETE ON validation_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- LEADERBOARD SNAPSHOTS: INSERT-only
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_lb_no_update
    BEFORE UPDATE ON leaderboard_snapshots
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_lb_no_delete
    BEFORE DELETE ON leaderboard_snapshots
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

COMMIT;
