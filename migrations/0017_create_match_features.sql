-- Migration 0017: Create match_features table
-- Phase 3.2: Persisted computed feature vectors
-- Ownership: CLASS B (System-owned — public read, system/admin write)
--
-- Each row stores the computed feature vector for a single match
-- under a specific feature_version configuration. The same match
-- can have features computed under different configurations.
--
-- UNIQUE(match_id, feature_version_id) — one computation per match per config.
-- IMMUTABLE after creation (trigger in 0022).

BEGIN;

CREATE TABLE IF NOT EXISTS match_features (
    id                          BIGSERIAL PRIMARY KEY,
    -- Links
    match_id                    BIGINT NOT NULL REFERENCES matches(match_id) ON DELETE RESTRICT,
    feature_version_id          UUID NOT NULL REFERENCES feature_versions(id) ON DELETE RESTRICT,
    -- Temporal context (denormalized from match for query efficiency)
    date_unix                   BIGINT NOT NULL,
    -- Core feature columns (from MatchFeatures dataclass)
    home_xg_eff_delta_rolling   DOUBLE PRECISION NOT NULL,
    away_xg_eff_delta_rolling   DOUBLE PRECISION NOT NULL,
    home_rolling_form           DOUBLE PRECISION NOT NULL CHECK (home_rolling_form BETWEEN 0 AND 1),
    away_rolling_form           DOUBLE PRECISION NOT NULL CHECK (away_rolling_form BETWEEN 0 AND 1),
    referee_volatility_index    DOUBLE PRECISION NOT NULL CHECK (referee_volatility_index >= 0),
    -- xMetric features (optional — NULL if xMetrics not computed for this version)
    home_xc                     DOUBLE PRECISION,
    away_xc                     DOUBLE PRECISION,
    home_xb                     DOUBLE PRECISION,
    away_xb                     DOUBLE PRECISION,
    home_xo                     DOUBLE PRECISION,
    away_xo                     DOUBLE PRECISION,
    -- Target variable + market data (carried through for backtest settlement)
    total_goals                 SMALLINT NOT NULL,
    over_under_line             DOUBLE PRECISION,
    over_odds                   DOUBLE PRECISION CHECK (over_odds IS NULL OR over_odds > 1.0),
    under_odds                  DOUBLE PRECISION CHECK (under_odds IS NULL OR under_odds > 1.0),
    -- Audit
    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One feature computation per match per version
    UNIQUE (match_id, feature_version_id)
);

-- Primary query: all features for a feature version (ordered chronologically)
CREATE INDEX idx_mf_version_date ON match_features (feature_version_id, date_unix);

-- Lookup by match
CREATE INDEX idx_mf_match ON match_features (match_id);

COMMIT;
