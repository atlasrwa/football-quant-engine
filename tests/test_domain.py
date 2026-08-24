"""Comprehensive tests for Phase 2 domain model.

Covers:
- DatasetVersion, FeatureVersion, ModelVersion (provenance)
- BacktestRun, ValidationRun (execution records)
- MarketDefinition, MarketPrice (market types)
- PredictionEvent (canonical prediction record)
- Settlement (outcome resolution)
- PredictionEventFactory, SettlementFactory (pipeline bridges)
- ProvenanceBuilder (chain construction)

Design principles tested:
- Immutability (frozen dataclasses)
- Deterministic content hashes
- Serialization round-trip safety
- Validation invariants
- Provenance chain linkage
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from src.domain.backtest_run import BacktestRun, BacktestStatus, ValidationRun, ValidationStatus
from src.domain.factories import PredictionEventFactory, SettlementFactory
from src.domain.market import MarketDefinition, MarketPrice, MarketType, PriceSide, PriceType
from src.domain.prediction import PredictionEvent, PredictionSource, PredictionStatus
from src.domain.provenance import DatasetVersion, FeatureVersion, ModelVersion
from src.domain.provenance_builder import ProvenanceBuilder
from src.domain.settlement import Settlement, SettlementOutcome
from src.engine.evaluator import Condition, Signal, Strategy
from src.engine.strategy_identity import StrategyIdentity, StrategyRegistry
from src.models.config import StrategyConfig
from src.models.match import Match


# ===========================================================================
# Helpers
# ===========================================================================

def _make_match(
    id: int = 1,
    date_unix: int = 1700000000,
    home_team: str = "Arsenal",
    away_team: str = "Chelsea",
    home_goals: int = 2,
    away_goals: int = 1,
    referee: str = "Michael Oliver",
) -> Match:
    return Match(
        id=id,
        date_unix=date_unix,
        league_id=4759,
        season="2023",
        home_team=home_team,
        away_team=away_team,
        home_goals=home_goals,
        away_goals=away_goals,
        total_goals=home_goals + away_goals,
        home_xg=1.5,
        away_xg=1.0,
        referee=referee,
        over_under_line=2.5,
        over_odds=1.90,
        under_odds=2.00,
    )


def _make_matches(n: int = 20) -> List[Match]:
    return [
        _make_match(id=1000 + i, date_unix=1700000000 + i * 86400)
        for i in range(n)
    ]


def _make_strategy() -> Strategy:
    return Strategy(
        name="Test Strategy",
        metric="xC",
        market="corners_over_under",
        conditions=(Condition(field="home_xC", op=">", value=2.5),),
        logic="and",
        direction="OVER",
        min_odds=1.70,
    )


# ===========================================================================
# DatasetVersion Tests
# ===========================================================================

class TestDatasetVersion:
    """Tests for DatasetVersion provenance type."""

    def test_creation(self):
        dv = DatasetVersion(
            dataset_id="ds-001",
            source="footystats",
            league_id=4759,
            season="2023",
            n_matches=380,
            date_range_start=1693526400,
            date_range_end=1716422400,
            content_hash="abc123",
            created_at="2024-01-01T00:00:00+00:00",
        )
        assert dv.dataset_id == "ds-001"
        assert dv.n_matches == 380
        assert dv.source == "footystats"

    def test_immutability(self):
        dv = DatasetVersion(
            dataset_id="ds-001", source="mock", league_id=4759,
            season="2023", n_matches=10, date_range_start=100,
            date_range_end=200, content_hash="x", created_at="now",
        )
        with pytest.raises(AttributeError):
            dv.n_matches = 999  # type: ignore

    def test_content_hash_deterministic(self):
        ids = [10, 5, 3, 8, 1]
        h1 = DatasetVersion.compute_content_hash(ids)
        h2 = DatasetVersion.compute_content_hash(ids)
        assert h1 == h2

    def test_content_hash_order_independent(self):
        """Hash sorts IDs internally, so order doesn't matter."""
        h1 = DatasetVersion.compute_content_hash([1, 2, 3])
        h2 = DatasetVersion.compute_content_hash([3, 1, 2])
        assert h1 == h2

    def test_content_hash_changes_with_data(self):
        h1 = DatasetVersion.compute_content_hash([1, 2, 3])
        h2 = DatasetVersion.compute_content_hash([1, 2, 3, 4])
        assert h1 != h2

    def test_content_hash_is_valid_sha256(self):
        h = DatasetVersion.compute_content_hash([1, 2, 3])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_to_dict_serialization(self):
        dv = DatasetVersion(
            dataset_id="ds-001", source="mock", league_id=4759,
            season="2023", n_matches=10, date_range_start=100,
            date_range_end=200, content_hash="abc", created_at="now",
        )
        d = dv.to_dict()
        assert d["dataset_id"] == "ds-001"
        assert d["n_matches"] == 10
        # Verify JSON-serializable
        json.dumps(d)


# ===========================================================================
# FeatureVersion Tests
# ===========================================================================

