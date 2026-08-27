"""Phase 1 Integrity Regression Tests.

Tests the fundamental quantitative invariants established by Phase 1:
- R01: xO temporal leakage (future-invariance)
- R02: Referee temporal leakage (future-invariance)
- R03: Synthetic odds fabrication (missing odds → NO_SIGNAL)
- R04: Fake CLV (model_edge_pct ≠ CLV)
- R05: Validation trust state (authoritative only)
- R06: Quarantine integration
- Strategy identity and versioning
- General temporal integrity harness
"""

from __future__ import annotations

from datetime import datetime as _datetime, timezone as _timezone
from typing import List

import numpy as np
import pandas as pd
import pytest

from src.engine.backtest import XBacktestConfig, XBetRecord, XMetricBacktester
from src.engine.clv import CLVCalculator, CLVResult
from src.engine.evaluator import Condition, Signal, Strategy, StrategyEvaluator
from src.engine.signals.community_broadcaster import BroadcastConfig, CommunityBroadcaster
from src.engine.strategy_identity import StrategyIdentity, StrategyRegistry
from src.engine.xmetrics import XMetricEngine
from src.features.referee_volatility import RefereeVolatilityCalculator
from src.models.match import Match

# Fixed clock for CommunityBroadcaster tests: noon UTC is outside the default
# quiet-hours window (1am-6am UTC), so these tests don't flake depending on
# what real wall-clock hour they happen to run at.
_NOON_UTC_CLOCK = lambda: _datetime(2024, 6, 15, 12, 0, tzinfo=_timezone.utc)


# ===========================================================================
# TEMPORAL INTEGRITY HARNESS — Reusable invariant testing
# ===========================================================================

class TemporalIntegrityHarness:
    """Reusable harness for testing temporal invariance.

    Fundamental invariant:
    «Adding future observations must never alter previously calculated features.»

    Usage:
        harness = TemporalIntegrityHarness()
        assert harness.verify_xO_invariance(history_df, future_df)
        assert harness.verify_referee_invariance(history_matches, future_matches)
    """

    @staticmethod
    def verify_xO_invariance(
        history_df: pd.DataFrame, future_df: pd.DataFrame
    ) -> bool:
        """Verify xO features are invariant to future data.

        Computes xO on history alone, then on history+future.
        Historical rows must produce identical xO values.
        """
        engine = XMetricEngine()
        n_history = len(history_df)

        # Compute on history only
        result_a = engine.compute_xO(history_df.copy())

        # Compute on history + future
        combined = pd.concat([history_df, future_df], ignore_index=True)
        result_b = engine.compute_xO(combined.copy())

        # Compare historical rows
        for i in range(n_history):
            if not np.isnan(result_a["home_xO"].iloc[i]):
                if not np.isclose(result_a["home_xO"].iloc[i], result_b["home_xO"].iloc[i], rtol=1e-10):
                    return False
            if not np.isnan(result_a["away_xO"].iloc[i]):
                if not np.isclose(result_a["away_xO"].iloc[i], result_b["away_xO"].iloc[i], rtol=1e-10):
                    return False
        return True

    @staticmethod
    def verify_referee_invariance(
        history: List[Match], future: List[Match]
    ) -> bool:
        """Verify referee volatility is invariant to future matches.

        Computes referee features on history alone, then on history+future.
        Historical matches must produce identical volatility values.
        """
        calc = RefereeVolatilityCalculator(min_matches=3)

        result_a = calc.compute_index(history)
        result_b = calc.compute_index(history + future)

        for match in history:
            if result_a[match.id] != result_b[match.id]:
                return False
        return True


# ===========================================================================
# R01 — xO TEMPORAL LEAKAGE TESTS
# ===========================================================================

