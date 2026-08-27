-- Migration 0028: Create validation_runs table
-- Phase 3.3: Statistical validation results
-- Ownership: CLASS D (User+System — system runs validation, user sees results)
--
-- Persists the output of StatisticalValidator.validate().
-- The DB stores results; the application owns validation logic.
-- Do NOT duplicate mathematical formulas in SQL.

BEGIN;

CREATE TABLE IF NOT EXISTS validation_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- What was validated
    backtest_run_id         UUID REFERENCES backtest_runs(id) ON DELETE RESTRICT,
    strategy_id             UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    strategy_version        INTEGER NOT NULL,
    -- Verdict
    status                  TEXT NOT NULL CHECK (status IN ('PASSED', 'FAILED', 'INSUFFICIENT_DATA')),
    -- Statistical results
    p_value                 DOUBLE PRECISION NOT NULL,
    roi_pct                 DOUBLE PRECISION NOT NULL,
    sample_size             INTEGER NOT NULL,
    effect_size             DOUBLE PRECISION NOT NULL,   -- Cohen's d
    ci_lower                DOUBLE PRECISION NOT NULL,   -- Confidence interval
    ci_upper                DOUBLE PRECISION NOT NULL,
    -- Criteria used
    min_sample_required     INTEGER NOT NULL,
    min_roi_required        DOUBLE PRECISION NOT NULL,
    max_p_value             DOUBLE PRECISION NOT NULL,
    -- FDR correction
    fdr_submission_count    INTEGER NOT NULL DEFAULT 1,
    fdr_adjusted_threshold  DOUBLE PRECISION,
    -- Human-readable explanation
    reason                  TEXT NOT NULL,
    -- Metadata
    validated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- FK to strategy version
    FOREIGN KEY (strategy_id, strategy_version)
        REFERENCES strategy_versions(strategy_id, version)
);

-- Strategy validation history
CREATE INDEX idx_vr_strategy ON validation_runs (strategy_id, strategy_version, validated_at DESC);
-- Backtest link
CREATE INDEX idx_vr_backtest ON validation_runs (backtest_run_id) WHERE backtest_run_id IS NOT NULL;

COMMIT;