class TestFeatureVersion:
    """Tests for FeatureVersion provenance type."""

    def test_creation(self):
        fv = FeatureVersion(
            feature_version_id="fv-001",
            dataset_id="ds-001",
            xg_rolling_window=5,
            form_rolling_window=6,
            referee_min_matches=5,
            xmetric_coefficients=None,
            content_hash="abc",
            created_at="now",
        )
        assert fv.xg_rolling_window == 5
        assert fv.dataset_id == "ds-001"

    def test_content_hash_deterministic(self):
        h1 = FeatureVersion.compute_content_hash("ds-1", 5, 6, 5, None)
        h2 = FeatureVersion.compute_content_hash("ds-1", 5, 6, 5, None)
        assert h1 == h2

    def test_content_hash_changes_with_params(self):
        h1 = FeatureVersion.compute_content_hash("ds-1", 5, 6, 5, None)
        h2 = FeatureVersion.compute_content_hash("ds-1", 10, 6, 5, None)
        assert h1 != h2

    def test_content_hash_changes_with_dataset(self):
        h1 = FeatureVersion.compute_content_hash("ds-1", 5, 6, 5, None)
        h2 = FeatureVersion.compute_content_hash("ds-2", 5, 6, 5, None)
        assert h1 != h2

    def test_content_hash_changes_with_coefficients(self):
        h1 = FeatureVersion.compute_content_hash("ds-1", 5, 6, 5, None)
        h2 = FeatureVersion.compute_content_hash("ds-1", 5, 6, 5, {"xo_eta": 1.5})
        assert h1 != h2

    def test_immutability(self):
        fv = FeatureVersion(
            feature_version_id="fv-001", dataset_id="ds-001",
            xg_rolling_window=5, form_rolling_window=6,
            referee_min_matches=5, xmetric_coefficients=None,
            content_hash="x", created_at="now",
        )
        with pytest.raises(AttributeError):
            fv.xg_rolling_window = 10  # type: ignore

    def test_to_dict(self):
        fv = FeatureVersion(
            feature_version_id="fv-001", dataset_id="ds-001",
            xg_rolling_window=5, form_rolling_window=6,
            referee_min_matches=5, xmetric_coefficients={"xo_eta": 1.0},
            content_hash="x", created_at="now",
        )
        d = fv.to_dict()
        assert d["xmetric_coefficients"] == {"xo_eta": 1.0}
        json.dumps(d)


# ===========================================================================
# ModelVersion Tests
# ===========================================================================

class TestModelVersion:
    """Tests for ModelVersion provenance type."""

    def test_creation(self):
        mv = ModelVersion(
            model_version_id="mv-001",
            strategy_id="strat-001",
            strategy_version=1,
            strategy_content_hash="abc",
            feature_version_id="fv-001",
            train_window=200,
            test_window=50,
            step_size=50,
            min_odds=1.50,
            max_odds=5.00,
            content_hash="xyz",
            created_at="now",
        )
        assert mv.strategy_id == "strat-001"
        assert mv.train_window == 200

    def test_content_hash_deterministic(self):
        h1 = ModelVersion.compute_content_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = ModelVersion.compute_content_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        assert h1 == h2

    def test_content_hash_changes_with_strategy(self):
        h1 = ModelVersion.compute_content_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = ModelVersion.compute_content_hash("def", "fv-1", 200, 50, 50, 1.5, 5.0)
        assert h1 != h2

    def test_content_hash_changes_with_window(self):
        h1 = ModelVersion.compute_content_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = ModelVersion.compute_content_hash("abc", "fv-1", 100, 50, 50, 1.5, 5.0)
        assert h1 != h2

    def test_content_hash_changes_with_odds(self):
        h1 = ModelVersion.compute_content_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = ModelVersion.compute_content_hash("abc", "fv-1", 200, 50, 50, 1.8, 5.0)
        assert h1 != h2

    def test_to_dict(self):
        mv = ModelVersion(
            model_version_id="mv-001", strategy_id="s-1",
            strategy_version=2, strategy_content_hash="abc",
            feature_version_id="fv-1", train_window=200,
            test_window=50, step_size=50, min_odds=1.5,
            max_odds=5.0, content_hash="xyz", created_at="now",
        )
        d = mv.to_dict()
        assert d["strategy_version"] == 2
        json.dumps(d)


# ===========================================================================
# BacktestRun Tests
# ===========================================================================

class TestBacktestRun:
    """Tests for BacktestRun domain type."""

    def test_creation(self):
        br = BacktestRun(
            run_id="run-001", model_version_id="mv-001",
            strategy_id="s-1", strategy_version=1,
            dataset_id="ds-1", feature_version_id="fv-1",
            status=BacktestStatus.COMPLETED,
            total_bets=150, net_roi_pct=5.2,
            win_rate=0.54, max_drawdown_pct=8.3,
            avg_model_edge_pct=3.1, total_profit_loss=7.8,
            n_folds=5, content_hash="abc",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:01:00Z",
        )
        assert br.status == BacktestStatus.COMPLETED
        assert br.total_bets == 150

    def test_content_hash_deterministic(self):
        h1 = BacktestRun.compute_content_hash("mv-1", "ds-1")
        h2 = BacktestRun.compute_content_hash("mv-1", "ds-1")
        assert h1 == h2

    def test_content_hash_changes_with_model(self):
        h1 = BacktestRun.compute_content_hash("mv-1", "ds-1")
        h2 = BacktestRun.compute_content_hash("mv-2", "ds-1")
        assert h1 != h2

    def test_to_dict_status_serialized(self):
        br = BacktestRun(
            run_id="r-1", model_version_id="mv-1",
            strategy_id="s-1", strategy_version=1,
            dataset_id="ds-1", feature_version_id="fv-1",
            status=BacktestStatus.COMPLETED,
            total_bets=100, net_roi_pct=5.0,
            win_rate=0.55, max_drawdown_pct=7.0,
            avg_model_edge_pct=2.5, total_profit_loss=5.0,
            n_folds=4, content_hash="abc",
            started_at="now", completed_at="now",
        )
        d = br.to_dict()
        assert d["status"] == "COMPLETED"
        json.dumps(d)


