-- Migration 0015: Create feature_versions table
-- Phase 3.2: Deterministic feature computation configuration
-- Ownership: CLASS B (System-owned — public read, system/admin write)
--
-- content_hash is computed as:
--   SHA-256(json.dumps({dataset_id, xg_rolling_window, form_rolling_window,
--                       referee_min_matches, xmetric_coefficients}, sort_keys=True))
-- This matches FeatureVersion.compute_content_hash() in src/domain/provenance.py
--
-- Relationship: dataset_versions → feature_versions
-- Same dataset + same config = same content_hash (deduplicated)
-- IMMUTABLE after creation.

BEGIN;

CREATE TABLE IF NOT EXISTS feature_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Parent dataset
    dataset_id      UUID NOT NULL REFERENCES dataset_versions(id) ON DELETE RESTRICT,
    -- Feature configuration (matches StrategyConfig feature params)
    xg_rolling_window   INTEGER NOT NULL CHECK (xg_rolling_window >= 1),
    form_rolling_window INTEGER NOT NULL CHECK (form_rolling_window >= 1),
    referee_min_matches INTEGER NOT NULL CHECK (referee_min_matches >= 1),
    -- Optional xMetric coefficients (NULL = not used)
    xmetric_coefficients JSONB,
    -- Deterministic identity
    content_hash    CHAR(64) NOT NULL,
    -- Metadata
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Deduplication
    UNIQUE (content_hash)
);

CREATE INDEX idx_fv_dataset ON feature_versions (dataset_id);

COMMIT;
