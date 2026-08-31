"""Tests for prediction lifecycle integrity, immutability, and proof-of-alpha.

These tests verify the Phase 2.5 production integrity invariants:
1. PredictionEvent is immutable after creation (frozen dataclass)
2. Settlement cannot mutate the original prediction
3. Proof hash is deterministic and uses only immutable fields
4. Settlement does not alter the original proof hash
5. Lifecycle transitions are explicit and correct

These tests serve as regression guards for the economic integrity
of the prediction pipeline.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

import pytest

from src.domain.factories import PredictionEventFactory, SettlementFactory
from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.analysis.evaluator import Signal


def _make_pending_prediction(
    prediction_id: str = "pred-001",
    strategy_id: str = "strat-001",
    match_id: int = 100,
    direction: str = "OVER",
    odds: float = 2.0,
    market_line: float = 2.5,
) -> PredictionEvent:
    """Create a standard PENDING PredictionEvent for testing."""
    return PredictionEvent(
        prediction_id=prediction_id,
        strategy_id=strategy_id,
        strategy_version=1,
        strategy_content_hash="a" * 64,
        model_version_id="model-v1",
        match_id=match_id,
        match_date_unix=1700000000,
        home_team="Arsenal",
        away_team="Chelsea",
        league_id=4759,
        market_type="OVER_UNDER",
        market_line=market_line,
        direction=direction,
        entry_odds=odds,
        model_edge_pct=15.0,
        confidence=85.0,
        recommended_stake=0.05,
        source=PredictionSource.LIVE_SIGNAL,
        status=PredictionStatus.PENDING,
        proof_hash="b" * 64,
        created_at="2024-01-15T12:00:00+00:00",
        settled_at=None,
    )


class TestPredictionImmutability:
    """Verify PredictionEvent cannot be mutated after creation."""

    def test_cannot_modify_prediction_id(self):
        """prediction_id is frozen."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.prediction_id = "new-id"  # type: ignore[misc]

    def test_cannot_modify_strategy_id(self):
        """strategy_id is frozen."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.strategy_id = "new-strategy"  # type: ignore[misc]

    def test_cannot_modify_entry_odds(self):
        """entry_odds is frozen — cannot be changed after prediction is made."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.entry_odds = 3.5  # type: ignore[misc]

    def test_cannot_modify_direction(self):
        """direction is frozen."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.direction = "UNDER"  # type: ignore[misc]

    def test_cannot_modify_status(self):
        """status is frozen — lifecycle transitions happen via Settlement, not mutation."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.status = PredictionStatus.SETTLED_WIN  # type: ignore[misc]

    def test_cannot_modify_proof_hash(self):
        """proof_hash is frozen — cannot be tampered with after creation."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.proof_hash = "forged" * 10  # type: ignore[misc]

    def test_cannot_modify_match_id(self):
        """match_id is frozen."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.match_id = 999  # type: ignore[misc]

    def test_cannot_modify_model_edge(self):
        """model_edge_pct is frozen."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.model_edge_pct = 99.9  # type: ignore[misc]

    def test_cannot_modify_created_at(self):
        """created_at is frozen — timestamp cannot be backdated."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.created_at = "1990-01-01T00:00:00+00:00"  # type: ignore[misc]

    def test_cannot_modify_settled_at(self):
        """settled_at is frozen — settlement cannot be injected into prediction."""
        pe = _make_pending_prediction()
        with pytest.raises(dataclasses.FrozenInstanceError):
            pe.settled_at = "2024-02-01T00:00:00+00:00"  # type: ignore[misc]


class TestSettlementPreservesOriginalPrediction:
    """Settlement creates a SEPARATE record — original prediction is unchanged."""

    def test_settlement_does_not_modify_prediction_object(self):
        """SettlementFactory produces a new Settlement without touching the prediction."""
        pe = _make_pending_prediction(odds=2.0)

        # Record original state
        original_dict = pe.to_dict()

        # Settle the prediction
        settlement = SettlementFactory.settle_prediction(
            prediction=pe,
            actual_total_goals=3,
            actual_home_goals=2,
            actual_away_goals=1,
            closing_odds=1.85,
            stake=1.0,
        )

        # Prediction is completely unchanged
        assert pe.to_dict() == original_dict
        assert pe.status == PredictionStatus.PENDING
        assert pe.settled_at is None

    def test_settlement_is_separate_object(self):
        """Settlement is a distinct object type from PredictionEvent."""
        pe = _make_pending_prediction()
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=3,
            actual_home_goals=2, actual_away_goals=1,
        )

        assert isinstance(settlement, Settlement)
        assert not isinstance(settlement, PredictionEvent)
        assert settlement.prediction_id == pe.prediction_id

    def test_settlement_links_back_via_prediction_id(self):
        """Settlement references the prediction by ID, not by embedding it."""
        pe = _make_pending_prediction(prediction_id="link-test-001")
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=4,
            actual_home_goals=2, actual_away_goals=2,
        )

        assert settlement.prediction_id == "link-test-001"
        assert settlement.match_id == pe.match_id

    def test_settlement_copies_entry_odds_not_reference(self):
        """Settlement records entry_odds as a value copy from prediction."""
        pe = _make_pending_prediction(odds=2.15)
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=3,
            actual_home_goals=1, actual_away_goals=2,
        )

        assert settlement.entry_odds == 2.15