# ===========================================================================
# ValidationRun Tests
# ===========================================================================

class TestValidationRun:
    """Tests for ValidationRun domain type."""

    def test_passed_property(self):
        vr = ValidationRun(
            validation_id="v-1", backtest_run_id="r-1",
            strategy_id="s-1", strategy_version=1,
            status=ValidationStatus.PASSED,
            p_value=0.01, roi_pct=5.0, sample_size=300,
            effect_size=0.35, confidence_interval_lower=0.02,
            confidence_interval_upper=0.08,
            min_sample_required=250, min_roi_required=3.0,
            max_p_value=0.05, fdr_submission_count=1,
            fdr_adjusted_threshold=None,
            reason="All gates passed", validated_at="now",
        )
        assert vr.passed is True

    def test_failed_property(self):
        vr = ValidationRun(
            validation_id="v-1", backtest_run_id="r-1",
            strategy_id="s-1", strategy_version=1,
            status=ValidationStatus.FAILED,
            p_value=0.12, roi_pct=1.5, sample_size=300,
            effect_size=0.10, confidence_interval_lower=-0.01,
            confidence_interval_upper=0.03,
            min_sample_required=250, min_roi_required=3.0,
            max_p_value=0.05, fdr_submission_count=1,
            fdr_adjusted_threshold=None,
            reason="ROI below minimum", validated_at="now",
        )
        assert vr.passed is False

    def test_insufficient_data_not_passed(self):
        vr = ValidationRun(
            validation_id="v-1", backtest_run_id="r-1",
            strategy_id="s-1", strategy_version=1,
            status=ValidationStatus.INSUFFICIENT_DATA,
            p_value=0.5, roi_pct=0.0, sample_size=50,
            effect_size=0.0, confidence_interval_lower=0.0,
            confidence_interval_upper=0.0,
            min_sample_required=250, min_roi_required=3.0,
            max_p_value=0.05, fdr_submission_count=1,
            fdr_adjusted_threshold=None,
            reason="Insufficient data", validated_at="now",
        )
        assert vr.passed is False

    def test_to_dict(self):
        vr = ValidationRun(
            validation_id="v-1", backtest_run_id="r-1",
            strategy_id="s-1", strategy_version=1,
            status=ValidationStatus.PASSED,
            p_value=0.03, roi_pct=5.0, sample_size=300,
            effect_size=0.3, confidence_interval_lower=0.01,
            confidence_interval_upper=0.09,
            min_sample_required=250, min_roi_required=3.0,
            max_p_value=0.05, fdr_submission_count=3,
            fdr_adjusted_threshold=0.0167,
            reason="Passed", validated_at="now",
        )
        d = vr.to_dict()
        assert d["status"] == "PASSED"
        assert d["fdr_adjusted_threshold"] == 0.0167
        json.dumps(d)


# ===========================================================================
# MarketDefinition Tests
# ===========================================================================

class TestMarketDefinition:
    """Tests for MarketDefinition domain type."""

    def test_creation(self):
        md = MarketDefinition(
            market_type=MarketType.OVER_UNDER,
            line=2.5,
            description="Over/Under 2.5 Goals",
        )
        assert md.market_type == MarketType.OVER_UNDER
        assert md.line == 2.5

    def test_content_hash_deterministic(self):
        md = MarketDefinition(
            market_type=MarketType.OVER_UNDER, line=2.5,
            description="Over/Under 2.5 Goals",
        )
        h1 = md.content_hash
        h2 = md.content_hash
        assert h1 == h2
        assert len(h1) == 64

    def test_content_hash_changes_with_line(self):
        md1 = MarketDefinition(MarketType.OVER_UNDER, 2.5, "O/U 2.5")
        md2 = MarketDefinition(MarketType.OVER_UNDER, 3.5, "O/U 3.5")
        assert md1.content_hash != md2.content_hash

    def test_content_hash_changes_with_type(self):
        md1 = MarketDefinition(MarketType.OVER_UNDER, 2.5, "O/U")
        md2 = MarketDefinition(MarketType.CORNERS_OVER_UNDER, 2.5, "Corners")
        assert md1.content_hash != md2.content_hash

    def test_to_dict(self):
        md = MarketDefinition(MarketType.OVER_UNDER, 2.5, "O/U 2.5")
        d = md.to_dict()
        assert d["market_type"] == "OVER_UNDER"
        assert d["line"] == 2.5
        json.dumps(d)


# ===========================================================================
# MarketPrice Tests
# ===========================================================================