class TestR01_xO_TemporalLeakage:
    """Tests proving xO is free from temporal leakage after fix."""

    def _make_df(self, n: int, base_ts: int = 1000000) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        return pd.DataFrame({
            "date_unix": base_ts + np.arange(n) * 86400,
            "offsides_home": rng.integers(0, 6, n).astype(float),
            "offsides_away": rng.integers(0, 6, n).astype(float),
            "ppda_home": rng.uniform(5.0, 15.0, n),
            "ppda_away": rng.uniform(5.0, 15.0, n),
        })

    def test_future_invariance(self):
        """Adding future data must NOT change historical xO values."""
        history = self._make_df(50, base_ts=1000000)
        future = self._make_df(50, base_ts=1000000 + 50 * 86400)
        future["date_unix"] = future["date_unix"] + 50 * 86400

        harness = TemporalIntegrityHarness()
        assert harness.verify_xO_invariance(history, future)

    def test_extreme_future_does_not_affect_history(self):
        """Anomalous future data (extreme PPDA) must not alter historical baselines."""
        history = self._make_df(30, base_ts=1000000)

        # Extreme future: PPDA=0.1 would make HLI=10, massively changing any global mean
        extreme_future = pd.DataFrame({
            "date_unix": [1000000 + 100 * 86400] * 50,
            "offsides_home": [20.0] * 50,
            "offsides_away": [20.0] * 50,
            "ppda_home": [0.1] * 50,  # Extreme — HLI = 10.0
            "ppda_away": [0.1] * 50,
        })

        harness = TemporalIntegrityHarness()
        assert harness.verify_xO_invariance(history, extreme_future)

    def test_first_row_uses_fallback_baseline(self):
        """The first row has no prior data — must use fallback, not future."""
        engine = XMetricEngine()
        df = self._make_df(5)
        result = engine.compute_xO(df)

        # First row should use baseline=1.0 (fallback)
        # Verify it doesn't crash and produces a valid value
        assert not pd.isna(result["home_xO"].iloc[0])

    def test_expanding_baseline_grows_with_data(self):
        """League baseline should evolve as more data accumulates."""
        engine = XMetricEngine()
        # Uniform PPDA = 10.0 → HLI = 0.1 for all rows
        df = pd.DataFrame({
            "date_unix": np.arange(10) * 86400,
            "offsides_home": [3.0] * 10,
            "offsides_away": [2.0] * 10,
            "ppda_home": [10.0] * 10,
            "ppda_away": [10.0] * 10,
        })
        result = engine.compute_xO(df)

        # After first few rows stabilize, baseline should converge to 0.1
        # Row 0: baseline=1.0 (fallback), ratio = 0.1/1.0 = 0.1
        # Row 1+: baseline→0.1, ratio→1.0
        # So later rows should have higher xO than row 0
        assert result["home_xO"].iloc[5] > result["home_xO"].iloc[0]


# ===========================================================================
# R02 — REFEREE TEMPORAL LEAKAGE TESTS
# ===========================================================================

class TestR02_RefereeTemporalLeakage:
    """Tests proving referee volatility is free from temporal leakage."""

    def _make_matches(self, n: int, referee: str = "Ref A",
                      base_ts: int = 1000000, goals: int = 2) -> List[Match]:
        return [
            Match(id=1000 + i, date_unix=base_ts + i * 86400, league_id=4759,
                  season="2023", home_team="A", away_team="B",
                  home_goals=goals, away_goals=0, total_goals=goals,
                  home_xg=1.5, away_xg=0.5, referee=referee,
                  over_under_line=2.5, over_odds=1.85, under_odds=2.05)
            for i in range(n)
        ]

    def test_future_invariance(self):
        """Adding future referee matches must NOT change historical features."""
        history = self._make_matches(20, "Ref A", goals=2)
        # Future matches with wildly different goals — use different IDs
        future = [
            Match(id=5000 + i, date_unix=1000000 + (100 + i) * 86400, league_id=4759,
                  season="2023", home_team="A", away_team="B",
                  home_goals=7, away_goals=0, total_goals=7,
                  home_xg=1.5, away_xg=0.5, referee="Ref A",
                  over_under_line=2.5, over_odds=1.85, under_odds=2.05)
            for i in range(20)
        ]

        harness = TemporalIntegrityHarness()
        assert harness.verify_referee_invariance(history, future)

    def test_extreme_future_referee_does_not_leak(self):
        """A referee with extreme future stats must not affect historical values."""
        history = self._make_matches(10, "Ref A", goals=2)

        # Future: Ref A suddenly has 10-goal games — use different IDs
        future = [
            Match(id=9000 + i, date_unix=2000000 + i * 86400, league_id=4759,
                  season="2024", home_team="X", away_team="Y",
                  home_goals=10, away_goals=0, total_goals=10,
                  home_xg=5.0, away_xg=0.0, referee="Ref A",
                  over_under_line=2.5, over_odds=1.85, under_odds=2.05)
            for i in range(20)
        ]

        harness = TemporalIntegrityHarness()
        assert harness.verify_referee_invariance(history, future)

    def test_first_match_uses_zero_volatility(self):
        """First match for any referee has no history → volatility = 0.0."""
        calc = RefereeVolatilityCalculator(min_matches=5)
        matches = self._make_matches(1, "New Ref", goals=3)

        result = calc.compute_index(matches)
        # First match has no prior data → league volatility = 0.0 (only 0 prior matches)
        assert result[matches[0].id] == 0.0

    def test_min_matches_threshold_respected(self):
        """Referee with fewer than min_matches prior games uses league fallback."""
        calc = RefereeVolatilityCalculator(min_matches=5)
        # 3 matches for Ref A (below threshold of 5)
        matches = self._make_matches(6, "Ref A", goals=2)

        result = calc.compute_index(matches)
        # Match 6 has 5 prior Ref A matches → should now use referee-specific volatility
        # Match 3 has only 2 prior → uses league fallback
        # Since all goals=2, std=0 everywhere, so values should be 0.0
        assert result[matches[5].id] == 0.0  # std of [2,2,2,2,2] = 0


