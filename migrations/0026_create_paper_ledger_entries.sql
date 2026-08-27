-- Migration 0026: Create paper_ledger_entries table
-- Phase 3.3: Append-only paper betting ledger (CRITICAL TRUST COMPONENT)
-- Ownership: CLASS A (User-owned via portfolio)
--
-- The ledger is the SOURCE OF TRUTH for portfolio state.
-- paper_portfolios.current_balance is a CACHED/MATERIALIZED value.
-- The ledger allows full reconstruction:
--   opening_balance + SUM(amounts) = current_balance
--
-- APPEND-ONLY: No UPDATE, no DELETE (trigger in 0033).
-- Corrections use compensating entries, never history rewriting.

BEGIN;

CREATE TABLE IF NOT EXISTS paper_ledger_entries (
    id                  BIGSERIAL PRIMARY KEY,  -- Monotonically increasing (audit-safe)
    -- Portfolio
    portfolio_id        UUID NOT NULL REFERENCES paper_portfolios(id) ON DELETE RESTRICT,
    -- References (nullable — not all entries are bet-related)
    prediction_id       UUID REFERENCES predictions(id),
    settlement_id       UUID REFERENCES settlements(id),
    -- Entry classification
    entry_type          TEXT NOT NULL CHECK (entry_type IN (
        'OPENING_BALANCE',  -- Initial portfolio creation
        'BET_PLACED',       -- Stake deducted
        'BET_SETTLED',      -- P&L credited/debited
        'ADJUSTMENT'        -- Administrative correction (compensating entry)
    )),
    -- Economics
    amount              DOUBLE PRECISION NOT NULL,  -- +credit / -debit
    balance_after       DOUBLE PRECISION NOT NULL,  -- Running balance snapshot
    -- Context
    metadata            JSONB,                      -- Strategy name, odds, etc.
    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Portfolio ledger (chronological)
CREATE INDEX idx_ple_portfolio ON paper_ledger_entries (portfolio_id, created_at ASC);
-- Prediction dedup (prevent double-crediting)
CREATE INDEX idx_ple_prediction ON paper_ledger_entries (prediction_id) WHERE prediction_id IS NOT NULL;
-- Settlement dedup
CREATE INDEX idx_ple_settlement ON paper_ledger_entries (settlement_id) WHERE settlement_id IS NOT NULL;

COMMIT;