class TestMarketPrice:
    """Tests for MarketPrice domain type."""

    def test_creation(self):
        mp = MarketPrice(
            match_id=12345,
            market_type=MarketType.OVER_UNDER,
            line=2.5,
            side=PriceSide.OVER,
            price_type=PriceType.ENTRY,
            odds=2.10,
            timestamp=1700000000,
            source="pinnacle",
        )
        assert mp.odds == 2.10
        assert mp.side == PriceSide.OVER

    def test_invalid_odds_raises(self):
        with pytest.raises(ValueError, match="Odds must be > 1.0"):
            MarketPrice(
                match_id=1, market_type=MarketType.OVER_UNDER,
                line=2.5, side=PriceSide.OVER,
                price_type=PriceType.ENTRY,
                odds=0.95, timestamp=100, source=None,
            )

    def test_odds_exactly_one_raises(self):
        with pytest.raises(ValueError, match="Odds must be > 1.0"):
            MarketPrice(
                match_id=1, market_type=MarketType.OVER_UNDER,
                line=2.5, side=PriceSide.OVER,
                price_type=PriceType.ENTRY,
                odds=1.0, timestamp=100, source=None,
            )

    def test_implied_probability(self):
        mp = MarketPrice(
            match_id=1, market_type=MarketType.OVER_UNDER,
            line=2.5, side=PriceSide.OVER,
            price_type=PriceType.ENTRY,
            odds=2.0, timestamp=100, source=None,
        )
        assert mp.implied_probability == pytest.approx(0.5)

    def test_is_valid(self):
        mp = MarketPrice(
            match_id=1, market_type=MarketType.OVER_UNDER,
            line=2.5, side=PriceSide.OVER,
            price_type=PriceType.ENTRY,
            odds=1.95, timestamp=100, source="bet365",
        )
        assert mp.is_valid is True

    def test_to_dict(self):
        mp = MarketPrice(
            match_id=1, market_type=MarketType.OVER_UNDER,
            line=2.5, side=PriceSide.OVER,
            price_type=PriceType.CLOSING,
            odds=1.85, timestamp=100, source="pinnacle",
        )
        d = mp.to_dict()
        assert d["price_type"] == "CLOSING"
        assert d["source"] == "pinnacle"
        json.dumps(d)


# ===========================================================================
# PredictionEvent Tests
# ===========================================================================

