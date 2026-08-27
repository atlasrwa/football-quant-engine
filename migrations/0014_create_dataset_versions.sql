-- Migration 0014: Create dataset_versions table
-- Phase 3.2: Deterministic dataset snapshots for reproducibility
-- Ownership: CLASS B (System-owned — public read, system/admin write)
--
-- content_hash is computed as: SHA-256(json.dumps(sorted(match_external_ids)))
-- This matches DatasetVersion.compute_content_hash() in src/domain/provenance.py
--
-- A dataset version is IMMUTABLE after creation. No UPDATE allowed.
-- Immutability trigger created in 0022.

BEGIN;

CREATE TABLE IF NOT EXISTS dataset_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Identity
    source          TEXT NOT NULL,              -- 'footystats', 'synthetic', 'mock'
    league_id       INTEGER NOT NULL,
    season          TEXT NOT NULL,
    -- Content description
    n_matches       INTEGER NOT NULL CHECK (n_matches > 0),
    date_range_start BIGINT NOT NULL,          -- earliest match date_unix
    date_range_end  BIGINT NOT NULL,           -- latest match date_unix
    -- Deterministic identity (SHA-256 of sorted match IDs)
    content_hash    CHAR(64) NOT NULL,
    -- Match list (for full reproducibility)
    match_ids       JSONB NOT NULL,            -- sorted array of external match IDs
    -- Metadata
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Deduplication: same content = same dataset
    UNIQUE (content_hash)
);

CREATE INDEX idx_dv_league_season ON dataset_versions (league_id, season);
CREATE INDEX idx_dv_source ON dataset_versions (source);

COMMIT;
