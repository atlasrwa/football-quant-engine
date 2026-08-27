"""PostgreSQL repository for attestation_commitments and attestation_reveals.

Append-only cryptographic attestation records. Implements the commit→reveal
lifecycle with strict ordering constraints:
  - Commitment must be created BEFORE settlement
  - Reveal must be created AFTER settlement
  - Reveal requires an existing commitment

Both tables are INSERT-only (trigger-enforced).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import asyncpg


class PgAttestationRepository:
    """Repository for attestation commitments and reveals."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    # ═══════════════════════════════════════════════════════════════
    # COMMITMENTS
    # ═══════════════════════════════════════════════════════════════

    async def create_commitment(
        self,
        commitment_id: UUID,
        prediction_id: UUID,
        commitment_hash: str,
        created_at: Optional[datetime] = None,
    ) -> dict:
        """Create an attestation commitment.

        Idempotent via UNIQUE(prediction_id). Returns existing if duplicate.

        Args:
            commitment_id: Pre-generated UUID.
            prediction_id: The prediction being committed.
            commitment_hash: Server-computed SHA-256 commitment hash.
            created_at: Override timestamp (defaults to NOW()).

        Returns:
            The created or existing commitment record.
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO attestation_commitments (id, prediction_id, commitment_hash, created_at)
            VALUES ($1, $2, $3, COALESCE($4, NOW()))
            ON CONFLICT (prediction_id) DO NOTHING
            RETURNING *
            """,
            commitment_id, prediction_id, commitment_hash, created_at,
        )
        if row:
            return dict(row)
        # Already exists — return existing (idempotent)
        return await self.get_commitment_by_prediction(prediction_id)

    async def get_commitment_by_id(self, commitment_id: UUID) -> Optional[dict]:
        """Get a commitment by its ID."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_commitments WHERE id = $1",
            commitment_id,
        )
        return dict(row) if row else None

    async def get_commitment_by_prediction(self, prediction_id: UUID) -> Optional[dict]:
        """Get the commitment for a prediction."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_commitments WHERE prediction_id = $1",
            prediction_id,
        )
        return dict(row) if row else None

    async def get_commitment_by_hash(self, commitment_hash: str) -> Optional[dict]:
        """Get a commitment by its hash (for verification)."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_commitments WHERE commitment_hash = $1",
            commitment_hash,
        )
        return dict(row) if row else None

    # ═══════════════════════════════════════════════════════════════
    # REVEALS
    # ═══════════════════════════════════════════════════════════════

    async def create_reveal(
        self,
        reveal_id: UUID,
        commitment_id: UUID,
        prediction_id: UUID,
        settlement_id: UUID,
        reveal_payload: dict,
        reveal_hash: str,
        created_at: Optional[datetime] = None,
    ) -> dict:
        """Create an attestation reveal.

        Idempotent via UNIQUE(commitment_id). Returns existing if duplicate.

        Args:
            reveal_id: Pre-generated UUID.
            commitment_id: The commitment being revealed.
            prediction_id: The prediction (redundant, for direct queries).
            settlement_id: The authoritative settlement.
            reveal_payload: Full reveal content (server-derived).
            reveal_hash: SHA-256 of canonical reveal payload.
            created_at: Override timestamp (defaults to NOW()).

        Returns:
            The created or existing reveal record.
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO attestation_reveals (
                id, commitment_id, prediction_id, settlement_id,
                reveal_payload, reveal_hash, created_at
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, COALESCE($7, NOW()))
            ON CONFLICT (commitment_id) DO NOTHING
            RETURNING *
            """,
            reveal_id, commitment_id, prediction_id, settlement_id,
            reveal_payload, reveal_hash, created_at,
        )
        if row:
            return dict(row)
        # Already exists — return existing (idempotent)
        return await self.get_reveal_by_commitment(commitment_id)

    async def get_reveal_by_id(self, reveal_id: UUID) -> Optional[dict]:
        """Get a reveal by its ID."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_reveals WHERE id = $1",
            reveal_id,
        )
        return dict(row) if row else None

    async def get_reveal_by_commitment(self, commitment_id: UUID) -> Optional[dict]:
        """Get the reveal for a commitment."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_reveals WHERE commitment_id = $1",
            commitment_id,
        )
        return dict(row) if row else None

    async def get_reveal_by_prediction(self, prediction_id: UUID) -> Optional[dict]:
        """Get the reveal for a prediction."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_reveals WHERE prediction_id = $1",
            prediction_id,
        )
        return dict(row) if row else None

    async def get_reveal_by_settlement(self, settlement_id: UUID) -> Optional[dict]:
        """Get the reveal for a settlement."""
        row = await self._conn.fetchrow(
            "SELECT * FROM attestation_reveals WHERE settlement_id = $1",
            settlement_id,
        )
        return dict(row) if row else None

    # ═══════════════════════════════════════════════════════════════
    # PROVENANCE QUERIES
    # ═══════════════════════════════════════════════════════════════

    async def get_full_attestation(self, prediction_id: UUID) -> Optional[dict]:
        """Get full attestation provenance for a prediction.

        Returns commitment + reveal (if exists) in a single dict.
        """
        row = await self._conn.fetchrow(
            """
            SELECT
                ac.id AS commitment_id,
                ac.prediction_id,
                ac.commitment_hash,
                ac.created_at AS committed_at,
                ac.chain_id AS commitment_chain_id,
                ac.contract_address AS commitment_contract_address,
                ac.tx_hash AS commitment_tx_hash,
                ac.block_number AS commitment_block_number,
                ar.id AS reveal_id,
                ar.settlement_id,
                ar.reveal_payload,
                ar.reveal_hash,
                ar.created_at AS revealed_at,
                ar.chain_id AS reveal_chain_id,
                ar.contract_address AS reveal_contract_address,
                ar.tx_hash AS reveal_tx_hash,
                ar.block_number AS reveal_block_number
            FROM attestation_commitments ac
            LEFT JOIN attestation_reveals ar ON ar.commitment_id = ac.id
            WHERE ac.prediction_id = $1
            """,
            prediction_id,
        )
        return dict(row) if row else None
