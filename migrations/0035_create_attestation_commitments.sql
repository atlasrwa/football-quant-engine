-- Migration 0035: Create attestation_commitments table
-- Phase 3.4: Web3-Ready Attestation — cryptographic pre-commitments
-- Ownership: CLASS D (User+System via prediction owner)
--
-- An attestation_commitment cryptographically binds a prediction to its
-- authoritative inputs BEFORE settlement occurs. This enables future
-- on-chain verification without requiring blockchain infrastructure now.
--
-- Critical invariant: commitment.created_at < settlement.settled_at
-- A commitment MUST exist before settlement.
-- A commitment CANNOT be created after settlement.
--
-- INSERT-only: no UPDATE, no DELETE (trigger in 0038).
-- Blockchain fields (chain_id, contract_address, tx_hash, block_number) remain
-- nullable — populated only if/when on-chain submission occurs.

BEGIN;

CREATE TABLE IF NOT EXISTS attestation_commitments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Link to authoritative prediction (1:1)
    prediction_id       UUID NOT NULL UNIQUE REFERENCES predictions(id) ON DELETE RESTRICT,
    -- Server-generated commitment hash (NEVER client-supplied)
    commitment_hash     CHAR(64) NOT NULL,
    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Web3 fields (nullable — future blockchain integration)
    chain_id            BIGINT,
    contract_address    VARCHAR(42),
    tx_hash             VARCHAR(66),
    block_number        BIGINT
);

-- Commitment hash lookup (for verification)
CREATE INDEX idx_ac_commitment_hash ON attestation_commitments (commitment_hash);
-- Prediction lookup (covered by UNIQUE but explicit)
CREATE INDEX idx_ac_prediction ON attestation_commitments (prediction_id);
-- Chain submission tracking
CREATE INDEX idx_ac_chain ON attestation_commitments (chain_id, block_number)
    WHERE chain_id IS NOT NULL;

COMMIT;
