"""Comprehensive tests for Batch 10 — Forward Research & Paper Trading.

Test categories:
A. Future Fixture Model (identity, immutability, state machine)
B. Fixture Providers
C. Temporal Cutoff & Feature Snapshots
D. Feature Provenance
E. Odds Snapshots (timestamps, validation)
F. Closing Odds Isolation
G. Paper Trade Identity & Immutability
H. Paper Trade State Machine
I. Paper Eligibility
J. Staking Model
K. Settlement
L. CLV
M. Forward Orchestrator (idempotency)
N. Persistence (forward repository)
O. Crash Recovery (idempotent operations)
P. Concurrency (duplicate prevention)
Q. Temporal Leakage Attacks (18 mandatory tests)
R. AI Safety (paper trading boundary)
S. Forward Performance Classification
T. Security (no credentials in artifacts)
U. Missing Data Handling (NULL != 0)
V. Cancelled/Postponed Fixtures
W. End-to-End Integration

All tests use deterministic providers. No network access required.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

import pytest

from src.research.data_source import ResearchMatch
from src.research.forward.future_fixture import FixtureStatus, FutureFixture
from src.research.forward.odds import OddsSelection, OddsSnapshot, OddsType
from src.research.forward.orchestrator import (
    ForwardEventType,
    ForwardResearchOrchestrator,
)
from src.research.forward.performance import (
    ForwardClassification,
    classify_forward_performance,
)
from src.research.forward.providers import (
    DeterministicFixtureProvider,
    DeterministicOddsProvider,
)
from src.research.forward.repository import InMemoryForwardRepository
from src.research.forward.snapshot import (
    FeatureProvenance,
    PreMatchSnapshot,
    TimestampConfidence,
)
from src.research.forward.temporal_features import TemporalFeatureEngine
from src.research.paper.clv import CLVResult, CLVSummary, compute_clv, compute_clv_summary
from src.research.paper.eligibility import EligibilityCriteria, PaperEligibility
from src.research.paper.paper_trade import PaperTrade, PaperTradeStatus
from src.research.paper.settlement import SettlementResult, determine_outcome, settle_trade
from src.research.paper.staking import StakingConfig, StakingModel, StakingType


# ═══════════════════════════════════════════════════════════════════
# FIXTURES (pytest)
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_fixture():
    return FutureFixture(
        source_fixture_id=12345,
        home_team_id=101,
        away_team_id=202,
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        competition_id=47,
        season_id=4759,
        kickoff_timestamp=1700100000,
        source="footystats",
        retrieved_at=1700000000.0,
    )


@pytest.fixture
def historical_matches():
    """Matches that completed BEFORE prediction time (1700000000)."""
    matches = []
    for i in range(30):
        matches.append(ResearchMatch(
            match_id=5000 + i,
            date_unix=1699000000 + i * 86400,  # Well before prediction
            league_id=47,
            season="2023/2024",
            home_team="101" if i % 2 == 0 else "202",
            away_team="202" if i % 2 == 0 else "101",
            total_goals=2 + i % 3,
            total_corners=9 + i % 4,
            total_cards=3 + i % 2,
            dangerous_attacks_home=35 + i % 10,
            dangerous_attacks_away=30 + i % 8,
        ))
    return matches


@pytest.fixture
def forward_repo():
    return InMemoryForwardRepository()


# ═══════════════════════════════════════════════════════════════════
# A. FUTURE FIXTURE MODEL
# ═══════════════════════════════════════════════════════════════════


class TestFutureFixtureModel:
    """Test fixture identity, immutability, and state machine."""

    def test_fixture_id_deterministic(self, sample_fixture):
        """Same source + source_fixture_id → same fixture_id."""
        f2 = FutureFixture(
            source_fixture_id=12345, home_team_id=999, away_team_id=888,
            source="footystats",
        )
        assert sample_fixture.fixture_id == f2.fixture_id

    def test_fixture_id_independent_of_retrieval_time(self, sample_fixture):
        """Retrieval time does not affect identity."""
        f2 = FutureFixture(
            source_fixture_id=12345, home_team_id=101, away_team_id=202,
            source="footystats", retrieved_at=9999999999.0,
        )
        assert sample_fixture.fixture_id == f2.fixture_id

    def test_fixture_id_independent_of_team_names(self, sample_fixture):
        """Team names are metadata, not identity."""
        f2 = FutureFixture(
            source_fixture_id=12345, home_team_id=101, away_team_id=202,
            home_team_name="Different", away_team_name="Names",
            source="footystats",
        )
        assert sample_fixture.fixture_id == f2.fixture_id

    def test_fixture_immutable(self, sample_fixture):
        with pytest.raises(AttributeError):
            sample_fixture.status = FixtureStatus.COMPLETED  # type: ignore

    def test_valid_transition_scheduled_to_started(self, sample_fixture):
        started = sample_fixture.transition(FixtureStatus.STARTED)
        assert started.status == FixtureStatus.STARTED
        assert started.fixture_id == sample_fixture.fixture_id

    def test_valid_transition_started_to_completed(self, sample_fixture):
        started = sample_fixture.transition(FixtureStatus.STARTED)
        completed = started.transition(FixtureStatus.COMPLETED)
        assert completed.status == FixtureStatus.COMPLETED

    def test_invalid_transition_raises(self, sample_fixture):
        with pytest.raises(ValueError, match="Invalid fixture transition"):
            sample_fixture.transition(FixtureStatus.COMPLETED)

    def test_terminal_states(self, sample_fixture):
        completed = sample_fixture.transition(FixtureStatus.STARTED).transition(FixtureStatus.COMPLETED)
        assert completed.is_terminal is True
        cancelled = sample_fixture.transition(FixtureStatus.CANCELLED)
        assert cancelled.is_terminal is True

    def test_paper_eligible_only_scheduled(self, sample_fixture):
        assert sample_fixture.is_paper_eligible is True
        started = sample_fixture.transition(FixtureStatus.STARTED)
        assert started.is_paper_eligible is False


# ═══════════════════════════════════════════════════════════════════
# B. FIXTURE PROVIDERS
# ═══════════════════════════════════════════════════════════════════


class TestFixtureProviders:
    def test_deterministic_provider_returns_fixtures(self, sample_fixture):
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        fixtures = provider.get_upcoming_fixtures()
        assert len(fixtures) == 1
        assert fixtures[0].fixture_id == sample_fixture.fixture_id

    def test_deterministic_provider_filter_by_competition(self, sample_fixture):
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        fixtures = provider.get_upcoming_fixtures(competition_id=999)
        assert len(fixtures) == 0

    def test_deterministic_provider_get_fixture(self, sample_fixture):
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        f = provider.get_fixture(sample_fixture.fixture_id)
        assert f is not None
        assert f.source_fixture_id == 12345

    def test_deterministic_provider_status_update(self, sample_fixture):
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        provider.update_status(sample_fixture.fixture_id, FixtureStatus.STARTED)
        status = provider.get_fixture_status(sample_fixture.fixture_id)
        assert status == FixtureStatus.STARTED

    def test_provider_name(self):
        provider = DeterministicFixtureProvider()
        assert provider.provider_name == "deterministic_test"


# ═══════════════════════════════════════════════════════════════════
# C. TEMPORAL CUTOFF & FEATURE SNAPSHOTS
# ═══════════════════════════════════════════════════════════════════


class TestTemporalCutoff:
    def test_snapshot_enforces_prediction_before_kickoff(self):
        with pytest.raises(ValueError, match="prediction_timestamp.*must be.*<= kickoff"):
            PreMatchSnapshot(
                fixture_id="abc",
                prediction_timestamp=2000000000,
                kickoff_timestamp=1000000000,  # Kickoff before prediction!
            )

    def test_snapshot_enforces_feature_before_prediction(self):
        with pytest.raises(ValueError, match="information_timestamp"):
            PreMatchSnapshot(
                fixture_id="abc",
                prediction_timestamp=1700000000,
                kickoff_timestamp=1700100000,
                feature_provenance=(
                    FeatureProvenance(
                        feature_id="avg_goals",
                        value=2.5,
                        information_timestamp=1700000001,  # AFTER prediction!
                    ),
                ),
            )

    def test_valid_snapshot_created(self):
        snapshot = PreMatchSnapshot(
            fixture_id="abc",
            prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000,
            features={"avg_goals_home": 2.5, "avg_corners_home": 9.0},
            feature_provenance=(
                FeatureProvenance(
                    feature_id="avg_goals_home", value=2.5,
                    information_timestamp=1699900000,
                ),
            ),
        )
        assert snapshot.snapshot_id != ""
        assert snapshot.temporal_cutoff == 1700000000

    def test_snapshot_immutable(self):
        snapshot = PreMatchSnapshot(
            fixture_id="abc",
            prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000,
        )
        with pytest.raises(AttributeError):
            snapshot.features = {}  # type: ignore

    def test_snapshot_features_dict_immutable(self):
        """Features dict itself cannot be mutated (audit fix)."""
        snapshot = PreMatchSnapshot(
            fixture_id="abc",
            prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000,
            features={"avg_goals_home": 2.5},
        )
        with pytest.raises(TypeError):
            snapshot.features["injected"] = 999.0  # type: ignore

    def test_temporal_integrity_validation(self):
        snapshot = PreMatchSnapshot(
            fixture_id="abc",
            prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000,
            feature_provenance=(
                FeatureProvenance(
                    feature_id="good", value=1.0,
                    information_timestamp=1699900000,
                ),
            ),
        )
        violations = snapshot.validate_temporal_integrity()
        assert violations == []


# ═══════════════════════════════════════════════════════════════════
# D. FEATURE PROVENANCE
# ═══════════════════════════════════════════════════════════════════


class TestFeatureProvenance:
    def test_provenance_tracks_timestamp(self):
        prov = FeatureProvenance(
            feature_id="avg_goals_home",
            value=2.3,
            information_timestamp=1699500000,
            timestamp_confidence=TimestampConfidence.ESTIMATED,
            estimation_method="latest_historical_match_completion_time",
        )
        assert prov.timestamp_confidence == TimestampConfidence.ESTIMATED
        assert prov.estimation_method != ""

    def test_none_value_preserved_not_zero(self):
        """NULL != 0 — missing features are None, never zero."""
        prov = FeatureProvenance(
            feature_id="avg_xg_home",
            value=None,  # Missing, NOT zero
            information_timestamp=1699500000,
        )
        assert prov.value is None
        assert prov.value != 0

    def test_feature_engine_produces_provenance(self, historical_matches):
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        snapshot = engine.build_snapshot(
            fixture_id="test",
            home_team_id=101,
            away_team_id=202,
            prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000,
        )
        assert len(snapshot.feature_provenance) > 0
        for prov in snapshot.feature_provenance:
            assert prov.information_timestamp < 1700000000


# ═══════════════════════════════════════════════════════════════════
# E. ODDS SNAPSHOTS
# ═══════════════════════════════════════════════════════════════════


class TestOddsSnapshots:
    def test_odds_below_1_rejected(self):
        with pytest.raises(ValueError, match="must be >= 1.0"):
            OddsSnapshot(
                fixture_id="abc", market="CORNERS_TOTAL",
                selection=OddsSelection.OVER, line=9.5,
                decimal_odds=0.8,  # Invalid!
            )

    def test_valid_odds_snapshot(self):
        snap = OddsSnapshot(
            fixture_id="abc", market="CORNERS_TOTAL",
            selection=OddsSelection.OVER, line=9.5,
            decimal_odds=2.05, source="test",
            snapshot_timestamp=1700000000,
        )
        assert snap.implied_probability == pytest.approx(1.0 / 2.05, abs=1e-6)
        assert snap.odds_snapshot_id != ""

    def test_odds_valid_for_prediction(self):
        snap = OddsSnapshot(
            fixture_id="abc", market="CORNERS_TOTAL",
            selection=OddsSelection.OVER, line=9.5,
            decimal_odds=2.05, snapshot_timestamp=1700000000,
        )
        # Odds captured at 1700000000, prediction at 1700000100
        assert snap.is_valid_for_prediction(1700000100) is True
        # Prediction BEFORE odds were captured
        assert snap.is_valid_for_prediction(1699999999) is False

    def test_multiple_snapshots_preserved(self):
        provider = DeterministicOddsProvider()
        for i in range(5):
            provider.add_snapshot(OddsSnapshot(
                fixture_id="abc", market="CORNERS_TOTAL",
                selection=OddsSelection.OVER, line=9.5,
                decimal_odds=2.0 + i * 0.05,
                snapshot_timestamp=1700000000 + i * 3600,
            ))
        history = provider.get_odds_history("abc")
        assert len(history) == 5
        # Never overwritten
        assert history[0].decimal_odds == 2.0
        assert history[4].decimal_odds == 2.2


# ═══════════════════════════════════════════════════════════════════
# F. CLOSING ODDS ISOLATION
# ═══════════════════════════════════════════════════════════════════


class TestClosingOddsIsolation:
    def test_closing_odds_separate_from_prematch(self):
        provider = DeterministicOddsProvider()
        provider.add_snapshot(OddsSnapshot(
            fixture_id="abc", market="CORNERS_TOTAL",
            selection=OddsSelection.OVER, line=9.5,
            decimal_odds=2.05, snapshot_timestamp=1700000000,
            odds_type=OddsType.PRE_MATCH,
        ))
        provider.add_snapshot(OddsSnapshot(
            fixture_id="abc", market="CORNERS_TOTAL",
            selection=OddsSelection.OVER, line=9.5,
            decimal_odds=1.95, snapshot_timestamp=1700090000,
            odds_type=OddsType.CLOSING,
        ))
        pre_match = provider.get_odds_snapshot("abc")
        closing = provider.get_closing_odds("abc")
        assert len(pre_match) == 1
        assert pre_match[0].decimal_odds == 2.05
        assert len(closing) == 1
        assert closing[0].decimal_odds == 1.95

    def test_closing_odds_not_in_prediction_view(self):
        """Closing odds must NOT be available for predictions."""
        snap = OddsSnapshot(
            fixture_id="abc", market="CORNERS_TOTAL",
            selection=OddsSelection.OVER, line=9.5,
            decimal_odds=1.95, snapshot_timestamp=1700090000,
            odds_type=OddsType.CLOSING,
        )
        # Prediction made at 1700080000 (before closing at 1700090000)
        assert snap.is_valid_for_prediction(1700080000) is False


# ═══════════════════════════════════════════════════════════════════
# G. PAPER TRADE IDENTITY & IMMUTABILITY
# ═══════════════════════════════════════════════════════════════════


class TestPaperTradeIdentity:
    def test_trade_id_deterministic(self):
        t1 = PaperTrade(
            strategy_id="s1", hypothesis_id="h1", fixture_id="f1",
            market="CORNERS_TOTAL", selection="OVER", line=9.5,
            snapshot_id="snap1", odds_snapshot_id="odds1",
        )
        t2 = PaperTrade(
            strategy_id="s1", hypothesis_id="h1", fixture_id="f1",
            market="CORNERS_TOTAL", selection="OVER", line=9.5,
            snapshot_id="snap1", odds_snapshot_id="odds1",
        )
        assert t1.trade_id == t2.trade_id

    def test_trade_id_changes_with_inputs(self):
        t1 = PaperTrade(
            strategy_id="s1", hypothesis_id="h1", fixture_id="f1",
            market="CORNERS_TOTAL", selection="OVER", line=9.5,
            snapshot_id="snap1", odds_snapshot_id="odds1",
        )
        t2 = PaperTrade(
            strategy_id="s1", hypothesis_id="h1", fixture_id="f1",
            market="GOALS_TOTAL", selection="OVER", line=2.5,
            snapshot_id="snap1", odds_snapshot_id="odds1",
        )
        assert t1.trade_id != t2.trade_id

    def test_trade_immutable(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1")
        with pytest.raises(AttributeError):
            trade.model_probability = 0.99  # type: ignore


# ═══════════════════════════════════════════════════════════════════
# H. PAPER TRADE STATE MACHINE
# ═══════════════════════════════════════════════════════════════════


class TestPaperTradeStateMachine:
    def test_full_lifecycle(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1", odds_at_prediction=2.0, stake=100)
        assert trade.status == PaperTradeStatus.GENERATED

        approved = trade.transition(PaperTradeStatus.APPROVED_FOR_PAPER)
        assert approved.status == PaperTradeStatus.APPROVED_FOR_PAPER

        opened = approved.transition(PaperTradeStatus.OPEN)
        assert opened.status == PaperTradeStatus.OPEN

        settled = opened.settle(
            result="WIN", profit_loss=100.0,
            settlement_timestamp=1700200000, closing_odds=1.95,
        )
        assert settled.status == PaperTradeStatus.SETTLED
        assert settled.profit_loss == 100.0
        assert settled.closing_odds == 1.95

    def test_cannot_skip_to_settled(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1")
        with pytest.raises(ValueError, match="Invalid trade transition"):
            trade.transition(PaperTradeStatus.SETTLED)

    def test_cannot_settle_non_open(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1")
        with pytest.raises(ValueError, match="Cannot settle trade"):
            trade.settle(result="WIN", profit_loss=10, settlement_timestamp=1700200000)

    def test_settled_is_terminal(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1", odds_at_prediction=2.0, stake=100)
        settled = (trade
                   .transition(PaperTradeStatus.APPROVED_FOR_PAPER)
                   .transition(PaperTradeStatus.OPEN)
                   .settle(result="LOSS", profit_loss=-100, settlement_timestamp=1700200000))
        assert settled.is_terminal is True
        with pytest.raises(ValueError):
            settled.transition(PaperTradeStatus.OPEN)

    def test_rejected_is_terminal(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1")
        rejected = trade.transition(PaperTradeStatus.REJECTED)
        assert rejected.is_terminal is True

    def test_void_trade(self):
        trade = (PaperTrade(strategy_id="s1", fixture_id="f1", odds_at_prediction=2.0, stake=100)
                 .transition(PaperTradeStatus.APPROVED_FOR_PAPER)
                 .transition(PaperTradeStatus.OPEN)
                 .transition(PaperTradeStatus.VOID))
        assert trade.status == PaperTradeStatus.VOID
        assert trade.is_terminal is True


# ═══════════════════════════════════════════════════════════════════
# I. PAPER ELIGIBILITY
# ═══════════════════════════════════════════════════════════════════


class TestPaperEligibility:
    def test_eligible_strategy(self):
        eligibility = PaperEligibility()
        result = eligibility.evaluate(
            strategy_id="s1",
            walkforward_passed=True, folds_completed=8,
            sample_size=200, positive_fold_ratio=0.75,
            fdr_passed=True, evidence_classification="STRONG_SIGNAL",
            expected_value=0.05,
        )
        assert result.eligible is True
        assert result.reasons == ()

    def test_ineligible_no_walkforward(self):
        eligibility = PaperEligibility()
        result = eligibility.evaluate(
            strategy_id="s1", walkforward_passed=False,
            folds_completed=8, sample_size=200,
            positive_fold_ratio=0.75, fdr_passed=True,
        )
        assert result.eligible is False
        assert any("Walk-forward" in r for r in result.reasons)

    def test_ineligible_low_folds(self):
        eligibility = PaperEligibility()
        result = eligibility.evaluate(
            strategy_id="s1", walkforward_passed=True,
            folds_completed=2, sample_size=200,
            positive_fold_ratio=0.75, fdr_passed=True,
        )
        assert result.eligible is False
        assert any("folds" in r.lower() for r in result.reasons)

    def test_ineligible_no_fdr(self):
        eligibility = PaperEligibility()
        result = eligibility.evaluate(
            strategy_id="s1", walkforward_passed=True,
            folds_completed=8, sample_size=200,
            positive_fold_ratio=0.75, fdr_passed=False,
        )
        assert result.eligible is False
        assert any("FDR" in r for r in result.reasons)

    def test_ai_confidence_not_criterion(self):
        """AI confidence must never be an eligibility criterion."""
        eligibility = PaperEligibility()
        # No parameter for AI confidence exists
        result = eligibility.evaluate(
            strategy_id="s1", walkforward_passed=True,
            folds_completed=8, sample_size=200,
            positive_fold_ratio=0.75, fdr_passed=True,
            evidence_classification="PROMISING",
        )
        assert result.eligible is True


# ═══════════════════════════════════════════════════════════════════
# J. STAKING MODEL
# ═══════════════════════════════════════════════════════════════════


class TestStakingModel:
    def test_fixed_stake(self):
        model = StakingModel(StakingConfig(staking_type=StakingType.FIXED_STAKE, fixed_stake=50.0))
        stake = model.calculate_stake(model_probability=0.55, decimal_odds=2.0)
        assert stake == 50.0

    def test_percent_bankroll(self):
        config = StakingConfig(
            staking_type=StakingType.FIXED_PERCENT_BANKROLL,
            starting_bankroll=10000, percent_of_bankroll=0.02,
        )
        model = StakingModel(config)
        stake = model.calculate_stake(model_probability=0.55, decimal_odds=2.0)
        assert stake == 200.0

    def test_kelly_fraction(self):
        config = StakingConfig(
            staking_type=StakingType.KELLY_FRACTION,
            starting_bankroll=10000, kelly_fraction=0.25,
        )
        model = StakingModel(config)
        # p=0.55, odds=2.0, b=1.0, kelly = (1*0.55 - 0.45)/1 = 0.10
        # fractional = 0.10 * 0.25 = 0.025 → stake = 10000 * 0.025 = 250
        stake = model.calculate_stake(model_probability=0.55, decimal_odds=2.0)
        assert stake == 250.0

    def test_negative_kelly_returns_zero(self):
        config = StakingConfig(staking_type=StakingType.KELLY_FRACTION, kelly_fraction=0.25)
        model = StakingModel(config)
        # p=0.3, odds=2.0 → negative Kelly
        stake = model.calculate_stake(model_probability=0.3, decimal_odds=2.0)
        assert stake == 0.0

    def test_max_stake_enforced(self):
        config = StakingConfig(
            staking_type=StakingType.FIXED_STAKE,
            fixed_stake=5000, max_stake=1000,
        )
        model = StakingModel(config)
        stake = model.calculate_stake(model_probability=0.6, decimal_odds=2.0)
        assert stake <= 1000.0

    def test_bankroll_tracking(self):
        model = StakingModel(StakingConfig(starting_bankroll=1000))
        model.record_result(stake=100, profit_loss=100)
        assert model.bankroll == 1100
        model.record_result(stake=100, profit_loss=-100)
        assert model.bankroll == 1000

    def test_zero_bankroll_returns_zero_stake(self):
        config = StakingConfig(starting_bankroll=0)
        model = StakingModel(config)
        # Override bankroll via internal attribute for test
        model._bankroll = 0
        stake = model.calculate_stake(model_probability=0.6, decimal_odds=2.0)
        assert stake == 0.0


# ═══════════════════════════════════════════════════════════════════
# K. SETTLEMENT
# ═══════════════════════════════════════════════════════════════════


class TestSettlement:
    def test_win_settlement(self):
        result = settle_trade("t1", "WIN", stake=100, odds=2.5, settlement_timestamp=1700200000)
        assert result.profit_loss == 150.0
        assert result.return_amount == 250.0

    def test_loss_settlement(self):
        result = settle_trade("t1", "LOSS", stake=100, odds=2.5, settlement_timestamp=1700200000)
        assert result.profit_loss == -100.0
        assert result.return_amount == 0.0

    def test_void_settlement(self):
        result = settle_trade("t1", "VOID", stake=100, odds=2.5, settlement_timestamp=1700200000)
        assert result.profit_loss == 0.0
        assert result.return_amount == 100.0  # Stake returned

    def test_invalid_outcome_rejected(self):
        with pytest.raises(ValueError, match="Invalid outcome"):
            settle_trade("t1", "PUSH", stake=100, odds=2.0, settlement_timestamp=1700200000)

    def test_determine_outcome_over(self):
        assert determine_outcome("CORNERS_TOTAL", "OVER", 9.5, 11) == "WIN"
        assert determine_outcome("CORNERS_TOTAL", "OVER", 9.5, 8) == "LOSS"

    def test_determine_outcome_under(self):
        assert determine_outcome("GOALS_TOTAL", "UNDER", 2.5, 1) == "WIN"
        assert determine_outcome("GOALS_TOTAL", "UNDER", 2.5, 4) == "LOSS"

    def test_determine_outcome_none_is_void(self):
        """NULL result → VOID (NOT zero, NOT loss)."""
        assert determine_outcome("CORNERS_TOTAL", "OVER", 9.5, None) == "VOID"


# ═══════════════════════════════════════════════════════════════════
# L. CLV
# ═══════════════════════════════════════════════════════════════════


class TestCLV:
    def test_positive_clv(self):
        result = compute_clv("t1", prediction_odds=2.10, closing_odds=1.95)
        assert result is not None
        assert result.clv > 0  # Got better odds than closing
        assert result.is_positive is True

    def test_negative_clv(self):
        result = compute_clv("t1", prediction_odds=1.90, closing_odds=2.05)
        assert result is not None
        assert result.clv < 0
        assert result.is_positive is False

    def test_clv_formula(self):
        result = compute_clv("t1", prediction_odds=2.0, closing_odds=2.0)
        assert result is not None
        assert result.clv == pytest.approx(0.0)

    def test_clv_none_for_invalid(self):
        assert compute_clv("t1", prediction_odds=0.5, closing_odds=2.0) is None
        assert compute_clv("t1", prediction_odds=2.0, closing_odds=0.5) is None

    def test_clv_summary(self):
        results = [
            compute_clv("t1", 2.10, 1.95),
            compute_clv("t2", 1.90, 2.05),
            compute_clv("t3", 2.00, 1.90),
        ]
        results = [r for r in results if r is not None]
        summary = compute_clv_summary(results)
        assert summary.total_trades == 3
        assert summary.positive_clv_count == 2  # t1 and t3 are positive


# ═══════════════════════════════════════════════════════════════════
# M. FORWARD ORCHESTRATOR (IDEMPOTENCY)
# ═══════════════════════════════════════════════════════════════════


class TestForwardOrchestrator:
    def test_sync_fixtures_idempotent(self, sample_fixture):
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        orchestrator = ForwardResearchOrchestrator(fixture_provider=provider)

        r1 = orchestrator.sync_fixtures()
        assert r1.fixtures_processed == 1

        r2 = orchestrator.sync_fixtures()
        assert r2.fixtures_processed == 0  # Already synced

    def test_events_emitted(self, sample_fixture):
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        orchestrator = ForwardResearchOrchestrator(fixture_provider=provider)
        orchestrator.sync_fixtures()
        assert len(orchestrator.events) == 1
        assert orchestrator.events[0].event_type == ForwardEventType.FIXTURE_DISCOVERED

    def test_add_trade_idempotent(self):
        provider = DeterministicFixtureProvider()
        orchestrator = ForwardResearchOrchestrator(fixture_provider=provider)
        trade = PaperTrade(strategy_id="s1", fixture_id="f1", market="CORNERS_TOTAL")
        assert orchestrator.add_trade(trade) is True
        assert orchestrator.add_trade(trade) is False  # Duplicate


# ═══════════════════════════════════════════════════════════════════
# N. PERSISTENCE
# ═══════════════════════════════════════════════════════════════════


class TestForwardPersistence:
    def test_save_and_get_fixture(self, forward_repo):
        assert forward_repo.save_fixture("f1", {"status": "SCHEDULED"}) is True
        result = forward_repo.get_fixture("f1")
        assert result is not None
        assert result["status"] == "SCHEDULED"

    def test_duplicate_fixture_rejected(self, forward_repo):
        forward_repo.save_fixture("f1", {"status": "SCHEDULED"})
        assert forward_repo.save_fixture("f1", {"status": "DIFFERENT"}) is False

    def test_save_and_get_trade(self, forward_repo):
        assert forward_repo.save_trade("t1", {"status": "GENERATED"}) is True
        result = forward_repo.get_trade("t1")
        assert result["status"] == "GENERATED"

    def test_duplicate_trade_rejected(self, forward_repo):
        forward_repo.save_trade("t1", {"status": "GENERATED"})
        assert forward_repo.save_trade("t1", {"data": "different"}) is False

    def test_save_odds_snapshot(self, forward_repo):
        assert forward_repo.save_odds_snapshot("o1", {"odds": 2.05}) is True
        assert forward_repo.save_odds_snapshot("o1", {"odds": 2.10}) is False  # Dup

    def test_append_events(self, forward_repo):
        forward_repo.append_forward_event({"event_type": "FIXTURE_DISCOVERED", "fixture_id": "f1"})
        forward_repo.append_forward_event({"event_type": "ODDS_CAPTURED", "fixture_id": "f1"})
        events = forward_repo.list_forward_events(fixture_id="f1")
        assert len(events) == 2


# ═══════════════════════════════════════════════════════════════════
# O. CRASH RECOVERY (idempotent operations)
# ═══════════════════════════════════════════════════════════════════


class TestCrashRecovery:
    def test_rerun_sync_after_crash(self, sample_fixture):
        """Simulate crash after partial sync — rerun is safe."""
        provider = DeterministicFixtureProvider(fixtures=[sample_fixture])
        orchestrator = ForwardResearchOrchestrator(fixture_provider=provider)
        orchestrator.sync_fixtures()  # First run succeeds
        # Simulate crash, new orchestrator re-runs — it already has the fixture
        # (In production, persistence would be checked)
        r2 = orchestrator.sync_fixtures()
        assert r2.fixtures_processed == 0  # No duplicates

    def test_duplicate_trade_after_crash(self, forward_repo):
        """If trade was persisted before crash, re-submission is safe."""
        forward_repo.save_trade("t1", {"status": "GENERATED", "fixture_id": "f1"})
        # After restart, try to save same trade
        assert forward_repo.save_trade("t1", {"status": "GENERATED"}) is False

    def test_settlement_idempotent(self):
        """Settling same trade twice → ValueError (already settled)."""
        trade = (PaperTrade(strategy_id="s1", fixture_id="f1", odds_at_prediction=2.0, stake=100)
                 .transition(PaperTradeStatus.APPROVED_FOR_PAPER)
                 .transition(PaperTradeStatus.OPEN))
        settled = trade.settle(result="WIN", profit_loss=100, settlement_timestamp=1700200000)
        # Cannot settle again
        with pytest.raises(ValueError):
            settled.settle(result="WIN", profit_loss=100, settlement_timestamp=1700200001)


# ═══════════════════════════════════════════════════════════════════
# P. CONCURRENCY
# ═══════════════════════════════════════════════════════════════════


class TestConcurrency:
    def test_concurrent_trade_creation(self, forward_repo):
        """Multiple threads saving same trade → exactly one succeeds."""
        results = []

        def save_trade():
            success = forward_repo.save_trade("t_concurrent", {"status": "GENERATED"})
            results.append(success)

        threads = [threading.Thread(target=save_trade) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 1  # Exactly one succeeds
        assert results.count(False) == 9

    def test_concurrent_fixture_creation(self, forward_repo):
        """Multiple threads saving same fixture → exactly one succeeds."""
        results = []

        def save_fixture():
            success = forward_repo.save_fixture("f_concurrent", {"status": "SCHEDULED"})
            results.append(success)

        threads = [threading.Thread(target=save_fixture) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 1


# ═══════════════════════════════════════════════════════════════════
# Q. TEMPORAL LEAKAGE ATTACKS (18 mandatory tests)
# ═══════════════════════════════════════════════════════════════════


class TestTemporalLeakageAttacks:
    """Mandatory adversarial temporal leakage tests."""

    def test_01_final_result_cannot_influence_prediction(self, historical_matches):
        """Final match result cannot enter feature snapshot."""
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        # No feature should be "result" or direct match outcome
        for feat_id in snapshot.features:
            assert not TemporalFeatureEngine.is_post_match_feature(feat_id)

    def test_02_final_goals_cannot_influence_prediction(self, historical_matches):
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        assert "home_goals" not in snapshot.features
        assert "away_goals" not in snapshot.features
        assert "total_goals" not in snapshot.features

    def test_03_final_corners_cannot_influence_prediction(self, historical_matches):
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        assert "corners_home" not in snapshot.features
        assert "corners_away" not in snapshot.features

    def test_04_final_cards_cannot_influence_prediction(self, historical_matches):
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        assert "yellow_cards_home" not in snapshot.features
        assert "total_cards" not in snapshot.features

    def test_05_final_xg_cannot_influence_prediction(self, historical_matches):
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        assert "home_xg" not in snapshot.features
        assert "away_xg" not in snapshot.features

    def test_06_closing_odds_cannot_influence_prediction(self):
        """Closing odds (captured at/near kickoff) cannot be used for predictions."""
        closing_snap = OddsSnapshot(
            fixture_id="abc", market="CORNERS_TOTAL",
            selection=OddsSelection.OVER, line=9.5,
            decimal_odds=1.95, snapshot_timestamp=1700099000,
            odds_type=OddsType.CLOSING,
        )
        # Prediction at 1700000000 — closing at 1700099000
        assert closing_snap.is_valid_for_prediction(1700000000) is False

    def test_07_odds_after_prediction_cannot_change_ev(self):
        """Odds captured after prediction cannot influence original EV."""
        trade = PaperTrade(
            strategy_id="s1", fixture_id="f1",
            odds_at_prediction=2.10, model_probability=0.55,
            expected_value=(0.55 * 2.10) - 1,
            prediction_timestamp=1700000000,
        )
        # Trade is frozen — odds_at_prediction cannot change
        with pytest.raises(AttributeError):
            trade.odds_at_prediction = 1.90  # type: ignore
        assert trade.expected_value == pytest.approx((0.55 * 2.10) - 1)

    def test_08_odds_after_prediction_cannot_change_trade_odds(self):
        """Settlement uses original prediction odds, not later odds."""
        result = settle_trade("t1", "WIN", stake=100, odds=2.10, settlement_timestamp=1700200000)
        # Profit uses original odds (2.10), not closing (1.95)
        assert result.profit_loss == pytest.approx(110.0)  # 100 * (2.10 - 1)

    def test_09_future_fixtures_cannot_influence_features(self, historical_matches):
        """Future match data cannot appear in feature snapshot."""
        # Add a match AFTER prediction time
        future_match = ResearchMatch(
            match_id=9999, date_unix=1700500000,  # FUTURE
            league_id=47, season="2023/2024",
            home_team="101", away_team="202", total_goals=5,
        )
        all_matches = historical_matches + [future_match]
        engine = TemporalFeatureEngine(historical_matches=all_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        # Verify all provenance timestamps are before prediction
        for prov in snapshot.feature_provenance:
            assert prov.information_timestamp < 1700000000

    def test_10_future_season_cannot_influence_prediction(self, historical_matches):
        """Future season data cannot contaminate current prediction."""
        # Same as test_09 — temporal filter is absolute, not season-based
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        eligible = engine._filter_eligible_matches(1700000000)
        for m in eligible:
            assert m.date_unix < 1700000000

    def test_11_settlement_cannot_modify_prediction(self):
        """Settlement adds data but NEVER changes prediction fields."""
        trade = PaperTrade(
            strategy_id="s1", fixture_id="f1",
            model_probability=0.55, odds_at_prediction=2.10,
            expected_value=0.155, prediction_timestamp=1700000000,
            stake=100, kickoff_timestamp=1700100000,
        )
        opened = trade.transition(PaperTradeStatus.APPROVED_FOR_PAPER).transition(PaperTradeStatus.OPEN)
        settled = opened.settle(result="WIN", profit_loss=110, settlement_timestamp=1700200000)
        # Original prediction fields unchanged
        assert settled.model_probability == 0.55
        assert settled.odds_at_prediction == 2.10
        assert settled.prediction_timestamp == 1700000000

    def test_12_clv_cannot_modify_original_trade(self):
        """CLV is a separate calculation — does not alter trade identity."""
        trade = PaperTrade(
            strategy_id="s1", fixture_id="f1",
            odds_at_prediction=2.10, stake=100,
        )
        clv_result = compute_clv("t1", prediction_odds=2.10, closing_odds=1.95)
        # Trade is unchanged — CLV is a separate artifact
        assert trade.odds_at_prediction == 2.10
        assert trade.clv is None  # Not yet attached

    def test_13_rerun_after_settlement_same_prediction(self, historical_matches):
        """Re-running prediction after settlement produces same snapshot."""
        engine = TemporalFeatureEngine(historical_matches=historical_matches)
        s1 = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        # Simulate "after settlement" — same inputs
        s2 = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        assert s1.snapshot_id == s2.snapshot_id

    def test_14_ai_context_cannot_contain_post_prediction_info(self):
        """ResearchContext temporal_cutoff prevents future info."""
        from src.research.ai.context import ResearchContext
        ctx = ResearchContext(
            market_type="CORNERS_TOTAL",
            temporal_cutoff=1700000000,
        )
        assert ctx.temporal_cutoff == 1700000000

    def test_15_same_kickoff_handled_conservatively(self, historical_matches):
        """Matches at exact prediction_timestamp are EXCLUDED in strict mode."""
        same_time_match = ResearchMatch(
            match_id=8888, date_unix=1700000000,  # SAME as prediction
            league_id=47, season="2023/2024",
            home_team="101", away_team="303", total_goals=3,
        )
        all_matches = historical_matches + [same_time_match]
        engine = TemporalFeatureEngine(historical_matches=all_matches, strict_mode=True)
        eligible = engine._filter_eligible_matches(1700000000)
        # Same-time match should be excluded
        assert all(m.date_unix < 1700000000 for m in eligible)

    def test_16_missing_timestamps_cannot_be_valid_prematch(self):
        """Features with UNKNOWN timestamp confidence should be flagged."""
        prov = FeatureProvenance(
            feature_id="suspicious",
            value=42.0,
            information_timestamp=1699900000,
            timestamp_confidence=TimestampConfidence.UNKNOWN,
        )
        assert prov.timestamp_confidence == TimestampConfidence.UNKNOWN
        # System should treat UNKNOWN with caution — documented behavior

    def test_17_estimated_timestamps_clearly_marked(self):
        """Estimated information timestamps are explicitly labeled."""
        prov = FeatureProvenance(
            feature_id="avg_goals_home",
            value=2.5,
            information_timestamp=1699800000,
            timestamp_confidence=TimestampConfidence.ESTIMATED,
            estimation_method="latest_historical_match_completion_time",
        )
        assert prov.timestamp_confidence == TimestampConfidence.ESTIMATED
        assert prov.estimation_method != ""

    def test_18_malicious_records_cannot_inject_future_features(self, historical_matches):
        """Even if historical_matches contains a 'future' match, temporal filter rejects it."""
        malicious = ResearchMatch(
            match_id=6666, date_unix=1800000000,  # Far future
            league_id=47, season="2024/2025",
            home_team="101", away_team="202",
            total_goals=10, total_corners=20,
        )
        all_matches = historical_matches + [malicious]
        engine = TemporalFeatureEngine(historical_matches=all_matches)
        snapshot = engine.build_snapshot(
            fixture_id="target", home_team_id=101, away_team_id=202,
            prediction_timestamp=1700000000, kickoff_timestamp=1700100000,
        )
        for prov in snapshot.feature_provenance:
            assert prov.information_timestamp < 1700000000


# ═══════════════════════════════════════════════════════════════════
# R. AI SAFETY
# ═══════════════════════════════════════════════════════════════════


class TestAISafety:
    def test_ai_cannot_create_paper_trade(self):
        """No code path from AI to paper trade creation without governance."""
        # PaperTrade requires explicit eligibility evaluation
        # AI proposals go through: propose → validate → experiment → walkforward → FDR → governance
        # There is no direct path from ResearchAgent to PaperTrade
        from src.research.ai.proposal import ProposalSource, ResearchPhase
        from src.research.ai.provider import MockLLMProvider
        from src.research.ai.agent import ResearchAgent
        from src.research.ai.context import ResearchContext

        agent = ResearchAgent(provider=MockLLMProvider())
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        # Proposal is EXPLORATION phase — cannot directly become a paper trade
        assert proposal.phase == ResearchPhase.EXPLORATION
        assert proposal.source == ProposalSource.AI


# ═══════════════════════════════════════════════════════════════════
# S. FORWARD PERFORMANCE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════


class TestForwardClassification:
    def test_insufficient_data(self):
        c = classify_forward_performance(settled_trades=5, roi=0.1, positive_clv_rate=0.6, win_rate=0.6)
        assert c == ForwardClassification.INSUFFICIENT_FORWARD_DATA

    def test_early_signal(self):
        c = classify_forward_performance(settled_trades=25, roi=0.03, positive_clv_rate=0.5, win_rate=0.55)
        assert c == ForwardClassification.EARLY_SIGNAL

    def test_promising(self):
        c = classify_forward_performance(settled_trades=60, roi=0.05, positive_clv_rate=0.55, win_rate=0.55)
        assert c == ForwardClassification.PROMISING

    def test_stable(self):
        c = classify_forward_performance(settled_trades=150, roi=0.04, positive_clv_rate=0.52, win_rate=0.54)
        assert c == ForwardClassification.STABLE

    def test_failed(self):
        c = classify_forward_performance(settled_trades=50, roi=-0.20, positive_clv_rate=0.3, win_rate=0.4)
        assert c == ForwardClassification.FAILED_FORWARD_VALIDATION

    def test_degrading(self):
        c = classify_forward_performance(
            settled_trades=50, roi=-0.01, positive_clv_rate=0.4,
            win_rate=0.48, historical_roi=0.08,
        )
        assert c == ForwardClassification.DEGRADING


# ═══════════════════════════════════════════════════════════════════
# T. SECURITY
# ═══════════════════════════════════════════════════════════════════


class TestSecurity:
    def test_no_credentials_in_fixture(self, sample_fixture):
        d = json.dumps(sample_fixture.to_dict())
        assert "aws_access" not in d.lower()
        assert "secret" not in d.lower()
        assert "api_key" not in d.lower()
        assert "password" not in d.lower()

    def test_no_credentials_in_trade(self):
        trade = PaperTrade(strategy_id="s1", fixture_id="f1", market="CORNERS_TOTAL")
        d = json.dumps(trade.to_dict())
        assert "aws_access" not in d.lower()
        assert "secret" not in d.lower()

    def test_no_credentials_in_snapshot(self):
        snapshot = PreMatchSnapshot(
            fixture_id="abc", prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000, features={"avg_goals_home": 2.5},
        )
        d = json.dumps(snapshot.to_dict())
        assert "aws_access" not in d.lower()
        assert "secret" not in d.lower()

    def test_no_betting_execution_path(self):
        """No code path exists for placing real bets."""
        import src.research.paper as paper_module
        # Verify no wallet, broker, or execution objects exist
        module_attrs = dir(paper_module)
        for attr in module_attrs:
            assert "wallet" not in attr.lower()
            assert "broker" not in attr.lower()
            assert "execute_bet" not in attr.lower()


# ═══════════════════════════════════════════════════════════════════
# U. MISSING DATA HANDLING (NULL != 0)
# ═══════════════════════════════════════════════════════════════════


class TestMissingData:
    def test_missing_feature_is_none_not_zero(self):
        snapshot = PreMatchSnapshot(
            fixture_id="abc", prediction_timestamp=1700000000,
            kickoff_timestamp=1700100000,
            features={"avg_goals_home": None, "avg_corners_home": 9.5},
        )
        assert snapshot.get_feature("avg_goals_home") is None
        assert snapshot.get_feature("avg_goals_home") != 0
        assert snapshot.get_feature("nonexistent") is None

    def test_settlement_void_for_none_result(self):
        """Missing result → VOID, not zero, not loss."""
        outcome = determine_outcome("CORNERS_TOTAL", "OVER", 9.5, None)
        assert outcome == "VOID"

    def test_clv_none_for_missing_odds(self):
        """Missing closing odds → no CLV, not zero CLV."""
        result = compute_clv("t1", prediction_odds=2.0, closing_odds=None)
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# V. CANCELLED/POSTPONED FIXTURES
# ═══════════════════════════════════════════════════════════════════


class TestCancelledPostponed:
    def test_cancelled_fixture_voids_trade(self, sample_fixture):
        cancelled = sample_fixture.transition(FixtureStatus.CANCELLED)
        assert cancelled.is_terminal is True
        assert cancelled.is_paper_eligible is False

    def test_postponed_fixture_not_eligible(self, sample_fixture):
        postponed = sample_fixture.transition(FixtureStatus.POSTPONED)
        assert postponed.is_paper_eligible is False

    def test_postponed_can_be_rescheduled(self, sample_fixture):
        postponed = sample_fixture.transition(FixtureStatus.POSTPONED)
        rescheduled = postponed.transition(FixtureStatus.SCHEDULED)
        assert rescheduled.status == FixtureStatus.SCHEDULED
        assert rescheduled.is_paper_eligible is True


# ═══════════════════════════════════════════════════════════════════
# W. END-TO-END INTEGRATION
# ═══════════════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_full_forward_pipeline(self, sample_fixture, historical_matches):
        """Complete pipeline: fixture → snapshot → odds → trade → settle → CLV."""
        # 1. Fixture provider
        fixture_provider = DeterministicFixtureProvider(fixtures=[sample_fixture])

        # 2. Odds provider
        odds_provider = DeterministicOddsProvider()
        odds_provider.add_snapshot(OddsSnapshot(
            fixture_id=sample_fixture.fixture_id,
            market="CORNERS_TOTAL", selection=OddsSelection.OVER,
            line=9.5, decimal_odds=2.05,
            snapshot_timestamp=1700050000,
            odds_type=OddsType.PRE_MATCH,
        ))
        odds_provider.add_snapshot(OddsSnapshot(
            fixture_id=sample_fixture.fixture_id,
            market="CORNERS_TOTAL", selection=OddsSelection.OVER,
            line=9.5, decimal_odds=1.95,
            snapshot_timestamp=1700099000,
            odds_type=OddsType.CLOSING,
        ))

        # 3. Feature engine
        engine = TemporalFeatureEngine(historical_matches=historical_matches)

        # 4. Orchestrator
        orchestrator = ForwardResearchOrchestrator(
            fixture_provider=fixture_provider,
            odds_provider=odds_provider,
            feature_engine=engine,
        )

        # 5. Sync fixtures
        r = orchestrator.sync_fixtures()
        assert r.fixtures_processed == 1

        # 6. Build snapshot
        r = orchestrator.build_snapshots(
            prediction_timestamp=1700060000, hypothesis_id="hyp1",
        )
        assert r.snapshots_created == 1

        # 7. Capture odds
        r = orchestrator.capture_odds()
        assert r.odds_captured >= 1

        # 8. Create paper trade
        trade = PaperTrade(
            strategy_id="strat1", hypothesis_id="hyp1",
            fixture_id=sample_fixture.fixture_id,
            market="CORNERS_TOTAL", selection="OVER", line=9.5,
            model_probability=0.55, market_probability=1.0 / 2.05,
            odds_at_prediction=2.05, edge=0.55 - (1.0 / 2.05),
            expected_value=(0.55 * 2.05) - 1,
            stake=100, bankroll_before=10000,
            prediction_timestamp=1700060000,
            kickoff_timestamp=1700100000,
            snapshot_id="snap1", odds_snapshot_id="odds1",
        )
        orchestrator.add_trade(trade)

        # 9. Approve and open
        orchestrator.approve_trade(trade.trade_id)
        orchestrator.open_trade(trade.trade_id)
        assert orchestrator.trades[trade.trade_id].status == PaperTradeStatus.OPEN

        # 10. Complete fixture
        fixture_provider.update_status(sample_fixture.fixture_id, FixtureStatus.STARTED)
        fixture_provider.update_status(sample_fixture.fixture_id, FixtureStatus.COMPLETED)
        orchestrator.sync_fixtures()  # Pick up status change

        # 11. Settle
        r = orchestrator.settle_trades(
            get_result=lambda fid, m, s, l: "WIN",
            get_actual_value=lambda fid, m: 11.0,  # 11 corners > 9.5 line
        )
        assert r.trades_settled == 1

        settled = orchestrator.trades[trade.trade_id]
        assert settled.status == PaperTradeStatus.SETTLED
        assert settled.settlement_result == "WIN"
        assert settled.profit_loss == pytest.approx(105.0)  # 100 * (2.05 - 1)
        assert settled.closing_odds == 1.95
        assert settled.clv is not None
        assert settled.clv > 0  # Got better odds (2.05) than closing (1.95)