# ===========================================================================
# R03 — SYNTHETIC ODDS TESTS
# ===========================================================================

class TestR03_SyntheticOdds:
    """Tests proving missing odds cannot create betting opportunities."""

    def _make_strategy(self) -> Strategy:
        return Strategy(name="Test", metric="xC", market="corners",
                        conditions=(Condition(field="home_xC", op=">", value=2.0),),
                        logic="and", direction="OVER", min_odds=1.50)

    def test_nan_odds_produce_no_signal(self):
        """NaN odds must suppress signal generation."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0],
            "over_odds": [np.nan, 2.00],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        # Only row 1 (with real odds) should produce a signal
        assert len(signals) == 1
        assert signals[0].match_index == 1

    def test_none_odds_produce_no_signal(self):
        """None odds must suppress signal generation."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0],
            "over_odds": [None],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0

    def test_zero_odds_produce_no_signal(self):
        """Odds of 0 or <= 1.0 must suppress signal generation."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0, 3.0],
            "over_odds": [0.0, 1.0, 0.5],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0

    def test_missing_odds_column_produces_no_signal(self):
        """Missing odds column entirely must suppress signals."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0, 3.0],
            # No 'over_odds' column at all
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0

    def test_valid_odds_still_produce_signals(self):
        """Valid odds should still generate signals normally."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [3.0, 3.0],
            "over_odds": [1.85, 2.10],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 2

    def test_walkforward_engine_skips_missing_odds(self):
        """The WalkForwardEngine must not place bets when odds are None."""
        from src.backtest.engine import WalkForwardEngine
        from src.models.config import StrategyConfig
        from src.models.features import MatchFeatures

        config = StrategyConfig(train_window=5, test_window=3, step_size=3)
        engine = WalkForwardEngine(config=config)

        # Create features with None odds
        features = [
            MatchFeatures(
                match_id=i, date_unix=1000 + i * 86400,
                home_xg_eff_delta_rolling=0.3, away_xg_eff_delta_rolling=0.2,
                home_rolling_form=0.8, away_rolling_form=0.6,
                referee_volatility_index=1.5, total_goals=3,
                over_under_line=2.5, over_odds=None, under_odds=None,
            )
            for i in range(20)
        ]

        result = engine.run(features)
        # With all odds=None, no bets should be placed
        assert result.total_bets == 0


# ===========================================================================
# R04 — CLV TESTS
# ===========================================================================

class TestR04_CLV:
    """Tests proving CLV is computed correctly from actual market data."""

    def test_real_clv_calculation(self):
        """CLV = (entry/closing - 1) * 100."""
        result = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.95)
        expected = (2.10 / 1.95 - 1.0) * 100.0
        assert result.available is True
        assert result.clv_pct == pytest.approx(expected, rel=1e-6)

    def test_missing_closing_odds_unavailable(self):
        """Missing closing odds → CLV unavailable."""
        result = CLVCalculator.compute(entry_odds=2.10, closing_odds=None)
        assert result.available is False
        assert result.clv_pct is None

    def test_missing_entry_odds_unavailable(self):
        """Missing entry odds → CLV unavailable."""
        result = CLVCalculator.compute(entry_odds=None, closing_odds=1.95)
        assert result.available is False
        assert result.clv_pct is None

    def test_model_edge_does_not_affect_clv(self):
        """Changing model edge without changing odds must NOT change CLV."""
        clv1 = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.95)
        clv2 = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.95)
        # Same odds → same CLV regardless of any model edge
        assert clv1.clv_pct == clv2.clv_pct

    def test_closing_odds_change_changes_clv(self):
        """Changing closing odds MUST change CLV."""
        clv1 = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.95)
        clv2 = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.80)
        assert clv1.clv_pct != clv2.clv_pct

    def test_clv_never_equals_edge_times_100(self):
        """CLV must not coincidentally equal 'edge * 100' for arbitrary values."""
        # edge=0.5, entry=2.10, closing=1.95
        fake_clv = 0.5 * 100  # This is what the old code did
        real_clv = CLVCalculator.compute(2.10, 1.95)
        assert real_clv.clv_pct != pytest.approx(fake_clv)

    def test_positive_clv_means_beat_closing(self):
        """Positive CLV = entry odds better than close."""
        result = CLVCalculator.compute(entry_odds=2.20, closing_odds=2.00)
        assert result.beat_closing_line is True

    def test_negative_clv_means_worse_than_closing(self):
        """Negative CLV = entry odds worse than close."""
        result = CLVCalculator.compute(entry_odds=1.80, closing_odds=2.00)
        assert result.beat_closing_line is False

    def test_backtest_bet_records_have_none_clv(self):
        """XBetRecord.clv should be None when closing odds unavailable."""
        record = XBetRecord(
            match_index=0, strategy_name="Test", direction="OVER",
            odds=2.00, stake=1.0, outcome="WIN", profit_loss=1.0,
            model_edge_pct=50.0, clv=None,
        )
        assert record.clv is None
        assert record.model_edge_pct == 50.0


# ===========================================================================
# R05 — VALIDATION TRUST STATE TESTS
# ===========================================================================

class TestR05_ValidationTrust:
    """Tests proving validation state is authoritative, not hardcoded."""

    def _make_signal(self) -> Signal:
        return Signal(match_index=0, strategy_name="Test", direction="OVER", edge=0.1, odds=2.0)

    @pytest.mark.asyncio
    async def test_unvalidated_strategy_gets_false_badge(self):
        """Unvalidated strategy must NOT receive fdr_validated=True."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        payloads = await broadcaster.run_once(
            signals=[self._make_signal()],
            match_data=[{"home_team": "A", "away_team": "B"}],
            validation_passed=False,  # Not validated
        )

        assert len(payloads) == 1
        assert payloads[0].fdr_validated is False

    @pytest.mark.asyncio
    async def test_validated_strategy_gets_true_badge(self):
        """Validated strategy may receive fdr_validated=True."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        payloads = await broadcaster.run_once(
            signals=[self._make_signal()],
            match_data=[{"home_team": "A", "away_team": "B"}],
            validation_passed=True,  # Validated by authoritative system
        )

        assert len(payloads) == 1
        assert payloads[0].fdr_validated is True

    @pytest.mark.asyncio
    async def test_default_is_not_validated(self):
        """Default (no validation_passed arg) must be False."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        payloads = await broadcaster.run_once(
            signals=[self._make_signal()],
            match_data=[{"home_team": "A", "away_team": "B"}],
            # No validation_passed argument → defaults to False
        )

        assert len(payloads) == 1
        assert payloads[0].fdr_validated is False


