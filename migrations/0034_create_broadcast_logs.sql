-- Migration 0034: Create broadcast_logs table
-- Phase 3.4: Signal Dispatch — immutable delivery audit records
-- Ownership: CLASS D (User+System — user owns via prediction, system dispatches)
--
-- A broadcast_log is an immutable delivery/audit record for a dispatched signal.
-- One prediction → many broadcasts (one per channel/destination).
-- One broadcast per (prediction_id, channel, destination) — idempotent.
--
-- Prediction ≠ Broadcast ≠ Delivery Attempt ≠ Attestation
-- This table tracks broadcast/delivery, NOT predictions or attestations.
--
-- INSERT-only: no UPDATE, no DELETE (trigger in 0038).

BEGIN;

CREATE TABLE IF NOT EXISTS broadcast_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Ownership (denormalized for RLS efficiency)
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    -- Link to authoritative prediction
    prediction_id       UUID NOT NULL REFERENCES predictions(id) ON DELETE RESTRICT,
    -- Channel/destination
    channel             VARCHAR(50) NOT NULL CHECK (channel IN (
                            'web', 'mobile', 'telegram', 'discord', 'email', 'webhook'
                        )),
    destination         VARCHAR(500),
    -- Delivery status
    status              VARCHAR(30) NOT NULL CHECK (status IN (
                            'PENDING', 'DISPATCHED', 'DELIVERED', 'FAILED', 'RETRY'
                        )),
    -- Payload integrity
    payload_hash        CHAR(64) NOT NULL,
    -- Deep link (stable, public reference)
    deep_link           VARCHAR(500),
    -- Dispatch timing
    dispatched_at       TIMESTAMPTZ,
    -- Error information (for failed/retry)
    error_code          VARCHAR(100),
    error_message       TEXT,
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Idempotency: one broadcast per prediction+channel+destination
    UNIQUE (prediction_id, channel, destination)
);

-- User's broadcast history
CREATE INDEX idx_bl_user_status ON broadcast_logs (user_id, status, created_at DESC);
-- Prediction broadcast lookup
CREATE INDEX idx_bl_prediction ON broadcast_logs (prediction_id, created_at DESC);
-- Channel analytics
CREATE INDEX idx_bl_channel_status ON broadcast_logs (channel, status);
-- Dispatch time window queries
CREATE INDEX idx_bl_dispatched ON broadcast_logs (dispatched_at) WHERE dispatched_at IS NOT NULL;
-- Payload dedup verification
CREATE INDEX idx_bl_payload_hash ON broadcast_logs (payload_hash);

COMMIT;
