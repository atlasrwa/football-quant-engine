-- Batch 12: Closing Odds & Production Scheduler Schema
-- Migration: 003_closing_odds_scheduler.sql
-- Idempotent: uses IF NOT EXISTS throughout.

-- ═══════════════════════════════════════════════════════════════
-- CLOSING ODDS OBSERVATIONS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS closing_odds_observations (
    observation_id VARCHAR(16) PRIMARY KEY,
    fixture_id VARCHAR(16) NOT NULL,
    market VARCHAR(50) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    line DOUBLE PRECISION NOT NULL DEFAULT 0,
    decimal_odds DOUBLE PRECISION NOT NULL,
    bookmaker VARCHAR(100) DEFAULT '',
    source VARCHAR(50) NOT NULL DEFAULT '',
    closing_timestamp DOUBLE PRECISION NOT NULL,
    timestamp_semantics VARCHAR(30) NOT NULL DEFAULT 'PROVIDER_ESTIMATED',
    kickoff_timestamp DOUBLE PRECISION DEFAULT 0,
    retrieved_at DOUBLE PRECISION DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'VALID',
    provider_event_id VARCHAR(100) DEFAULT '',
    raw_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_closing_odds_fixture ON closing_odds_observations(fixture_id);
CREATE INDEX IF NOT EXISTS idx_closing_odds_market ON closing_odds_observations(market);
CREATE INDEX IF NOT EXISTS idx_closing_odds_status ON closing_odds_observations(status);
CREATE INDEX IF NOT EXISTS idx_closing_odds_source ON closing_odds_observations(source);
CREATE INDEX IF NOT EXISTS idx_closing_odds_timestamp ON closing_odds_observations(closing_timestamp);

-- ═══════════════════════════════════════════════════════════════
-- CLV CALCULATIONS (upgraded from Batch 10)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS clv_calculations (
    trade_id VARCHAR(16) PRIMARY KEY,
    entry_odds DOUBLE PRECISION NOT NULL,
    closing_odds DOUBLE PRECISION NOT NULL,
    clv DOUBLE PRECISION NOT NULL,
    methodology VARCHAR(30) NOT NULL DEFAULT 'PRICE_BASED',
    entry_implied_prob DOUBLE PRECISION NOT NULL,
    closing_implied_prob DOUBLE PRECISION NOT NULL,
    is_positive BOOLEAN NOT NULL,
    is_genuine BOOLEAN NOT NULL DEFAULT FALSE,
    closing_source VARCHAR(50) DEFAULT '',
    closing_bookmaker VARCHAR(100) DEFAULT '',
    overround DOUBLE PRECISION,
    status VARCHAR(20) NOT NULL DEFAULT 'VALID',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clv_genuine ON clv_calculations(is_genuine);
CREATE INDEX IF NOT EXISTS idx_clv_positive ON clv_calculations(is_positive);

-- ═══════════════════════════════════════════════════════════════
-- SCHEDULER JOBS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS scheduler_jobs (
    job_id VARCHAR(12) PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    scheduled_at DOUBLE PRECISION NOT NULL,
    started_at DOUBLE PRECISION DEFAULT 0,
    completed_at DOUBLE PRECISION DEFAULT 0,
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    timeout_seconds DOUBLE PRECISION DEFAULT 300,
    error_message TEXT DEFAULT '',
    result_data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_type ON scheduler_jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_status ON scheduler_jobs(status);
CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_scheduled ON scheduler_jobs(scheduled_at);

-- ═══════════════════════════════════════════════════════════════
-- FIXTURE VERSIONS (for rescheduling tracking)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS fixture_versions (
    version_id VARCHAR(12) PRIMARY KEY,
    fixture_id VARCHAR(16) NOT NULL,
    version_number INTEGER NOT NULL,
    kickoff_timestamp BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    recorded_at DOUBLE PRECISION NOT NULL,
    change_reason VARCHAR(50) DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fixture_versions_fixture ON fixture_versions(fixture_id);
CREATE INDEX IF NOT EXISTS idx_fixture_versions_num ON fixture_versions(fixture_id, version_number);

-- ═══════════════════════════════════════════════════════════════
-- OPERATIONAL EVENTS (Batch 12 extensions)
-- ═══════════════════════════════════════════════════════════════

-- Reuses existing forward_events table (created in 002).
-- No schema change needed — event_type is a VARCHAR that accepts new values.