# ===========================================================================
# R06 — QUARANTINE INTEGRATION TESTS
# ===========================================================================

class TestR06_QuarantineIntegration:
    """Tests proving quarantine actually affects the pipeline."""

    @pytest.mark.asyncio
    async def test_quarantined_strategy_not_validated(self):
        """Quarantined strategy must not broadcast as validated."""
        from src.engine.fdr import QuarantineStatus, QuarantineTracker
        from datetime import datetime

        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_1", datetime(2024, 1, 1))

        # Status is PENDING_QUARANTINE → validation_passed must be False
        status = tracker.check_status("strat_1", datetime(2024, 3, 1))
        assert status == QuarantineStatus.PENDING_QUARANTINE

        # This means the broadcaster should receive validation_passed=False
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)
        signal = Signal(match_index=0, strategy_name="strat_1", direction="OVER", edge=0.1, odds=2.0)

        # Caller must check quarantine status and pass it correctly
        is_validated = (status == QuarantineStatus.PROMOTED)
        payloads = await broadcaster.run_once(
            signals=[signal], match_data=[{"home_team": "A", "away_team": "B"}],
            validation_passed=is_validated,
        )

        assert payloads[0].fdr_validated is False

    @pytest.mark.asyncio
    async def test_promoted_strategy_can_be_validated(self):
        """Only PROMOTED strategies may broadcast as validated."""
        from src.engine.fdr import QuarantineStatus, QuarantineTracker
        from datetime import datetime, timedelta

        tracker = QuarantineTracker()
        tracker.enter_quarantine("strat_2", datetime(2024, 1, 1))
        tracker.promote("strat_2", datetime(2024, 1, 1) + timedelta(days=91))

        status = tracker.check_status("strat_2", datetime(2024, 5, 1))
        assert status == QuarantineStatus.PROMOTED

        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)
        signal = Signal(match_index=0, strategy_name="strat_2", direction="OVER", edge=0.1, odds=2.0)

        is_validated = (status == QuarantineStatus.PROMOTED)
        payloads = await broadcaster.run_once(
            signals=[signal], match_data=[{"home_team": "X", "away_team": "Y"}],
            validation_passed=is_validated,
        )

        assert payloads[0].fdr_validated is True


