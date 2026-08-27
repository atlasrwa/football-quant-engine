-- Migration 0022: Immutability triggers for Phase 3.2 tables
-- Enforces INSERT-only semantics on provenance/historical data.
--
-- Design decisions:
--   market_prices: INSERT-only (historical observations never rewritten)
--   dataset_versions: INSERT-only (snapshots are immutable)
--   feature_versions: INSERT-only (configurations are immutable)
--   model_versions: INSERT-only (configurations are immutable)
--   match_features: INSERT-only (computed features are immutable)
--   backtest_runs: Status can transition RUNNING→COMPLETED/FAILED, metrics
--                  can be written once on completion. After COMPLETED, fully immutable.
--   backtest_bets: INSERT-only (bet records never change after creation)

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- Generic INSERT-only enforcement (no UPDATE, no DELETE)
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION prevent_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% on % is forbidden — table is INSERT-only',
        TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

-- market_prices: INSERT-only
CREATE TRIGGER trg_mp_no_update
    BEFORE UPDATE ON market_prices
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_mp_no_delete
    BEFORE DELETE ON market_prices
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- dataset_versions: INSERT-only
CREATE TRIGGER trg_dv_no_update
    BEFORE UPDATE ON dataset_versions
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_dv_no_delete
    BEFORE DELETE ON dataset_versions
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- feature_versions: INSERT-only
CREATE TRIGGER trg_fv_no_update
    BEFORE UPDATE ON feature_versions
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_fv_no_delete
    BEFORE DELETE ON feature_versions
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- model_versions: INSERT-only
CREATE TRIGGER trg_mv_no_update
    BEFORE UPDATE ON model_versions
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_mv_no_delete
    BEFORE DELETE ON model_versions
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- match_features: INSERT-only
CREATE TRIGGER trg_mf_no_update
    BEFORE UPDATE ON match_features
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_mf_no_delete
    BEFORE DELETE ON match_features
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- backtest_bets: INSERT-only
CREATE TRIGGER trg_bb_no_update
    BEFORE UPDATE ON backtest_bets
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

CREATE TRIGGER trg_bb_no_delete
    BEFORE DELETE ON backtest_bets
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- ═══════════════════════════════════════════════════════════════
-- backtest_runs: Controlled mutability
-- RUNNING → COMPLETED/FAILED is allowed (status + metrics + completed_at)
-- After COMPLETED or FAILED: fully immutable
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION enforce_backtest_run_lifecycle()
RETURNS TRIGGER AS $$
BEGIN
    -- Once completed or failed, no further changes allowed
    IF OLD.status IN ('COMPLETED', 'FAILED') THEN
        RAISE EXCEPTION 'Backtest run % is % and cannot be modified',
            OLD.id, OLD.status;
    END IF;

    -- While RUNNING, only allow: status change + metrics + completed_at
    IF OLD.status = 'RUNNING' THEN
        -- Protect immutable provenance fields
        IF OLD.user_id != NEW.user_id
           OR OLD.strategy_id != NEW.strategy_id
           OR OLD.strategy_version != NEW.strategy_version
           OR OLD.strategy_content_hash != NEW.strategy_content_hash
           OR OLD.dataset_id != NEW.dataset_id
           OR OLD.feature_version_id != NEW.feature_version_id
           OR OLD.model_version_id != NEW.model_version_id
           OR OLD.content_hash != NEW.content_hash
           OR OLD.config != NEW.config
           OR OLD.started_at != NEW.started_at
           OR OLD.created_at != NEW.created_at THEN
            RAISE EXCEPTION 'Cannot modify provenance fields on backtest run %', OLD.id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_br_lifecycle
    BEFORE UPDATE ON backtest_runs
    FOR EACH ROW EXECUTE FUNCTION enforce_backtest_run_lifecycle();

-- Prevent deletion of backtest runs
CREATE TRIGGER trg_br_no_delete
    BEFORE DELETE ON backtest_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

COMMIT;
