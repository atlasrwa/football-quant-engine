-- Migration 0006: Create matches table with provider-independent identity
-- Phase 3.1-A: Data foundation
-- Ownership: CLASS B (SYSTEM OWNED — ingested by data pipeline)
--
-- Design: surrogate BIGSERIAL PK with (external_source, external_id) uniqueness.
-- The existing engine uses integer Match.id which maps to external_id.
-- Foreign keys throughout the system reference matches.match_id (the surrogate).

BEGIN;

CREATE TABLE IF NOT EXISTS matches (
    match_id        BIGSERIAL PRIMARY KEY,
    -- Provider-independent identity
    external_id     INTEGER NOT NULL,
    external_source TEXT NOT NULL DEFAULT 'footystats',
    -- Core fields (mirrors src/models/match.py)
    date_unix       BIGINT NOT NULL,
    league_id       INTEGER NOT NULL,
    season          TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    home_goals      SMALLINT CHECK (home_goals >= 0),
    away_goals      SMALLINT CHECK (away_goals >= 0),
    total_goals     SMALLINT GENERATED ALWAYS AS (home_goals + away_goals) STORED,
    home_xg         DOUBLE PRECISION CHECK (home_xg IS NULL OR home_xg >= 0),
    away_xg         DOUBLE PRECISION CHECK (away_xg IS NULL OR away_xg >= 0),
    referee         TEXT,
    over_under_line DOUBLE PRECISION CHECK (over_under_line IS NULL OR over_under_line > 0),
    over_odds       DOUBLE PRECISION CHECK (over_odds IS NULL OR over_odds > 1.0),
    under_odds      DOUBLE PRECISION CHECK (under_odds IS NULL OR under_odds > 1.0),
    -- Raw provider payload for reproducibility
    raw_data        JSONB,
    -- Match lifecycle
    status          TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('scheduled', 'live', 'completed', 'postponed', 'cancelled')),
    -- Metadata
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Provider uniqueness: same external_id from same source = same match
    UNIQUE (external_source, external_id)
);

-- Access pattern indexes
CREATE INDEX idx_matches_league_season ON matches (league_id, season);
CREATE INDEX idx_matches_date ON matches (date_unix);
CREATE INDEX idx_matches_status ON matches (status) WHERE status IN ('scheduled', 'live');
CREATE INDEX idx_matches_external ON matches (external_id);

-- Auto-update updated_at
CREATE TRIGGER trg_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS: matches are publicly readable (CLASS B/C), writable only by system/admin
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;

CREATE POLICY matches_select_all ON matches
    FOR SELECT
    USING (TRUE);  -- All authenticated users can read match data

CREATE POLICY matches_insert_system ON matches
    FOR INSERT
    WITH CHECK (is_admin_or_system());

CREATE POLICY matches_update_system ON matches
    FOR UPDATE
    USING (is_admin_or_system());

COMMIT;