class TestProofHashIntegrity:
    """Proof-of-alpha hash uses only immutable prediction fields."""

    def test_proof_hash_deterministic(self):
        """Same inputs produce same proof hash."""
        h1 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        assert h1 == h2

    def test_proof_hash_changes_with_strategy(self):
        """Different strategy_content_hash produces different proof."""
        h1 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("hash2", 100, "OVER", 2.0, 1700000000)
        assert h1 != h2

    def test_proof_hash_changes_with_match(self):
        """Different match_id produces different proof."""
        h1 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("hash1", 200, "OVER", 2.0, 1700000000)
        assert h1 != h2

    def test_proof_hash_changes_with_direction(self):
        """Different direction produces different proof."""
        h1 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("hash1", 100, "UNDER", 2.0, 1700000000)
        assert h1 != h2

    def test_proof_hash_changes_with_odds(self):
        """Different entry_odds produces different proof."""
        h1 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.5, 1700000000)
        assert h1 != h2

    def test_proof_hash_changes_with_timestamp(self):
        """Different timestamp produces different proof."""
        h1 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", 2.0, 1700000001)
        assert h1 != h2

    def test_proof_hash_is_valid_sha256(self):
        """Proof hash is 64-character hex (SHA-256)."""
        h = PredictionEvent.compute_proof_hash("x" * 64, 1, "OVER", 1.5, 1700000000)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_proof_hash_unchanged_after_settlement(self):
        """Settlement does not alter the prediction's proof hash."""
        pe = _make_pending_prediction()
        original_proof = pe.proof_hash

        # Settle
        SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=3,
            actual_home_goals=2, actual_away_goals=1,
            closing_odds=1.85, stake=1.0,
        )

        # Original prediction proof is untouched
        assert pe.proof_hash == original_proof

    def test_proof_hash_does_not_include_settlement_data(self):
        """Proof hash inputs contain no settlement-time data."""
        # Proof hash is computed from: strategy_content_hash, match_id,
        # direction, entry_odds, timestamp — all pre-match data.
        # Verify by computing proof for same prediction twice and getting same result
        import hashlib
        import json

        canonical = json.dumps({
            "strategy_content_hash": "a" * 64,
            "match_id": 100,
            "direction": "OVER",
            "entry_odds": 2.0,
            "timestamp": 1700000000,
        }, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode()).hexdigest()

        computed = PredictionEvent.compute_proof_hash("a" * 64, 100, "OVER", 2.0, 1700000000)
        assert computed == expected

    def test_proof_hash_none_odds_handled(self):
        """Proof hash handles None entry_odds correctly."""
        h = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", None, 1700000000)
        assert len(h) == 64
        # Same None odds produces same hash
        h2 = PredictionEvent.compute_proof_hash("hash1", 100, "OVER", None, 1700000000)
        assert h == h2


