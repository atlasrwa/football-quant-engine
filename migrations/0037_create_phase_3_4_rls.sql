-- Migration 0037: RLS policies for Phase 3.4 tables
-- Classification:
--   broadcast_logs              → CLASS D (User+System): owner + admin read; owner/system write
--   attestation_commitments     → CLASS D (via prediction owner): owner + admin read; system write
--   attestation_reveals         → CLASS D (via prediction owner): owner + admin read; system write
--
-- Public provenance (commitment_hash, reveal_hash) may be exposed via
-- dedicated read-only API endpoints in the future. For now, access is
-- restricted to the prediction owner + admin/system.
--
-- UPDATE/DELETE policies exist to allow the row to be "found" by RLS so the
-- immutability trigger (the final authority) produces a clear error message.
-- Without these policies, FORCE RLS would silently block the operation.

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- BROADCAST LOGS (User-owned, system dispatches)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE broadcast_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE broadcast_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY bl_select_own ON broadcast_logs
    FOR SELECT USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY bl_insert_own ON broadcast_logs
    FOR INSERT WITH CHECK (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

-- UPDATE/DELETE: allow row to be found, trigger blocks the mutation
CREATE POLICY bl_update_blocked ON broadcast_logs
    FOR UPDATE USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY bl_delete_blocked ON broadcast_logs
    FOR DELETE USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

-- ═══════════════════════════════════════════════════════════════
-- ATTESTATION COMMITMENTS (via prediction owner)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE attestation_commitments ENABLE ROW LEVEL SECURITY;
ALTER TABLE attestation_commitments FORCE ROW LEVEL SECURITY;

CREATE POLICY ac_select_own ON attestation_commitments
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_commitments.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY ac_insert_system ON attestation_commitments
    FOR INSERT WITH CHECK (
        is_admin_or_system()
        OR EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_commitments.prediction_id
              AND p.user_id = current_app_user_id()
        )
    );

-- UPDATE/DELETE: allow row to be found, trigger blocks the mutation
CREATE POLICY ac_update_blocked ON attestation_commitments
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_commitments.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY ac_delete_blocked ON attestation_commitments
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_commitments.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

-- ═══════════════════════════════════════════════════════════════
-- ATTESTATION REVEALS (via prediction owner)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE attestation_reveals ENABLE ROW LEVEL SECURITY;
ALTER TABLE attestation_reveals FORCE ROW LEVEL SECURITY;

CREATE POLICY ar_select_own ON attestation_reveals
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_reveals.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY ar_insert_system ON attestation_reveals
    FOR INSERT WITH CHECK (
        is_admin_or_system()
        OR EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_reveals.prediction_id
              AND p.user_id = current_app_user_id()
        )
    );

-- UPDATE/DELETE: allow row to be found, trigger blocks the mutation
CREATE POLICY ar_update_blocked ON attestation_reveals
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_reveals.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY ar_delete_blocked ON attestation_reveals
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = attestation_reveals.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

COMMIT;
