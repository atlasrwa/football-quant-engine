-- Migration 0038: Immutability triggers for Phase 3.4 tables
--
-- All Phase 3.4 tables are INSERT-only (append-only audit/provenance):
--   broadcast_logs: immutable delivery records
--   attestation_commitments: immutable cryptographic pre-commitments
--   attestation_reveals: immutable post-settlement reveals
--
-- Uses the existing prevent_modification() function from migration 0022.
-- Corrections occur through new records, not mutations.

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- BROADCAST LOGS: INSERT-only (no UPDATE, no DELETE)
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_bl_no_update
    BEFORE UPDATE ON broadcast_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_bl_no_delete
    BEFORE DELETE ON broadcast_logs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- ATTESTATION COMMITMENTS: INSERT-only (no UPDATE, no DELETE)
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_ac_no_update
    BEFORE UPDATE ON attestation_commitments
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_ac_no_delete
    BEFORE DELETE ON attestation_commitments
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- ATTESTATION REVEALS: INSERT-only (no UPDATE, no DELETE)
-- ═══════════════════════════════════════════════════════════════
CREATE TRIGGER trg_ar_no_update
    BEFORE UPDATE ON attestation_reveals
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_ar_no_delete
    BEFORE DELETE ON attestation_reveals
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

COMMIT;
