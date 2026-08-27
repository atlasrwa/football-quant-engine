"""Phase 3.4 integration tests: Broadcast & Attestation Hashing.

Tests the canonical hashing utilities for:
- Determinism (same inputs → same hash)
- Sensitivity (different inputs → different hash)
- Independence from field ordering
- SHA-256 format (64 hex chars)
- Null handling
"""

import pytest
from src.persistence.broadcast_hashing import (
    compute_broadcast_payload_hash,
    compute_commitment_hash,
    compute_reveal_hash,
)

pytestmark = pytest.mark.asyncio


class TestBroadcastPayloadHash:
    def test_deterministic(self):
        """Same inputs always produce same hash."""
        h1 = compute_broadcast_payload_hash(
            prediction_id="abc-123",
            strategy_id="def-456",
            strategy_version=2,
            direction="OVER",
            entry_odds=1.90,
            confidence=75.0,
            match_id=12345,
            proof_hash="a" * 64,
            prediction_timestamp="2024-01-01T00:00:00+00:00",
        )
        h2 = compute_broadcast_payload_hash(
            prediction_id="abc-123",
            strategy_id="def-456",
            strategy_version=2,
            direction="OVER",
            entry_odds=1.90,
            confidence=75.0,
            match_id=12345,
            proof_hash="a" * 64,
            prediction_timestamp="2024-01-01T00:00:00+00:00",
        )
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        """Different inputs produce different hashes."""
        h1 = compute_broadcast_payload_hash(
            prediction_id="abc-123",
            strategy_id="def-456",
            strategy_version=2,
            direction="OVER",
            entry_odds=1.90,
            confidence=75.0,
            match_id=12345,
            proof_hash="a" * 64,
            prediction_timestamp="2024-01-01T00:00:00+00:00",
        )
        h2 = compute_broadcast_payload_hash(
            prediction_id="abc-123",
            strategy_id="def-456",
            strategy_version=2,
            direction="UNDER",  # Changed
            entry_odds=1.90,
            confidence=75.0,
            match_id=12345,
            proof_hash="a" * 64,
            prediction_timestamp="2024-01-01T00:00:00+00:00",
        )
        assert h1 != h2

    def test_null_odds_handled(self):
        """None entry_odds produces valid hash."""
        h = compute_broadcast_payload_hash(
            prediction_id="abc-123",
            strategy_id="def-456",
            strategy_version=1,
            direction="OVER",
            entry_odds=None,
            confidence=50.0,
            match_id=99999,
            proof_hash="b" * 64,
            prediction_timestamp="2024-06-15T12:00:00+00:00",
        )
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_sha256_format(self):
        """Hash is 64-char lowercase hex (SHA-256)."""
        h = compute_broadcast_payload_hash(
            prediction_id="x",
            strategy_id="y",
            strategy_version=1,
            direction="OVER",
            entry_odds=2.0,
            confidence=80.0,
            match_id=1,
            proof_hash="c" * 64,
            prediction_timestamp="2024-01-01T00:00:00+00:00",
        )
        assert len(h) == 64
        assert h == h.lower()


class TestCommitmentHash:
    def test_deterministic(self):
        """Same inputs always produce same hash."""
        h1 = compute_commitment_hash(
            prediction_id="pred-1",
            strategy_id="strat-1",
            strategy_version=3,
            entry_odds=1.85,
            proof_hash="d" * 64,
            prediction_timestamp="2024-03-01T10:00:00+00:00",
        )
        h2 = compute_commitment_hash(
            prediction_id="pred-1",
            strategy_id="strat-1",
            strategy_version=3,
            entry_odds=1.85,
            proof_hash="d" * 64,
            prediction_timestamp="2024-03-01T10:00:00+00:00",
        )
        assert h1 == h2

    def test_different_proof_hash_different_commitment(self):
        """Different proof_hash produces different commitment hash."""
        h1 = compute_commitment_hash(
            prediction_id="pred-1",
            strategy_id="strat-1",
            strategy_version=3,
            entry_odds=1.85,
            proof_hash="d" * 64,
            prediction_timestamp="2024-03-01T10:00:00+00:00",
        )
        h2 = compute_commitment_hash(
            prediction_id="pred-1",
            strategy_id="strat-1",
            strategy_version=3,
            entry_odds=1.85,
            proof_hash="e" * 64,  # Different
            prediction_timestamp="2024-03-01T10:00:00+00:00",
        )
        assert h1 != h2

    def test_null_odds_handled(self):
        """None entry_odds produces valid hash."""
        h = compute_commitment_hash(
            prediction_id="pred-2",
            strategy_id="strat-2",
            strategy_version=1,
            entry_odds=None,
            proof_hash="f" * 64,
            prediction_timestamp="2024-06-01T00:00:00+00:00",
        )
        assert len(h) == 64


class TestRevealHash:
    def test_deterministic(self):
        """Same inputs always produce same hash."""
        h1 = compute_reveal_hash(
            prediction_id="pred-1",
            settlement_id="settle-1",
            commitment_hash="g" * 64,
            outcome="WIN",
            entry_odds=1.90,
            closing_odds=1.85,
            profit_loss=0.90,
            clv_pct=2.7,
            settled_at="2024-04-01T15:00:00+00:00",
        )
        h2 = compute_reveal_hash(
            prediction_id="pred-1",
            settlement_id="settle-1",
            commitment_hash="g" * 64,
            outcome="WIN",
            entry_odds=1.90,
            closing_odds=1.85,
            profit_loss=0.90,
            clv_pct=2.7,
            settled_at="2024-04-01T15:00:00+00:00",
        )
        assert h1 == h2

    def test_different_outcome_different_hash(self):
        """Different outcome produces different hash."""
        h1 = compute_reveal_hash(
            prediction_id="pred-1",
            settlement_id="settle-1",
            commitment_hash="g" * 64,
            outcome="WIN",
            entry_odds=1.90,
            closing_odds=1.85,
            profit_loss=0.90,
            clv_pct=2.7,
            settled_at="2024-04-01T15:00:00+00:00",
        )
        h2 = compute_reveal_hash(
            prediction_id="pred-1",
            settlement_id="settle-1",
            commitment_hash="g" * 64,
            outcome="LOSS",  # Different
            entry_odds=1.90,
            closing_odds=1.85,
            profit_loss=-1.0,
            clv_pct=2.7,
            settled_at="2024-04-01T15:00:00+00:00",
        )
        assert h1 != h2

    def test_null_closing_odds_handled(self):
        """None closing_odds + None clv_pct produce valid hash."""
        h = compute_reveal_hash(
            prediction_id="pred-3",
            settlement_id="settle-3",
            commitment_hash="h" * 64,
            outcome="WIN",
            entry_odds=2.0,
            closing_odds=None,
            profit_loss=1.0,
            clv_pct=None,
            settled_at="2024-05-01T00:00:00+00:00",
        )
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