class TestPredictionEvent:
    """Tests for PredictionEvent — the core Phase 2 domain object."""

    def _make_prediction(self, **overrides) -> PredictionEvent:
        defaults = {
            "prediction_id": "pred-001",
            "strategy_id": "strat-001",
            "strategy_version": 1,
            "strategy_content_hash": "abc123",
            "model_version_id": "mv-001",
            "match_id": 12345,
            "match_date_unix": 1700000000,
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league_id": 4759,
            "market_type": "OVER_UNDER",
            "market_line": 2.5,
            "direction": "OVER",
            "entry_odds": 2.10,
            "model_edge_pct": 5.2,
            "confidence": 72.0,
            "recommended_stake": 0.02,
            "source": PredictionSource.LIVE_SIGNAL,
            "status": PredictionStatus.PENDING,
            "proof_hash": "proof123",
            "created_at": "2024-01-01T12:00:00Z",
            "settled_at": None,
        }
        defaults.update(overrides)
        return PredictionEvent(**defaults)

    def test_creation(self):
        p = self._make_prediction()
        assert p.prediction_id == "pred-001"
        assert p.direction == "OVER"
        assert p.is_settled is False
        assert p.is_win is None

    def test_immutability(self):
        p = self._make_prediction()
        with pytest.raises(AttributeError):
            p.status = PredictionStatus.SETTLED_WIN  # type: ignore

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="direction must be"):
            self._make_prediction(direction="SIDEWAYS")

    def test_invalid_odds_raises(self):
        with pytest.raises(ValueError, match="entry_odds must be > 1.0"):
            self._make_prediction(entry_odds=0.5)

    def test_none_odds_allowed(self):
        """None entry_odds is valid (odds unavailable)."""
        p = self._make_prediction(entry_odds=None)
        assert p.entry_odds is None

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence must be"):
            self._make_prediction(confidence=101.0)
        with pytest.raises(ValueError, match="confidence must be"):
            self._make_prediction(confidence=-1.0)

    def test_invalid_stake_raises(self):
        with pytest.raises(ValueError, match="recommended_stake must be non-negative"):
            self._make_prediction(recommended_stake=-0.01)

    def test_is_settled_win(self):
        p = self._make_prediction(status=PredictionStatus.SETTLED_WIN)
        assert p.is_settled is True
        assert p.is_win is True

    def test_is_settled_loss(self):
        p = self._make_prediction(status=PredictionStatus.SETTLED_LOSS)
        assert p.is_settled is True
        assert p.is_win is False

    def test_is_settled_void(self):
        p = self._make_prediction(status=PredictionStatus.SETTLED_VOID)
        assert p.is_settled is True
        assert p.is_win is None

    def test_pending_not_settled(self):
        p = self._make_prediction(status=PredictionStatus.PENDING)
        assert p.is_settled is False
        assert p.is_win is None

    def test_proof_hash_deterministic(self):
        h1 = PredictionEvent.compute_proof_hash("abc", 123, "OVER", 2.10, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("abc", 123, "OVER", 2.10, 1700000000)
        assert h1 == h2
        assert len(h1) == 64

    def test_proof_hash_changes_with_direction(self):
        h1 = PredictionEvent.compute_proof_hash("abc", 123, "OVER", 2.10, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("abc", 123, "UNDER", 2.10, 1700000000)
        assert h1 != h2

    def test_proof_hash_changes_with_match(self):
        h1 = PredictionEvent.compute_proof_hash("abc", 123, "OVER", 2.10, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("abc", 456, "OVER", 2.10, 1700000000)
        assert h1 != h2

    def test_proof_hash_changes_with_strategy(self):
        h1 = PredictionEvent.compute_proof_hash("abc", 123, "OVER", 2.10, 1700000000)
        h2 = PredictionEvent.compute_proof_hash("def", 123, "OVER", 2.10, 1700000000)
        assert h1 != h2

    def test_to_dict_serialization(self):
        p = self._make_prediction()
        d = p.to_dict()
        assert d["prediction_id"] == "pred-001"
        assert d["source"] == "LIVE_SIGNAL"
        assert d["status"] == "PENDING"
        assert d["settled_at"] is None
        # Must be JSON-serializable
        json.dumps(d)

    def test_all_sources_valid(self):
        for source in PredictionSource:
            p = self._make_prediction(source=source)
            assert p.source == source

    def test_all_statuses_valid(self):
        for status in PredictionStatus:
            p = self._make_prediction(status=status)
            assert p.status == status


# ===========================================================================
# Settlement Tests
# ===========================================================================

class TestSettlement:
    """Tests for Settlement domain type."""

    def _make_settlement(self, **overrides) -> Settlement:
        defaults = {
            "settlement_id": "settle-001",
            "prediction_id": "pred-001",
            "match_id": 12345,
            "outcome": SettlementOutcome.WIN,
            "actual_total_goals": 3,
            "actual_result": "2-1",
            "entry_odds": 2.10,
            "closing_odds": 1.95,
            "clv_pct": 7.69,
            "stake": 1.0,
            "profit_loss": 1.10,
            "settled_at": "2024-01-01T15:00:00Z",
        }
        defaults.update(overrides)
        return Settlement(**defaults)

    def test_creation(self):
        s = self._make_settlement()
        assert s.outcome == SettlementOutcome.WIN
        assert s.has_clv is True
        assert s.beat_closing_line is True

    def test_no_clv_when_closing_odds_missing(self):
        s = self._make_settlement(closing_odds=None, clv_pct=None)
        assert s.has_clv is False
        assert s.beat_closing_line is None

    def test_negative_clv(self):
        s = self._make_settlement(clv_pct=-3.5)
        assert s.beat_closing_line is False

    def test_invalid_entry_odds_raises(self):
        with pytest.raises(ValueError, match="entry_odds must be > 1.0"):
            self._make_settlement(entry_odds=0.9)

    def test_invalid_closing_odds_raises(self):
        with pytest.raises(ValueError, match="closing_odds must be > 1.0"):
            self._make_settlement(closing_odds=0.5)

    def test_none_odds_allowed(self):
        s = self._make_settlement(entry_odds=None, closing_odds=None, clv_pct=None)
        assert s.entry_odds is None
        assert s.closing_odds is None

    def test_invalid_stake_raises(self):
        with pytest.raises(ValueError, match="stake must be non-negative"):
            self._make_settlement(stake=-1.0)

    def test_compute_clv_valid(self):
        # Entry=2.10, Close=1.95 → (2.10/1.95 - 1)*100 ≈ 7.69%
        clv = Settlement.compute_clv(2.10, 1.95)
        assert clv == pytest.approx(7.6923, rel=1e-3)

    def test_compute_clv_missing_entry(self):
        assert Settlement.compute_clv(None, 1.95) is None

    def test_compute_clv_missing_closing(self):
        assert Settlement.compute_clv(2.10, None) is None

    def test_compute_clv_invalid_odds(self):
        assert Settlement.compute_clv(1.0, 2.0) is None
        assert Settlement.compute_clv(2.0, 1.0) is None

    def test_compute_profit_loss_win(self):
        pnl = Settlement.compute_profit_loss(SettlementOutcome.WIN, 2.10, 1.0)
        assert pnl == pytest.approx(1.10)

    def test_compute_profit_loss_loss(self):
        pnl = Settlement.compute_profit_loss(SettlementOutcome.LOSS, 2.10, 1.0)
        assert pnl == -1.0

    def test_compute_profit_loss_void(self):
        pnl = Settlement.compute_profit_loss(SettlementOutcome.VOID, 2.10, 1.0)
        assert pnl == 0.0

    def test_compute_profit_loss_push(self):
        pnl = Settlement.compute_profit_loss(SettlementOutcome.PUSH, 2.10, 1.0)
        assert pnl == 0.0

    def test_to_dict(self):
        s = self._make_settlement()
        d = s.to_dict()
        assert d["outcome"] == "WIN"
        assert d["clv_pct"] == 7.69
        json.dumps(d)


# ===========================================================================
# PredictionEventFactory Tests
# ===========================================================================

class TestPredictionEventFactory:
    """Tests for factory bridging Signal → PredictionEvent."""

    def test_from_signal(self):
        signal = Signal(
            match_index=0,
            strategy_name="Test Strategy",
            direction="OVER",
            edge=0.052,
            odds=2.10,
        )

        pred = PredictionEventFactory.from_signal(
            signal=signal,
            strategy_id="strat-001",
            strategy_version=1,
            strategy_content_hash="abc123",
            match_id=12345,
            match_date_unix=1700000000,
            home_team="Arsenal",
            away_team="Chelsea",
            league_id=4759,
        )

        assert pred.direction == "OVER"
        assert pred.entry_odds == 2.10
        assert pred.model_edge_pct == pytest.approx(5.2)
        assert pred.status == PredictionStatus.PENDING
        assert pred.source == PredictionSource.LIVE_SIGNAL
        assert pred.strategy_id == "strat-001"
        assert len(pred.proof_hash) == 64
        assert pred.settled_at is None

    def test_from_signal_generates_unique_ids(self):
        signal = Signal(match_index=0, strategy_name="S", direction="OVER", edge=0.05, odds=2.0)
        p1 = PredictionEventFactory.from_signal(
            signal=signal, strategy_id="s", strategy_version=1,
            strategy_content_hash="h", match_id=1, match_date_unix=100,
            home_team="A", away_team="B", league_id=1,
        )
        p2 = PredictionEventFactory.from_signal(
            signal=signal, strategy_id="s", strategy_version=1,
            strategy_content_hash="h", match_id=1, match_date_unix=100,
            home_team="A", away_team="B", league_id=1,
        )
        assert p1.prediction_id != p2.prediction_id

    def test_from_backtest_bet_win(self):
        pred = PredictionEventFactory.from_backtest_bet(
            strategy_id="strat-001",
            strategy_version=1,
            strategy_content_hash="abc",
            match_id=12345,
            match_date_unix=1700000000,
            home_team="Arsenal",
            away_team="Chelsea",
            league_id=4759,
            direction="OVER",
            odds=2.10,
            model_edge_pct=5.0,
            outcome="WIN",
        )
        assert pred.status == PredictionStatus.SETTLED_WIN
        assert pred.source == PredictionSource.BACKTEST
        assert pred.is_settled is True
        assert pred.is_win is True

    def test_from_backtest_bet_loss(self):
        pred = PredictionEventFactory.from_backtest_bet(
            strategy_id="s", strategy_version=1,
            strategy_content_hash="h", match_id=1,
            match_date_unix=100, home_team="A",
            away_team="B", league_id=1,
            direction="UNDER", odds=1.85,
            model_edge_pct=3.0, outcome="LOSS",
        )
        assert pred.status == PredictionStatus.SETTLED_LOSS
        assert pred.is_win is False


# ===========================================================================
# SettlementFactory Tests
# ===========================================================================

class TestSettlementFactory:
    """Tests for SettlementFactory."""

    def _make_pending_prediction(self, direction="OVER", entry_odds=2.10) -> PredictionEvent:
        return PredictionEvent(
            prediction_id="pred-001",
            strategy_id="strat-001",
            strategy_version=1,
            strategy_content_hash="abc",
            model_version_id="mv-001",
            match_id=12345,
            match_date_unix=1700000000,
            home_team="Arsenal",
            away_team="Chelsea",
            league_id=4759,
            market_type="OVER_UNDER",
            market_line=2.5,
            direction=direction,
            entry_odds=entry_odds,
            model_edge_pct=5.0,
            confidence=70.0,
            recommended_stake=0.02,
            source=PredictionSource.LIVE_SIGNAL,
            status=PredictionStatus.PENDING,
            proof_hash="proof",
            created_at="2024-01-01T12:00:00Z",
            settled_at=None,
        )

    def test_settle_over_win(self):
        """OVER prediction with 3 goals on 2.5 line = WIN."""
        pred = self._make_pending_prediction(direction="OVER")
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=3,
            actual_home_goals=2,
            actual_away_goals=1,
            stake=1.0,
        )
        assert settlement.outcome == SettlementOutcome.WIN
        assert settlement.profit_loss == pytest.approx(1.10)
        assert settlement.actual_result == "2-1"

    def test_settle_over_loss(self):
        """OVER prediction with 2 goals on 2.5 line = LOSS."""
        pred = self._make_pending_prediction(direction="OVER")
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=2,
            actual_home_goals=1,
            actual_away_goals=1,
            stake=1.0,
        )
        assert settlement.outcome == SettlementOutcome.LOSS
        assert settlement.profit_loss == -1.0

    def test_settle_under_win(self):
        """UNDER prediction with 2 goals on 2.5 line = WIN."""
        pred = self._make_pending_prediction(direction="UNDER", entry_odds=1.85)
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=2,
            actual_home_goals=1,
            actual_away_goals=1,
            stake=1.0,
        )
        assert settlement.outcome == SettlementOutcome.WIN
        assert settlement.profit_loss == pytest.approx(0.85)

    def test_settle_under_loss(self):
        """UNDER prediction with 4 goals on 2.5 line = LOSS."""
        pred = self._make_pending_prediction(direction="UNDER", entry_odds=1.85)
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=4,
            actual_home_goals=3,
            actual_away_goals=1,
            stake=1.0,
        )
        assert settlement.outcome == SettlementOutcome.LOSS
        assert settlement.profit_loss == -1.0

    def test_settle_with_closing_odds_produces_clv(self):
        """Closing odds provided → CLV calculated."""
        pred = self._make_pending_prediction(entry_odds=2.10)
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=3,
            actual_home_goals=2,
            actual_away_goals=1,
            closing_odds=1.95,
            stake=1.0,
        )
        assert settlement.clv_pct == pytest.approx(7.6923, rel=1e-3)
        assert settlement.has_clv is True
        assert settlement.beat_closing_line is True

    def test_settle_without_closing_odds_no_clv(self):
        """No closing odds → CLV is None."""
        pred = self._make_pending_prediction(entry_odds=2.10)
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=3,
            actual_home_goals=2,
            actual_away_goals=1,
            closing_odds=None,
            stake=1.0,
        )
        assert settlement.clv_pct is None
        assert settlement.has_clv is False

    def test_settle_links_prediction_id(self):
        pred = self._make_pending_prediction()
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=3,
            actual_home_goals=2,
            actual_away_goals=1,
        )
        assert settlement.prediction_id == "pred-001"
        assert settlement.match_id == 12345


