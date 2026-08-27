-- Migration 0021: RLS policies for Phase 3.2 tables
-- Classification:
--   market_prices      → CLASS B (System): all read, system/admin write
--   dataset_versions   → CLASS B (System): all read, system/admin write
--   feature_versions   → CLASS B (System): all read, system/admin write
--   model_versions     → CLASS B (System): all read, system/admin write
--   match_features     → CLASS B (System): all read, system/admin write
--   backtest_runs      → CLASS D (User+System): owner + admin read/write
--   backtest_bets      → CLASS D (User+System): inherits via parent run

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- CLASS B TABLES: Public read, system/admin write
-- ═══════════════════════════════════════════════════════════════

-- market_prices
ALTER TABLE market_prices ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_prices FORCE ROW LEVEL SECURITY;

CREATE POLICY mp_select_all ON market_prices
    FOR SELECT USING (TRUE);

CREATE POLICY mp_insert_system ON market_prices
    FOR INSERT WITH CHECK (is_admin_or_system());

-- dataset_versions
ALTER TABLE dataset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY dv_select_all ON dataset_versions
    FOR SELECT USING (TRUE);

CREATE POLICY dv_insert_system ON dataset_versions
    FOR INSERT WITH CHECK (is_admin_or_system());

-- feature_versions
ALTER TABLE feature_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY fv_select_all ON feature_versions
    FOR SELECT USING (TRUE);

CREATE POLICY fv_insert_system ON feature_versions
    FOR INSERT WITH CHECK (is_admin_or_system());

-- model_versions
ALTER TABLE model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY mv_select_all ON model_versions
    FOR SELECT USING (TRUE);

CREATE POLICY mv_insert_system ON model_versions
    FOR INSERT WITH CHECK (is_admin_or_system());

-- match_features
ALTER TABLE match_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_features FORCE ROW LEVEL SECURITY;

CREATE POLICY mf_select_all ON match_features
    FOR SELECT USING (TRUE);

CREATE POLICY mf_insert_system ON match_features
    FOR INSERT WITH CHECK (is_admin_or_system());

-- ═══════════════════════════════════════════════════════════════
-- CLASS D TABLES: User-owned, private to owner + admin
-- ═══════════════════════════════════════════════════════════════

-- backtest_runs
ALTER TABLE backtest_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_runs FORCE ROW LEVEL SECURITY;

CREATE POLICY br_select_own ON backtest_runs
    FOR SELECT USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY br_insert_own ON backtest_runs
    FOR INSERT WITH CHECK (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY br_update_own ON backtest_runs
    FOR UPDATE USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

-- backtest_bets: ownership inherited through parent backtest_run
ALTER TABLE backtest_bets ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_bets FORCE ROW LEVEL SECURITY;

CREATE POLICY bb_select_own ON backtest_bets
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM backtest_runs br
            WHERE br.id = backtest_bets.run_id
              AND (br.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

CREATE POLICY bb_insert_own ON backtest_bets
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM backtest_runs br
            WHERE br.id = backtest_bets.run_id
              AND (br.user_id = current_app_user_id() OR is_admin_or_system())
        )
    );

COMMIT;
