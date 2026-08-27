-- Migration 0036: Create attestation_reveals table
-- Phase 3.4: Web3-Ready Attestation — post-settlement reveal records
-- Ownership: CLASS D (User+System via prediction owner)
--
-- An attestation_reveal links a commitment to its settlement outcome,
-- completing the commit→reveal lifecycle. The reveal payload contains
-- the full authoritative settlement data (server-derived, never client-supplied).
--
-- Valid lifecycle:
--   PREDICTION CREATED → COMMITMENT CREATED → SETTLEMENT → REVEAL CREATED
--
-- Reject:
--   Reveal without commitment
--   Reveal before settlement
--   Duplicate reveal (UNIQUE constraints)
--   Cross-user operations (RLS)
--
-- INSERT-only: no UPDATE, no DELETE (trigger in 0038).
-- Blockchain fields nullable — future on-chain integration.

BEGIN;

CREATE TABLE IF NOT EXISTS attestation_reveals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Links to commitment (1:1)
    commitment_id       UUID NOT NULL UNIQUE REFERENCES attestation_commitments(id) ON DELETE RESTRICT,
    -- Links to prediction (1:1, redundant with commitment but enables direct queries)
    prediction_id       UUID NOT NULL UNIQUE REFERENCES predictions(id) ON DELETE RESTRICT,
    -- Links to settlement (1:1)
    settlement_id       UUID NOT NULL UNIQUE REFERENCES settlements(id) ON DELETE RESTRICT,
    -- Reveal content
    reveal_payload      JSONB NOT NULL,
    reveal_hash         CHAR(64) NOT NULL,
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Web3 fields (nullable — future blockchain integration)
    chain_id            BIGINT,
    contract_address    VARCHAR(42),
    tx_hash             VARCHAR(66),
    block_number        BIGINT
);

-- Reveal hash lookup (for verification)
CREATE INDEX idx_ar_reveal_hash ON attestation_reveals (reveal_hash);
-- Settlement lookup
CREATE INDEX idx_ar_settlement ON attestation_reveals (settlement_id);
-- Commitment lookup (covered by UNIQUE but explicit)
CREATE INDEX idx_ar_commitment ON attestation_reveals (commitment_id);
-- Chain submission tracking
CREATE INDEX idx_ar_chain ON attestation_reveals (chain_id, block_number)
    WHERE chain_id IS NOT NULL;

COMMIT;
