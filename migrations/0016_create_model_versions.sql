-- Migration 0016: Create model_versions table
-- Phase 3.2: Deterministic model/evaluation configuration
-- Ownership: CLASS B (System-owned — public read, system/admin write)
--
-- content_hash is computed as:
--   SHA-256(json.dumps({strategy_content_hash, feature_version_id,
--                       train_window, test_window, step_size, min_odds, max_odds},
--                      sort_keys=True))
-- This matches ModelVersion.compute_content_hash() in src/domain/provenance.py
--
-- Provenance chain:
--   strategy_versions.content_hash → model_versions.strategy_content_hash
--   feature_versions.id → model_versions.feature_version_id
--
-- IMMUTABLE after creation.

BEGIN;

CREATE TABLE IF NOT EXISTS model_versions (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Strategy link (by content hash for provenance integrity)
    strategy_id           UUID NOT NULL REFERENCES strategies(id) ON DELETE RESTRICT,
    strategy_version      INTEGER NOT NULL,
    strategy_content_hash CHAR(64) NOT NULL,
    -- Feature link
    feature_version_id    UUID NOT NULL REFERENCES feature_versions(id) ON DELETE RESTRICT,
    -- Walk-forward configuration
    train_window          INTEGER NOT NULL CHECK (train_window >= 1),
    test_window           INTEGER NOT NULL CHECK (test_window >= 1),
    step_size             INTEGER NOT NULL CHECK (step_size >= 1),
    min_odds              DOUBLE PRECISION NOT NULL CHECK (min_odds > 1.0),
    max_odds              DOUBLE PRECISION NOT NULL CHECK (max_odds > min_odds),
    -- Deterministic identity
    content_hash          CHAR(64) NOT NULL,
    -- Metadata
    created_by            UUID REFERENCES users(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Deduplication
    UNIQUE (content_hash),
    -- FK to strategy version (composite)
    FOREIGN KEY (strategy_id, strategy_version)
        REFERENCES strategy_versions(strategy_id, version)
);

CREATE INDEX idx_mv_strategy ON model_versions (strategy_id, strategy_version);
CREATE INDEX idx_mv_feature ON model_versions (feature_version_id);

COMMIT;
