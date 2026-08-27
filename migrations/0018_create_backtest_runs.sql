-- Migration 0018: Create backtest_runs table
-- Phase 3.2: Reproducible backtest execution records
-- Ownership: CLASS D (User+System — user-initiated, results private)
--
-- content_hash is computed from INPUTS only (not outputs):
--   SHA-256(json.dumps({model_version_id, dataset_id}, sort_keys=True))
-- This matches BacktestRun.compute_content_hash() in src/domain/backtest_run.py
--
-- Deduplication: UNIQUE(user_id, content_hash)
-- Same user cannot accidentally create duplicate identical runs.
-- Different users CAN independently run the same configuration.
--
-- Completed runs are IMMUTABLE (trigger in 0022).

BEGIN;

CREATE TABLE IF NOT EXISTS backtest_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Ownership
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Provenance chain
    strategy_id         UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    strategy_version    INTEGER NOT NULL,
    strategy_content_hash CHAR(64) NOT NULL,
    dataset_id          UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE RESTRICT,
    feature_version_id  UUID NOT NULL REFERENCES feature_versions(id) ON DELETE RESTRICT,
    model_version_id    UUID NOT NULL REFERENCES model_versions(id) ON DELETE RESTRICT,
    -- Deterministic identity (hash of inputs)
    content_hash        CHAR(64) NOT NULL,
    -- Lifecycle
    status              TEXT NOT NULL DEFAULT 'RUNNING'
                        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    -- Configuration snapshot (for display/audit without joining model_versions)
    config              JSONB NOT NULL DEFAULT '{}',
    -- Result metrics (NULL while RUNNING, populated on COMPLETED)
    total_bets          INTEGER,
    net_roi_pct         DOUBLE PRECISION,
    win_rate            DOUBLE PRECISION,
    max_drawdown_pct    DOUBLE PRECISION,
    avg_model_edge_pct  DOUBLE PRECISION,
    total_profit_loss   DOUBLE PRECISION,
    total_staked        DOUBLE PRECISION,
    n_folds             INTEGER,
    -- Timestamps
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Deduplication: same user + same inputs = one run
    UNIQUE (user_id, content_hash),
    -- FK to strategy version composite
    FOREIGN KEY (strategy_id, strategy_version)
        REFERENCES strategy_versions(strategy_id, version)
);

-- Primary query: user's runs
CREATE INDEX idx_br_user ON backtest_runs (user_id, created_at DESC);

-- Provenance lookups
CREATE INDEX idx_br_strategy ON backtest_runs (strategy_id, strategy_version);
CREATE INDEX idx_br_model ON backtest_runs (model_version_id);
CREATE INDEX idx_br_dataset ON backtest_runs (dataset_id);
CREATE INDEX idx_br_status ON backtest_runs (status) WHERE status = 'RUNNING';

COMMIT;
