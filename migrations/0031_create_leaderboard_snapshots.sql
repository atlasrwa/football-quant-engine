-- Migration 0031: Create leaderboard_snapshots table
-- Phase 3.3: Snapshot-based leaderboard rankings
-- Ownership: CLASS B (System-owned — computed by batch job, readable by all)
--
-- Leaderboards are pre-computed snapshots, not live queries.
-- Only PUBLIC strategies/users appear on public leaderboards.
-- Private and unlisted strategies are excluded.

BEGIN;

CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Scope
    scope               TEXT NOT NULL,          -- 'global', 'league:4759', 'metric:xC'
    period_type         TEXT NOT NULL CHECK (period_type IN ('7d', '30d', '90d', 'lifetime')),
    -- Ranking
    rank                INTEGER NOT NULL,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    display_name        TEXT NOT NULL,
    -- Metrics
    score               DOUBLE PRECISION NOT NULL,
    roi_pct             DOUBLE PRECISION,
    win_rate            DOUBLE PRECISION,
    total_bets          INTEGER NOT NULL DEFAULT 0,
    avg_clv_pct         DOUBLE PRECISION,
    -- Snapshot time
    snapshot_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary query: leaderboard by scope + period + time
CREATE INDEX idx_lb_scope_period ON leaderboard_snapshots (scope, period_type, snapshot_at DESC, rank);
-- User's ranking history
CREATE INDEX idx_lb_user ON leaderboard_snapshots (user_id, snapshot_at DESC);

COMMIT;