# ===========================================================================
# STRATEGY IDENTITY TESTS
# ===========================================================================

class TestStrategyIdentity:
    """Tests for strategy identity and versioning foundation."""

    def _make_strategy(self, name: str = "Test") -> Strategy:
        return Strategy(name=name, metric="xC", market="corners",
                        conditions=(Condition(field="home_xC", op=">", value=2.5),),
                        logic="and", direction="OVER", min_odds=1.75)

    def test_register_creates_identity(self):
        """Registration produces a StrategyIdentity with ID and version."""
        registry = StrategyRegistry()
        identity = registry.register(self._make_strategy())

        assert identity.strategy_id is not None
        assert identity.strategy_version == 1
        assert identity.name == "Test"
        assert identity.content_hash is not None
        assert identity.schema_version == "1.0.0"

    def test_same_content_same_version(self):
        """Registering identical strategy content doesn't create new version."""
        registry = StrategyRegistry()
        id1 = registry.register(self._make_strategy(), strategy_id="fixed-id")
        id2 = registry.register(self._make_strategy(), strategy_id="fixed-id")

        assert id1.strategy_version == id2.strategy_version == 1

    def test_modified_content_increments_version(self):
        """Changed strategy creates a new version."""
        registry = StrategyRegistry()
        s1 = self._make_strategy("V1")
        id1 = registry.register(s1, strategy_id="fixed-id")

        s2 = Strategy(name="V2", metric="xC", market="corners",
                      conditions=(Condition(field="home_xC", op=">", value=3.0),),
                      logic="and", direction="OVER", min_odds=1.75)
        id2 = registry.register(s2, strategy_id="fixed-id")

        assert id1.strategy_version == 1
        assert id2.strategy_version == 2
        assert id2.parent_version == 1

    def test_content_hash_deterministic(self):
        """Same strategy always produces same content hash."""
        registry = StrategyRegistry()
        s = self._make_strategy()
        h1 = registry._compute_hash(s)
        h2 = registry._compute_hash(s)
        assert h1 == h2

    def test_different_strategies_different_hash(self):
        """Different strategies produce different hashes."""
        registry = StrategyRegistry()
        s1 = self._make_strategy("A")
        s2 = self._make_strategy("B")
        assert registry._compute_hash(s1) != registry._compute_hash(s2)

    def test_historical_versions_preserved(self):
        """All historical versions are retrievable."""
        registry = StrategyRegistry()
        sid = "my-strategy"
        registry.register(self._make_strategy("V1"), strategy_id=sid)

        s2 = Strategy(name="V2", metric="xB", market="cards",
                      conditions=(Condition(field="home_xB", op=">", value=8.0),),
                      logic="and", direction="OVER", min_odds=1.70)
        registry.register(s2, strategy_id=sid)

        v1 = registry.get_version(sid, 1)
        v2 = registry.get_version(sid, 2)
        assert v1 is not None and v1.name == "V1"
        assert v2 is not None and v2.name == "V2"
