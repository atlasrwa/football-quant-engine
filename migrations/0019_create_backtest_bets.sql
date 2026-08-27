-- Migration 0019: Create backtest_bets table
-- Phase 3.2: Individual bet records from backtest execution
-- Ownership: CLASS D (User+System — inherits from parent backtest_run)
--
-- IMMUTABLE after parent backtest_run is COMPLETED (trigger in 0022).
-- Missing odds remain NULL — no synthetic data fabricated.
-- Missing closing odds remain NULL — no CLV fabrication.
-- P&L computed by engine logic, stored as-is.

BEGIN;

CREATE TABLE IF NOT EXISTS backtest_bets (
    id                  BIGSERIAL PRIMARY KEY,
    -- Parent run
    run_id              UUID NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    -- Match reference
    match_id            BIGINT NOT NULL REFERENCES matches(match_id) ON DELETE RESTRICT,
    -- Bet details
    fold_index          INTEGER NOT NULL,
    strategy_name       TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('OVER', 'UNDER', 'BACK', 'LAY')),
    -- Pricing (NULL preserved — never fabricated)
    odds                DOUBLE PRECISION NOT NULL CHECK (odds > 1.0),
    stake               DOUBLE PRECISION NOT NULL CHECK (stake > 0),
    -- Outcome
    outcome             TEXT NOT NULL CHECK (outcome IN ('WIN', 'LOSS', 'VOID')),
    profit_loss         DOUBLE PRECISION NOT NULL,
    -- Model metrics
    model_edge_pct      DOUBLE PRECISION NOT NULL,
    -- Real CLV (NULL = unavailable, NEVER fabricated)
    clv_pct             DOUBLE PRECISION,
    -- Source distinction
    source              TEXT NOT NULL DEFAULT 'BACKTEST'
                        CHECK (source IN ('BACKTEST', 'LIVE_SIGNAL', 'PAPER_TRADE')),
    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary query: all bets for a run
CREATE INDEX idx_bb_run ON backtest_bets (run_id);

-- Match-level queries (e.g., "all bets on this match across all runs")
CREATE INDEX idx_bb_match ON backtest_bets (match_id);

-- Fold-level queries
CREATE INDEX idx_bb_run_fold ON backtest_bets (run_id, fold_index);

COMMIT;
