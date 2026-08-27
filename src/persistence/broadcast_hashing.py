"""Canonical hashing for broadcast payloads and attestation commitments/reveals.

Phase 3.4 extends the existing hashing pattern (src/persistence/hashing.py)
with broadcast and attestation-specific hash functions.

Rules (same as Phase 3.2 hashing):
- SHA-256
- Canonical JSON with sort_keys=True, separators=(",",":")
- UTF-8 encoding
- Deterministic: equivalent payloads ALWAYS produce identical hashes
- Different payloads ALWAYS produce different hashes
- Server-computed: NEVER accepted from clients

Documented canonical representations:

BROADCAST PAYLOAD HASH:
    Fields (sorted alphabetically by key):
    {
        "confidence": <float>,
        "direction": "<string>",
        "entry_odds": <float|null>,
        "match_id": <int>,
        "prediction_id": "<uuid-string>",
        "prediction_timestamp": "<iso8601-string>",
        "proof_hash": "<64-char-hex>",
        "strategy_id": "<uuid-string>",
        "strategy_version": <int>
    }
    Encoding: UTF-8
    Hash: SHA-256 hex digest (64 chars, lowercase)

ATTESTATION COMMITMENT HASH:
    Fields (sorted alphabetically by key):
    {
        "entry_odds": <float|null>,
        "prediction_id": "<uuid-string>",
        "prediction_timestamp": "<iso8601-string>",
        "proof_hash": "<64-char-hex>",
        "strategy_id": "<uuid-string>",
        "strategy_version": <int>
    }
    Encoding: UTF-8
    Hash: SHA-256 hex digest (64 chars, lowercase)

    Note: The commitment MAY reference the existing proof_hash from
    PredictionEvent.compute_proof_hash() — it does NOT replace it.

ATTESTATION REVEAL HASH:
    Fields (sorted alphabetically by key):
    {
        "clv_pct": <float|null>,
        "closing_odds": <float|null>,
        "commitment_hash": "<64-char-hex>",
        "entry_odds": <float|null>,
        "outcome": "<WIN|LOSS|VOID|PUSH>",
        "prediction_id": "<uuid-string>",
        "profit_loss": <float>,
        "settled_at": "<iso8601-string>",
        "settlement_id": "<uuid-string>"
    }
    Encoding: UTF-8
    Hash: SHA-256 hex digest (64 chars, lowercase)

Numeric representation:
- Floats use Python default repr (no trailing zeros forced)
- None/null encoded as JSON null
- Integers as JSON integers

Timestamp representation:
- ISO 8601 string from datetime.isoformat()
- Includes timezone offset
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional


def _canonical_json(obj: dict) -> str:
    """Produce deterministic canonical JSON string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: str) -> str:
    """Compute SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_broadcast_payload_hash(
    prediction_id: str,
    strategy_id: str,
    strategy_version: int,
    direction: str,
    entry_odds: Optional[float],
    confidence: float,
    match_id: int,
    proof_hash: str,
    prediction_timestamp: str,
) -> str:
    """Compute canonical broadcast payload hash.

    This hash ensures broadcast integrity — the same prediction content
    always produces the same payload hash regardless of dispatch channel.

    Args:
        prediction_id: UUID string of the prediction.
        strategy_id: UUID string of the strategy.
        strategy_version: Strategy version number.
        direction: Prediction direction (OVER/UNDER/BACK/LAY).
        entry_odds: Entry odds (None if unavailable).
        confidence: Model confidence [0, 100].
        match_id: Match identifier.
        proof_hash: Existing proof_hash from prediction.
        prediction_timestamp: ISO 8601 prediction creation time.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = _canonical_json({
        "prediction_id": prediction_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "direction": direction,
        "entry_odds": entry_odds,
        "confidence": confidence,
        "match_id": match_id,
        "proof_hash": proof_hash,
        "prediction_timestamp": prediction_timestamp,
    })
    return _sha256(canonical)


def compute_commitment_hash(
    prediction_id: str,
    strategy_id: str,
    strategy_version: int,
    entry_odds: Optional[float],
    proof_hash: str,
    prediction_timestamp: str,
) -> str:
    """Compute attestation commitment hash.

    Cryptographically binds the prediction to its authoritative inputs
    BEFORE settlement. References the existing proof_hash.

    Args:
        prediction_id: UUID string of the prediction.
        strategy_id: UUID string of the strategy.
        strategy_version: Strategy version number.
        entry_odds: Entry odds at prediction time.
        proof_hash: Existing proof_hash from PredictionEvent.compute_proof_hash().
        prediction_timestamp: ISO 8601 prediction creation time.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = _canonical_json({
        "prediction_id": prediction_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "entry_odds": entry_odds,
        "proof_hash": proof_hash,
        "prediction_timestamp": prediction_timestamp,
    })
    return _sha256(canonical)


def compute_reveal_hash(
    prediction_id: str,
    settlement_id: str,
    commitment_hash: str,
    outcome: str,
    entry_odds: Optional[float],
    closing_odds: Optional[float],
    profit_loss: float,
    clv_pct: Optional[float],
    settled_at: str,
) -> str:
    """Compute attestation reveal hash.

    Binds the settlement outcome to the original commitment, completing
    the commit→reveal lifecycle. All fields are server-derived.

    Args:
        prediction_id: UUID string of the prediction.
        settlement_id: UUID string of the settlement.
        commitment_hash: The original commitment hash being revealed.
        outcome: Settlement outcome (WIN/LOSS/VOID/PUSH).
        entry_odds: Entry odds (from prediction).
        closing_odds: Closing odds (from market_prices, may be None).
        profit_loss: Computed P&L.
        clv_pct: Closing line value percentage (may be None).
        settled_at: ISO 8601 settlement timestamp.

    Returns:
        64-char lowercase hex SHA-256.
    """
    canonical = _canonical_json({
        "prediction_id": prediction_id,
        "settlement_id": settlement_id,
        "commitment_hash": commitment_hash,
        "outcome": outcome,
        "entry_odds": entry_odds,
        "closing_odds": closing_odds,
        "profit_loss": profit_loss,
        "clv_pct": clv_pct,
        "settled_at": settled_at,
    })
    return _sha256(canonical)
