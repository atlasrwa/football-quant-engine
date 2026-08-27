-- Migration 0030: Create reputation_scores table
-- Phase 3.3: Derived reputation metrics
-- Ownership: CLASS B (System-owned — computed by batch job, readable by all)
--
-- Reputation is DERIVED from authoritative settled prediction data.
-- Users cannot directly write reputation scores.
-- Computed by a scheduled service reading from settlements.

BEGIN;

CREATE TABLE IF NOT EXISTS reputation_scores (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Period
    period_type         TEXT NOT NULL CHECK (period_type IN ('7d', '30d', '90d', 'lifetime')),
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    -- Metrics (derived from settlements)
    total_predictions   INTEGER NOT NULL DEFAULT 0,
    settled_predictions INTEGER NOT NULL DEFAULT 0,
    win_rate            DOUBLE PRECISION,
    roi_pct             DOUBLE PRECISION,
    avg_clv_pct         DOUBLE PRECISION,      -- NULL if CLV unavailable
    max_drawdown_pct    DOUBLE PRECISION,
    -- Composite score
    reputation_score    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    rank                INTEGER,
    -- Metadata
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One score per user per period type per period start
    UNIQUE (user_id, period_type, period_start)
);

-- Leaderboard queries (rank by score)
CREATE INDEX idx_rs_period_score ON reputation_scores (period_type, period_start, reputation_score DESC);
-- User profile
CREATE INDEX idx_rs_user ON reputation_scores (user_id, period_type);

COMMIT;