# ===========================================================================
# ProvenanceBuilder Tests
# ===========================================================================

class TestProvenanceBuilder:
    """Tests for the provenance chain builder."""

    def test_create_dataset_version(self):
        matches = _make_matches(20)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")

        assert dv.source == "mock"
        assert dv.n_matches == 20
        assert dv.league_id == 4759
        assert dv.season == "2023"
        assert dv.date_range_start == matches[0].date_unix
        assert dv.date_range_end == matches[-1].date_unix
        assert len(dv.content_hash) == 64
        assert len(dv.dataset_id) == 36  # UUID format

    def test_create_dataset_version_empty_raises(self):
        with pytest.raises(ValueError, match="Cannot create DatasetVersion from empty"):
            ProvenanceBuilder.create_dataset_version([], source="mock")

    def test_create_dataset_version_deterministic_hash(self):
        matches = _make_matches(10)
        dv1 = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        dv2 = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        # Same matches → same content hash (IDs differ because UUID)
        assert dv1.content_hash == dv2.content_hash

    def test_create_feature_version(self):
        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        config = StrategyConfig()

        fv = ProvenanceBuilder.create_feature_version(dv, config)

        assert fv.dataset_id == dv.dataset_id
        assert fv.xg_rolling_window == config.xg_rolling_window
        assert fv.form_rolling_window == config.form_rolling_window
        assert fv.referee_min_matches == config.referee_min_matches
        assert len(fv.content_hash) == 64

    def test_create_feature_version_deterministic_hash(self):
        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        config = StrategyConfig()

        fv1 = ProvenanceBuilder.create_feature_version(dv, config)
        fv2 = ProvenanceBuilder.create_feature_version(dv, config)
        assert fv1.content_hash == fv2.content_hash

    def test_create_model_version(self):
        registry = StrategyRegistry()
        strategy = _make_strategy()
        identity = registry.register(strategy, strategy_id="test-strat-001")

        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())

        mv = ProvenanceBuilder.create_model_version(identity, fv)

        assert mv.strategy_id == identity.strategy_id
        assert mv.strategy_version == identity.strategy_version
        assert mv.strategy_content_hash == identity.content_hash
        assert mv.feature_version_id == fv.feature_version_id
        assert mv.train_window == 200
        assert len(mv.content_hash) == 64

    def test_create_backtest_run(self):
        registry = StrategyRegistry()
        strategy = _make_strategy()
        identity = registry.register(strategy, strategy_id="test-strat-002")

        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)

        br = ProvenanceBuilder.create_backtest_run(
            model_version=mv,
            dataset_version=dv,
            feature_version=fv,
            total_bets=150,
            net_roi_pct=5.2,
            win_rate=0.54,
            max_drawdown_pct=8.0,
            avg_model_edge_pct=3.1,
            total_profit_loss=7.8,
            n_folds=5,
        )

        assert br.strategy_id == identity.strategy_id
        assert br.model_version_id == mv.model_version_id
        assert br.dataset_id == dv.dataset_id
        assert br.status == BacktestStatus.COMPLETED
        assert br.total_bets == 150
        assert br.net_roi_pct == 5.2

    def test_create_validation_run_passed(self):
        # Build full chain
        registry = StrategyRegistry()
        identity = registry.register(_make_strategy(), strategy_id="s-1")
        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)
        br = ProvenanceBuilder.create_backtest_run(
            mv, dv, fv, total_bets=300,
            net_roi_pct=5.0, win_rate=0.55,
            max_drawdown_pct=7.0, avg_model_edge_pct=3.0,
            total_profit_loss=15.0, n_folds=5,
        )

        vr = ProvenanceBuilder.create_validation_run(
            backtest_run=br,
            p_value=0.02,
            roi_pct=5.0,
            sample_size=300,
            effect_size=0.35,
            ci_lower=0.01,
            ci_upper=0.09,
        )

        assert vr.status == ValidationStatus.PASSED
        assert vr.passed is True
        assert vr.backtest_run_id == br.run_id

    def test_create_validation_run_insufficient_data(self):
        registry = StrategyRegistry()
        identity = registry.register(_make_strategy(), strategy_id="s-2")
        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)
        br = ProvenanceBuilder.create_backtest_run(
            mv, dv, fv, total_bets=50,
            net_roi_pct=10.0, win_rate=0.60,
            max_drawdown_pct=5.0, avg_model_edge_pct=4.0,
            total_profit_loss=5.0, n_folds=2,
        )

        vr = ProvenanceBuilder.create_validation_run(
            backtest_run=br,
            p_value=0.01,
            roi_pct=10.0,
            sample_size=50,  # Below 250 minimum
            effect_size=0.5,
            ci_lower=0.05,
            ci_upper=0.15,
        )

        assert vr.status == ValidationStatus.INSUFFICIENT_DATA
        assert vr.passed is False
        assert "Insufficient data" in vr.reason

    def test_create_validation_run_failed_roi(self):
        registry = StrategyRegistry()
        identity = registry.register(_make_strategy(), strategy_id="s-3")
        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)
        br = ProvenanceBuilder.create_backtest_run(
            mv, dv, fv, total_bets=300,
            net_roi_pct=1.5, win_rate=0.51,
            max_drawdown_pct=12.0, avg_model_edge_pct=1.0,
            total_profit_loss=4.5, n_folds=5,
        )

        vr = ProvenanceBuilder.create_validation_run(
            backtest_run=br,
            p_value=0.04,
            roi_pct=1.5,  # Below 3% minimum
            sample_size=300,
            effect_size=0.1,
            ci_lower=-0.01,
            ci_upper=0.03,
        )

        assert vr.status == ValidationStatus.FAILED
        assert vr.passed is False
        assert "ROI" in vr.reason

    def test_create_validation_run_failed_pvalue(self):
        registry = StrategyRegistry()
        identity = registry.register(_make_strategy(), strategy_id="s-4")
        matches = _make_matches(10)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)
        br = ProvenanceBuilder.create_backtest_run(
            mv, dv, fv, total_bets=300,
            net_roi_pct=5.0, win_rate=0.53,
            max_drawdown_pct=9.0, avg_model_edge_pct=2.5,
            total_profit_loss=15.0, n_folds=5,
        )

        vr = ProvenanceBuilder.create_validation_run(
            backtest_run=br,
            p_value=0.12,  # Above 0.05 threshold
            roi_pct=5.0,
            sample_size=300,
            effect_size=0.15,
            ci_lower=-0.005,
            ci_upper=0.10,
        )

        assert vr.status == ValidationStatus.FAILED
        assert vr.passed is False
        assert "p-value" in vr.reason

    def test_full_provenance_chain_linkage(self):
        """Verify the entire chain is properly linked end-to-end."""
        registry = StrategyRegistry()
        strategy = _make_strategy()
        identity = registry.register(strategy, strategy_id="chain-test")

        matches = _make_matches(20)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="footystats")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)
        br = ProvenanceBuilder.create_backtest_run(
            mv, dv, fv, total_bets=250,
            net_roi_pct=4.5, win_rate=0.54,
            max_drawdown_pct=6.0, avg_model_edge_pct=2.8,
            total_profit_loss=11.25, n_folds=4,
        )
        vr = ProvenanceBuilder.create_validation_run(
            backtest_run=br,
            p_value=0.03, roi_pct=4.5,
            sample_size=250, effect_size=0.25,
            ci_lower=0.005, ci_upper=0.085,
        )

        # Verify chain linkage
        assert fv.dataset_id == dv.dataset_id
        assert mv.feature_version_id == fv.feature_version_id
        assert mv.strategy_id == identity.strategy_id
        assert mv.strategy_content_hash == identity.content_hash
        assert br.model_version_id == mv.model_version_id
        assert br.dataset_id == dv.dataset_id
        assert br.feature_version_id == fv.feature_version_id
        assert br.strategy_id == identity.strategy_id
        assert vr.backtest_run_id == br.run_id
        assert vr.strategy_id == identity.strategy_id

        # Verify all hashes are valid SHA-256
        for h in [dv.content_hash, fv.content_hash, mv.content_hash, br.content_hash]:
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)


