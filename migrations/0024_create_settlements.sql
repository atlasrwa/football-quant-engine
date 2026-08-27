-- Migration 0024: Create settlements table
-- Phase 3.3: Immutable settlement records
-- Ownership: CLASS D (inherits via prediction owner)
--
-- Maps from src/domain/settlement.py Settlement dataclass.
-- INSERT-only: no UPDATE, no DELETE (trigger in 0033).
-- prediction_id is UNIQUE: one settlement per prediction (I14: idempotent).
-- closing_odds come from market_prices (I9: never client-supplied).
-- outcome is computed by SettlementFactory._resolve_outcome() (I11).
-- CLV is NULL when closing_odds unavailable (I4).

BEGIN;

CREATE TABLE IF NOT EXISTS settlements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Link to prediction (1:1, idempotent)
    prediction_id       UUID NOT NULL UNIQUE REFERENCES predictions(id) ON DELETE RESTRICT,
    -- Match reference
    match_id            BIGINT NOT NULL REFERENCES matches(match_id) ON DELETE RESTRICT,
    -- Outcome (I11: server-derived from match result)
    outcome             TEXT NOT NULL CHECK (outcome IN ('WIN', 'LOSS', 'VOID', 'PUSH')),
    actual_total_goals  SMALLINT NOT NULL,
    actual_result       TEXT NOT NULL,          -- e.g. "2-1"
    -- Odds (I9: closing_odds from authoritative source only)
    entry_odds          DOUBLE PRECISION CHECK (entry_odds IS NULL OR entry_odds > 1.0),
    closing_odds        DOUBLE PRECISION CHECK (closing_odds IS NULL OR closing_odds > 1.0),
    -- CLV (I4: NULL if closing_odds unavailable)
    clv_pct             DOUBLE PRECISION,
    -- Economics
    stake               DOUBLE PRECISION NOT NULL CHECK (stake >= 0),
    profit_loss         DOUBLE PRECISION NOT NULL,
    -- Timestamps
    settled_at          TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Match settlement lookup
CREATE INDEX idx_settle_match ON settlements (match_id);
-- Prediction lookup (covered by UNIQUE but explicit for clarity)
CREATE INDEX idx_settle_prediction ON settlements (prediction_id);
-- User analytics via prediction join
CREATE INDEX idx_settle_outcome ON settlements (outcome);

COMMIT;
