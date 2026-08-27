-- Migration 0032: RLS policies for all Phase 3.3 tables
-- Classification:
--   predictions          → CLASS D (User+System): owner + admin read/write
--   settlements          → CLASS D: via prediction owner read; system write
--   paper_portfolios     → CLASS A (User): owner + admin
--   paper_ledger_entries → CLASS A: via portfolio owner read; system write
--   quarantine_entries   → CLASS D: owner + admin; promoted visible to all
--   validation_runs      → CLASS D: owner + admin
--   follows              → CLASS A: follower/followed + admin
--   reputation_scores    → CLASS B (System): all read, system write
--   leaderboard_snapshots→ CLASS B: all read, system write

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- PREDICTIONS (User+System)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions FORCE ROW LEVEL SECURITY;

CREATE POLICY pred_select_own ON predictions
    FOR SELECT USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY pred_insert_own ON predictions
    FOR INSERT WITH CHECK (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY pred_update_own ON predictions
    FOR UPDATE USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

-- ═══════════════════════════════════════════════════════════════
-- SETTLEMENTS (inherits via prediction)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE settlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlements FORCE ROW LEVEL SECURITY;

CREATE POLICY settle_select_own ON settlements
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = settlements.prediction_id
              AND (p.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY settle_insert_system ON settlements
    FOR INSERT WITH CHECK (
        is_admin_or_system()
        OR EXISTS (
            SELECT 1 FROM predictions p
            WHERE p.id = settlements.prediction_id
              AND p.user_id = current_app_user_id()
        )
    );

-- ═══════════════════════════════════════════════════════════════
-- PAPER PORTFOLIOS (User-owned)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE paper_portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_portfolios FORCE ROW LEVEL SECURITY;

CREATE POLICY pp_select_own ON paper_portfolios
    FOR SELECT USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY pp_insert_own ON paper_portfolios
    FOR INSERT WITH CHECK (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY pp_update_own ON paper_portfolios
    FOR UPDATE USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

-- ═══════════════════════════════════════════════════════════════
-- PAPER LEDGER ENTRIES (via portfolio owner)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE paper_ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_ledger_entries FORCE ROW LEVEL SECURITY;

CREATE POLICY ple_select_own ON paper_ledger_entries
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM paper_portfolios pp
            WHERE pp.id = paper_ledger_entries.portfolio_id
              AND (pp.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY ple_insert_own ON paper_ledger_entries
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM paper_portfolios pp
            WHERE pp.id = paper_ledger_entries.portfolio_id
              AND (pp.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

-- ═══════════════════════════════════════════════════════════════
-- QUARANTINE ENTRIES (owner + admin; promoted readable by all)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE quarantine_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE quarantine_entries FORCE ROW LEVEL SECURITY;

CREATE POLICY qe_select ON quarantine_entries
    FOR SELECT USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
        OR status = 'PROMOTED'  -- Promoted strategies are publicly visible
    );

CREATE POLICY qe_insert ON quarantine_entries
    FOR INSERT WITH CHECK (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY qe_update ON quarantine_entries
    FOR UPDATE USING (
        user_id = current_app_user_id() OR is_admin_or_system()
    );

-- ═══════════════════════════════════════════════════════════════
-- VALIDATION RUNS (owner + admin)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE validation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY vr_select ON validation_runs
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM strategies s
            WHERE s.id = validation_runs.strategy_id
              AND (s.owner_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY vr_insert ON validation_runs
    FOR INSERT WITH CHECK (is_admin_or_system());

-- ═══════════════════════════════════════════════════════════════
-- FOLLOWS (follower + followed + admin)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE follows ENABLE ROW LEVEL SECURITY;
ALTER TABLE follows FORCE ROW LEVEL SECURITY;

CREATE POLICY follows_select ON follows
    FOR SELECT USING (
        follower_id = current_app_user_id()
        OR followed_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY follows_insert ON follows
    FOR INSERT WITH CHECK (
        follower_id = current_app_user_id() OR is_admin_or_system()
    );

CREATE POLICY follows_delete ON follows
    FOR DELETE USING (
        follower_id = current_app_user_id() OR is_admin_or_system()
    );

-- ═══════════════════════════════════════════════════════════════
-- REPUTATION SCORES (System-owned, all read)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE reputation_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE reputation_scores FORCE ROW LEVEL SECURITY;

CREATE POLICY rs_select_all ON reputation_scores
    FOR SELECT USING (TRUE);

CREATE POLICY rs_insert_system ON reputation_scores
    FOR INSERT WITH CHECK (is_admin_or_system());

CREATE POLICY rs_update_system ON reputation_scores
    FOR UPDATE USING (is_admin_or_system());

-- ═══════════════════════════════════════════════════════════════
-- LEADERBOARD SNAPSHOTS (System-owned, all read)
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE leaderboard_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE leaderboard_snapshots FORCE ROW LEVEL SECURITY;

CREATE POLICY lb_select_all ON leaderboard_snapshots
    FOR SELECT USING (TRUE);

CREATE POLICY lb_insert_system ON leaderboard_snapshots
    FOR INSERT WITH CHECK (is_admin_or_system());

COMMIT;
