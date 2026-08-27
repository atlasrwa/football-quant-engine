-- Migration 0013: Create market_prices table
-- Phase 3.2: Time-series market price observations
-- Ownership: CLASS B (System-owned — public read, system/admin write)
--
-- DESIGN DECISION: market_prices is INSERT-only for historical observations.
-- Corrections are handled by inserting a new observation with updated metadata,
-- not by rewriting history. No UPDATE/DELETE triggers are applied here —
-- they are created in 0022_create_phase_3_2_triggers.sql.
--
-- NO uniqueness constraint that would prevent time-series observations.
-- The same match/market/selection can have many price points over time.

BEGIN;

CREATE TABLE IF NOT EXISTS market_prices (
    id              BIGSERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL REFERENCES matches(match_id) ON DELETE RESTRICT,
    -- Market identification
    market_type     TEXT NOT NULL,              -- 'OVER_UNDER', 'MATCH_RESULT', 'BTTS', etc.
    line            DOUBLE PRECISION,           -- e.g. 2.5 for Over/Under 2.5 (NULL for markets without lines)
    selection       TEXT NOT NULL,              -- 'OVER', 'UNDER', 'HOME', 'DRAW', 'AWAY', 'YES', 'NO'
    price_type      TEXT NOT NULL,              -- 'OPENING', 'ENTRY', 'CLOSING', 'LIVE'
    -- Price data
    odds            DOUBLE PRECISION NOT NULL CHECK (odds > 1.0),
    -- Temporal
    observed_at     TIMESTAMPTZ NOT NULL,       -- actual observation timestamp
    -- Provider identity
    source          TEXT NOT NULL,              -- 'pinnacle', 'bet365', 'betfair', etc.
    -- Optional metadata
    raw_payload     JSONB,                      -- provider-specific extra data
    -- Audit
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary query pattern: all prices for a match/market/selection over time
CREATE INDEX idx_mp_match_market_time ON market_prices (match_id, market_type, selection, observed_at);

-- Secondary: by source for provider-specific queries
CREATE INDEX idx_mp_source_time ON market_prices (source, observed_at DESC);

-- Closing price lookup (most common CLV use case)
CREATE INDEX idx_mp_closing ON market_prices (match_id, market_type, selection)
    WHERE price_type = 'CLOSING';

COMMIT;
