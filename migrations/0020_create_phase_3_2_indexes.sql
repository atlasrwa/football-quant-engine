-- Migration 0020: Additional performance indexes for Phase 3.2
-- Focused on query patterns for provenance chain traversal and large-table access.

BEGIN;

-- market_prices: match + closing price lookup by market type
CREATE INDEX IF NOT EXISTS idx_mp_match_type ON market_prices (match_id, market_type);

-- dataset_versions: hash lookup for dedup on insert
CREATE INDEX IF NOT EXISTS idx_dv_hash ON dataset_versions (content_hash);

-- feature_versions: hash lookup
CREATE INDEX IF NOT EXISTS idx_fv_hash ON feature_versions (content_hash);

-- model_versions: hash lookup
CREATE INDEX IF NOT EXISTS idx_mv_hash ON model_versions (content_hash);

-- backtest_runs: content_hash lookup (dedup check)
CREATE INDEX IF NOT EXISTS idx_br_hash ON backtest_runs (content_hash);

-- backtest_bets: outcome analysis per run
CREATE INDEX IF NOT EXISTS idx_bb_run_outcome ON backtest_bets (run_id, outcome);

-- Provenance chain join optimization:
-- backtest_runs → model_versions → feature_versions → dataset_versions
-- These are already indexed by PK (UUID), but covering indexes help joins:
CREATE INDEX IF NOT EXISTS idx_br_provenance ON backtest_runs (model_version_id, dataset_id, feature_version_id);

COMMIT;