class TestPredictionLifecycleSemantics:
    """Verify lifecycle transition semantics."""

    def test_live_prediction_born_pending(self):
        """Live signal predictions are created in PENDING status."""
        signal = Signal(match_index=0, strategy_name="s1", direction="OVER", condition_strength=0.1, odds=2.0)
        pe = PredictionEventFactory.from_signal(
            signal=signal, strategy_id="strat-1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759,
        )
        assert pe.status == PredictionStatus.PENDING
        assert pe.settled_at is None
        assert pe.source == PredictionSource.LIVE_SIGNAL

    def test_backtest_prediction_born_settled(self):
        """Backtest predictions are created already-settled."""
        pe = PredictionEventFactory.from_backtest_bet(
            strategy_id="strat-1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=100,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759, direction="OVER", odds=2.0,
            model_edge_pct=15.0, outcome="WIN",
        )
        assert pe.status == PredictionStatus.SETTLED_WIN
        assert pe.settled_at is not None
        assert pe.source == PredictionSource.BACKTEST

    def test_paper_trade_prediction_born_pending(self):
        """Paper trade predictions are PENDING (awaiting real match outcome)."""
        signal = Signal(match_index=0, strategy_name="s1", direction="UNDER", condition_strength=0.08, odds=1.9)
        pe = PredictionEventFactory.from_signal(
            signal=signal, strategy_id="strat-1", strategy_version=1,
            strategy_content_hash="a" * 64, match_id=200,
            match_date_unix=1700100000, home_team="C", away_team="D",
            league_id=4759, source=PredictionSource.PAPER_TRADE,
        )
        assert pe.status == PredictionStatus.PENDING
        assert pe.source == PredictionSource.PAPER_TRADE

    def test_settlement_resolves_over_win(self):
        """OVER prediction with goals > line settles as WIN."""
        pe = _make_pending_prediction(direction="OVER", market_line=2.5)
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=3,
            actual_home_goals=2, actual_away_goals=1,
        )
        assert settlement.outcome == SettlementOutcome.WIN

    def test_settlement_resolves_over_loss(self):
        """OVER prediction with goals < line settles as LOSS."""
        pe = _make_pending_prediction(direction="OVER", market_line=2.5)
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=2,
            actual_home_goals=1, actual_away_goals=1,
        )
        assert settlement.outcome == SettlementOutcome.LOSS

    def test_settlement_resolves_push(self):
        """Goals exactly on line settles as PUSH."""
        pe = _make_pending_prediction(direction="OVER", market_line=3.0)
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=3,
            actual_home_goals=2, actual_away_goals=1,
        )
        assert settlement.outcome == SettlementOutcome.PUSH

    def test_settlement_void_when_no_line(self):
        """None market_line results in VOID settlement."""
        pe = PredictionEvent(
            prediction_id="void-test", strategy_id="s1", strategy_version=1,
            strategy_content_hash="a" * 64, model_version_id=None,
            match_id=100, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", market_line=None,
            direction="OVER", entry_odds=2.0, model_edge_pct=10.0,
            confidence=80.0, recommended_stake=0.05,
            source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING,
            proof_hash="f" * 64, created_at="2024-01-01T00:00:00+00:00",
            settled_at=None,
        )
        settlement = SettlementFactory.settle_prediction(
            prediction=pe, actual_total_goals=3,
            actual_home_goals=2, actual_away_goals=1,
        )
        assert settlement.outcome == SettlementOutcome.VOID

    def test_prediction_validation_rejects_invalid_odds(self):
        """entry_odds <= 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="entry_odds must be > 1.0"):
            PredictionEvent(
                prediction_id="bad", strategy_id="s1", strategy_version=1,
                strategy_content_hash="a" * 64, model_version_id=None,
                match_id=1, match_date_unix=1700000000,
                home_team="A", away_team="B", league_id=1,
                market_type="OVER_UNDER", market_line=2.5,
                direction="OVER", entry_odds=0.95,  # Invalid!
                model_edge_pct=10.0, confidence=80.0,
                recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
                status=PredictionStatus.PENDING, proof_hash="f" * 64,
                created_at="2024-01-01T00:00:00+00:00", settled_at=None,
            )

    def test_prediction_validation_rejects_invalid_direction(self):
        """Invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="direction must be"):
            PredictionEvent(
                prediction_id="bad", strategy_id="s1", strategy_version=1,
                strategy_content_hash="a" * 64, model_version_id=None,
                match_id=1, match_date_unix=1700000000,
                home_team="A", away_team="B", league_id=1,
                market_type="OVER_UNDER", market_line=2.5,
                direction="INVALID",  # Invalid!
                entry_odds=2.0, model_edge_pct=10.0, confidence=80.0,
                recommended_stake=0.05, source=PredictionSource.LIVE_SIGNAL,
                status=PredictionStatus.PENDING, proof_hash="f" * 64,
                created_at="2024-01-01T00:00:00+00:00", settled_at=None,
            )

    def test_prediction_validation_rejects_negative_stake(self):
        """Negative recommended_stake raises ValueError."""
        with pytest.raises(ValueError, match="recommended_stake must be non-negative"):
            PredictionEvent(
                prediction_id="bad", strategy_id="s1", strategy_version=1,
                strategy_content_hash="a" * 64, model_version_id=None,
                match_id=1, match_date_unix=1700000000,
                home_team="A", away_team="B", league_id=1,
                market_type="OVER_UNDER", market_line=2.5,
                direction="OVER", entry_odds=2.0,
                model_edge_pct=10.0, confidence=80.0,
                recommended_stake=-0.01,  # Invalid!
                source=PredictionSource.LIVE_SIGNAL,
                status=PredictionStatus.PENDING, proof_hash="f" * 64,
                created_at="2024-01-01T00:00:00+00:00", settled_at=None,
            )