# ===========================================================================
# Integration: End-to-End Pipeline Test
# ===========================================================================

class TestEndToEndPipeline:
    """Integration test: Signal → PredictionEvent → Settlement."""

    def test_signal_to_prediction_to_settlement(self):
        """Full lifecycle: generate prediction from signal, then settle it."""
        # 1. Create a signal (as the evaluator would)
        signal = Signal(
            match_index=0,
            strategy_name="High xC Over",
            direction="OVER",
            edge=0.052,
            odds=2.10,
        )

        # 2. Create prediction from signal
        pred = PredictionEventFactory.from_signal(
            signal=signal,
            strategy_id="strat-high-xc",
            strategy_version=2,
            strategy_content_hash="abc123def456",
            match_id=99001,
            match_date_unix=1700000000,
            home_team="Arsenal",
            away_team="Tottenham",
            league_id=4759,
            confidence=72.0,
            recommended_stake=0.02,
        )

        assert pred.status == PredictionStatus.PENDING
        assert pred.entry_odds == 2.10
        assert pred.direction == "OVER"

        # 3. Match plays: Arsenal 2-1 Tottenham (3 goals > 2.5 = OVER wins)
        settlement = SettlementFactory.settle_prediction(
            prediction=pred,
            actual_total_goals=3,
            actual_home_goals=2,
            actual_away_goals=1,
            closing_odds=1.95,
            stake=1.0,
        )

        assert settlement.outcome == SettlementOutcome.WIN
        assert settlement.profit_loss == pytest.approx(1.10)
        assert settlement.clv_pct == pytest.approx(7.6923, rel=1e-3)
        assert settlement.prediction_id == pred.prediction_id
        assert settlement.actual_result == "2-1"

    def test_backtest_prediction_already_settled(self):
        """Backtest predictions are created pre-settled."""
        pred = PredictionEventFactory.from_backtest_bet(
            strategy_id="strat-001",
            strategy_version=1,
            strategy_content_hash="xyz",
            match_id=88001,
            match_date_unix=1700000000,
            home_team="Liverpool",
            away_team="Man City",
            league_id=4759,
            direction="UNDER",
            odds=1.85,
            model_edge_pct=3.5,
            outcome="LOSS",
        )

        assert pred.is_settled is True
        assert pred.is_win is False
        assert pred.source == PredictionSource.BACKTEST
        assert pred.settled_at is not None

    def test_full_provenance_with_prediction(self):
        """Complete provenance chain ending in a PredictionEvent."""
        # Build provenance
        registry = StrategyRegistry()
        strategy = _make_strategy()
        identity = registry.register(strategy, strategy_id="e2e-strat")

        matches = _make_matches(20)
        dv = ProvenanceBuilder.create_dataset_version(matches, source="mock")
        fv = ProvenanceBuilder.create_feature_version(dv, StrategyConfig())
        mv = ProvenanceBuilder.create_model_version(identity, fv)

        # Generate prediction with full provenance
        signal = Signal(match_index=5, strategy_name=strategy.name,
                        direction="OVER", edge=0.04, odds=1.95)

        pred = PredictionEventFactory.from_signal(
            signal=signal,
            strategy_id=identity.strategy_id,
            strategy_version=identity.strategy_version,
            strategy_content_hash=identity.content_hash,
            match_id=matches[5].id,
            match_date_unix=matches[5].date_unix,
            home_team=matches[5].home_team,
            away_team=matches[5].away_team,
            league_id=matches[5].league_id,
            model_version_id=mv.model_version_id,
        )

        # Verify provenance linkage
        assert pred.strategy_id == identity.strategy_id
        assert pred.strategy_version == identity.strategy_version
        assert pred.strategy_content_hash == identity.content_hash
        assert pred.model_version_id == mv.model_version_id
        assert pred.match_id == matches[5].id
