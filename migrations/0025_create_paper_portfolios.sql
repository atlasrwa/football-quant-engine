-- Migration 0025: Create paper_portfolios table
-- Phase 3.3: User paper betting portfolios
-- Ownership: CLASS A (User-owned)
--
-- Paper portfolios represent VIRTUAL bankrolls for tracking performance.
-- They NEVER hold real money. No deposits, withdrawals, or custodial balances.
-- A user may have multiple portfolios (e.g., different strategies/markets).

BEGIN;

CREATE TABLE IF NOT EXISTS paper_portfolios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    name                TEXT NOT NULL DEFAULT 'Default',
    currency            TEXT NOT NULL DEFAULT 'USD',
    initial_balance     DOUBLE PRECISION NOT NULL DEFAULT 1000.0 CHECK (initial_balance > 0),
    current_balance     DOUBLE PRECISION NOT NULL DEFAULT 1000.0,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One portfolio name per user
    UNIQUE (user_id, name)
);

-- User's portfolios
CREATE INDEX idx_pp_user ON paper_portfolios (user_id);

-- Auto-update updated_at
CREATE TRIGGER trg_pp_updated_at
    BEFORE UPDATE ON paper_portfolios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
