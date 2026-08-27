-- Migration 0023: Create predictions table
-- Phase 3.3: User prediction records
-- Ownership: CLASS D (User+System — user creates, system settles)
--
-- Maps directly from src/domain/prediction.py PredictionEvent dataclass.
-- proof_hash is ALWAYS server-computed (PredictionEvent.compute_proof_hash()).
-- entry_odds follows invariant I3: > 1.0 OR NULL (never fabricated).
-- status transitions: PENDING → SETTLED_WIN/SETTLED_LOSS/SETTLED_VOID/EXPIRED
-- Only status + settled_at are mutable after creation (trigger in 0033).

BEGIN;

CREATE TABLE IF NOT EXISTS predictions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Ownership
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Strategy provenance
    strategy_id             UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    strategy_version        INTEGER NOT NULL,
    strategy_content_hash   CHAR(64) NOT NULL,
    model_version_id        UUID REFERENCES model_versions(id),
    -- Match reference (surrogate)
    match_id                BIGINT NOT NULL REFERENCES matches(match_id) ON DELETE RESTRICT,
    match_date_unix         BIGINT NOT NULL,
    -- Match context (denormalized for display)
    home_team               TEXT NOT NULL,
    away_team               TEXT NOT NULL,
    league_id               INTEGER NOT NULL,
    -- Market
    market_type             TEXT NOT NULL,
    market_line             DOUBLE PRECISION,
    direction               TEXT NOT NULL CHECK (direction IN ('OVER', 'UNDER', 'BACK', 'LAY')),
    -- Pricing (I3: never fabricated)
    entry_odds              DOUBLE PRECISION CHECK (entry_odds IS NULL OR entry_odds > 1.0),
    -- Model output
    model_edge_pct          DOUBLE PRECISION NOT NULL,
    confidence              DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    recommended_stake       DOUBLE PRECISION NOT NULL CHECK (recommended_stake >= 0),
    -- Source distinction (I12: BACKTEST cannot enter live settlement)
    source                  TEXT NOT NULL CHECK (source IN ('BACKTEST', 'LIVE_SIGNAL', 'PAPER_TRADE')),
    -- Lifecycle
    status                  TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING', 'SETTLED_WIN', 'SETTLED_LOSS', 'SETTLED_VOID', 'EXPIRED')),
    -- Proof of alpha (I10: server-computed, never client-supplied)
    proof_hash              CHAR(64) NOT NULL,
    -- Timestamps
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at              TIMESTAMPTZ,
    -- FK to strategy version
    FOREIGN KEY (strategy_id, strategy_version)
        REFERENCES strategy_versions(strategy_id, version)
);

-- User's predictions
CREATE INDEX idx_pred_user_status ON predictions (user_id, status, created_at DESC);
-- Match lookup (for settlement: find all PENDING predictions for a match)
CREATE INDEX idx_pred_match_pending ON predictions (match_id) WHERE status = 'PENDING';
-- Strategy analytics
CREATE INDEX idx_pred_strategy ON predictions (strategy_id, strategy_version);
-- Proof hash lookup (attestation verification)
CREATE INDEX idx_pred_proof ON predictions (proof_hash);
-- Source filter
CREATE INDEX idx_pred_source ON predictions (source);

COMMIT;
