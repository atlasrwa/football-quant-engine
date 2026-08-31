"""Integrity Gate Tests — Phase 2 Pre-Condition Verification.

These tests verify 7 critical invariants before Phase 2 begins:

1. xO league baseline: no temporal leakage under non-stationary regime shift
2. Referee volatility: no temporal leakage under non-stationary regime shift
3. Missing odds can never generate a signal (R03)
4. Missing closing odds cannot generate CLV
5. Quarantined strategies cannot be broadcast as validated
6. content_hash changes when strategy definition changes
7. Same strategy + same version + same dataset = deterministic results

Tests 1 & 2 construct deliberately NON-STATIONARY future observations:
- Historical period: low-corners-against regime (high defensive lines, many offsides)
- Future period: high-corners-against regime (deep blocks, few offsides)
This creates a structural break. Any implementation that leaks future data
into historical features will produce materially different baselines.

The tests verify that features computed for historical matches are IDENTICAL
whether computed with Dataset A (historical only) or Dataset B (historical + future).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np
import pandas as pd
import pytest

from src.engine.market.clv import CLVCalculator, CLVResult
from src.engine.analysis.evaluator import Condition, Signal, Strategy, StrategyEvaluator
from src.engine.analysis.fdr import QuarantineStatus, QuarantineTracker
from src.engine.market.signals.community_broadcaster import BroadcastConfig, CommunityBroadcaster
from src.engine.analysis.strategy_identity import StrategyRegistry
from src.engine.analysis.xmetrics import XMetricCoefficients, XMetricEngine
from src.features.assembler import FeatureAssembler
from src.features.referee_volatility import RefereeVolatilityCalculator
from src.models.config import StrategyConfig
from src.models.match import Match

# Fixed clock outside the default quiet-hours window (1am-6am UTC) so
# CommunityBroadcaster tests don't flake depending on the real wall-clock hour.
_NOON_UTC_CLOCK = lambda: datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)


# ===========================================================================
# Helpers — Regime-shift data generators
# ===========================================================================

def _make_match(
    id: int,
    date_unix: int,
    home_team: str = "TeamA",
    away_team: str = "TeamB",
    home_goals: int = 2,
    away_goals: int = 1,
    home_xg: float = 1.5,
    away_xg: float = 1.0,
    referee: str | None = "RefA",
    over_odds: float | None = 1.90,
    under_odds: float | None = 2.00,
) -> Match:
    """Create a Match with sensible defaults."""
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
        home_xg=home_xg,
        away_xg=away_xg,
        referee=referee,
        over_under_line=2.5,
        over_odds=over_odds,
        under_odds=under_odds,
    )


def _build_xo_regime_shift_df(
    n_historical: int = 20,
    n_future: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build DataFrames with a deliberate corners-against regime shift.

    Historical regime: corners_avg_against ~ 3.0 (aggressive pressing, high HLI ~ 0.33)
    Future regime:     corners_avg_against ~ 10.0 (deep block, low HLI ~ 0.10)

    The expanding-mean league baseline should NOT be affected by the future
    regime when computing historical features.

    Returns:
        (historical_only_df, historical_plus_future_df)
    """
    rng = np.random.default_rng(42)

    base_ts = 1700000000

    # Historical period: aggressive pressing (low corners against → high HLI)
    hist_rows = []
    for i in range(n_historical):
        hist_rows.append({
            "date_unix": base_ts + i * 86400,
            "corners_avg_against_home": rng.uniform(2.5, 4.0),
            "corners_avg_against_away": rng.uniform(2.5, 4.0),
            "offsides_home": rng.integers(2, 8),
            "offsides_away": rng.integers(2, 8),
        })

    # Future period: MASSIVE regime shift to deep-block (high corners against → low HLI)
    future_rows = []
    for i in range(n_future):
        future_rows.append({
            "date_unix": base_ts + (n_historical + i) * 86400,
            "corners_avg_against_home": rng.uniform(9.0, 12.0),  # 3-4x higher
            "corners_avg_against_away": rng.uniform(9.0, 12.0),
            "offsides_home": rng.integers(0, 2),
            "offsides_away": rng.integers(0, 2),
        })

    df_hist = pd.DataFrame(hist_rows)
    df_combined = pd.DataFrame(hist_rows + future_rows)

    return df_hist, df_combined


def _build_referee_regime_shift_matches(
    n_historical: int = 20,
    n_future: int = 20,
) -> tuple[List[Match], List[Match]]:
    """Build match lists with a deliberate goals-per-referee regime shift.

    Historical regime: RefA averages ~2 total goals/match (tight games)
    Future regime:     RefA averages ~7 total goals/match (wild games)

    If the expanding std leaks future data, RefA's historical volatility
    would be inflated by the future high-scoring matches.

    Returns:
        (historical_matches, historical_plus_future_matches)
    """
    rng = np.random.default_rng(99)
    base_ts = 1700000000

    historical: List[Match] = []
    for i in range(n_historical):
        # Tight games: 0-2 goals per side
        hg = int(rng.integers(0, 2))
        ag = int(rng.integers(0, 2))
        historical.append(_make_match(
            id=1000 + i,
            date_unix=base_ts + i * 86400,
            home_goals=hg,
            away_goals=ag,
            home_xg=float(hg) + 0.1,
            away_xg=float(ag) + 0.1,
            referee="RefA",
        ))

    future: List[Match] = []
    for i in range(n_future):
        # Wild games: 3-5 goals per side (massive regime shift)
        hg = int(rng.integers(3, 6))
        ag = int(rng.integers(3, 6))
        future.append(_make_match(
            id=2000 + i,
            date_unix=base_ts + (n_historical + i) * 86400,
            home_goals=hg,
            away_goals=ag,
            home_xg=float(hg) - 0.2,
            away_xg=float(ag) - 0.2,
            referee="RefA",
        ))

    return historical, historical + future


# ===========================================================================
# Test 1: xO League Baseline — Temporal Leakage Regression
# ===========================================================================

class TestXOLeagueBaselineTemporalLeakage:
    """Verify xO league baseline is immune to non-stationary future data.

    The test constructs a deliberate regime shift:
    - Historical: corners_avg_against ~ 3.0 (HLI ~ 0.33)
    - Future:     corners_avg_against ~ 10.5 (HLI ~ 0.095)

    If the baseline used a global mean instead of an expanding mean,
    the future low-HLI values would DRAG DOWN the baseline for historical
    matches, inflating xO values. This test catches that.
    """

    def test_historical_xO_identical_with_or_without_future(self):
        """Features for historical matches must be identical whether
        computed from Dataset A (hist only) or Dataset B (hist + future).
        """
        df_hist, df_combined = _build_xo_regime_shift_df(
            n_historical=20, n_future=20
        )
        engine = XMetricEngine()

        # Dataset A: historical only
        result_a = engine.compute_xO(df_hist.copy())

        # Dataset B: historical + future (regime shift)
        result_b = engine.compute_xO(df_combined.copy())

        # Historical slice from combined result
        n_hist = len(df_hist)

        # All historical xO values must be BIT-FOR-BIT identical
        for col in ["home_xO", "away_xO"]:
            hist_only_vals = result_a[col].values
            combined_hist_vals = result_b[col].values[:n_hist]

            np.testing.assert_array_equal(
                hist_only_vals,
                combined_hist_vals,
                err_msg=(
                    f"TEMPORAL LEAKAGE DETECTED in xO {col}: "
                    f"historical features differ when future data is present. "
                    f"Max delta = {np.max(np.abs(hist_only_vals - combined_hist_vals))}"
                ),
            )

    def test_regime_shift_actually_non_stationary(self):
        """Sanity check: verify the future regime IS materially different.

        Without this, the test above could trivially pass on identical data.
        """
        df_hist, df_combined = _build_xo_regime_shift_df(
            n_historical=20, n_future=20
        )

        # HLI = 1/corners_avg_against: historical avg ~ 0.33, future avg ~ 0.095
        hist_hli = (1.0 / df_hist["corners_avg_against_home"].values + 1.0 / df_hist["corners_avg_against_away"].values) / 2
        future_rows = df_combined.iloc[20:]
        future_hli = (1.0 / future_rows["corners_avg_against_home"].values + 1.0 / future_rows["corners_avg_against_away"].values) / 2

        # The means must differ by at least 50% (they differ by ~3.5x)
        ratio = hist_hli.mean() / future_hli.mean()
        assert ratio > 2.0, (
            f"Regime shift too weak: HLI ratio = {ratio:.2f}, need > 2.0"
        )

    def test_league_baseline_monotonically_expanding(self):
        """The league baseline at row i must depend only on rows 0..i-1."""
        df_hist, _ = _build_xo_regime_shift_df(n_historical=30, n_future=0)
        engine = XMetricEngine()

        # Compute for full 30 rows
        result_full = engine.compute_xO(df_hist.copy())

        # Compute for first 15 rows
        result_partial = engine.compute_xO(df_hist.iloc[:15].copy().reset_index(drop=True))

        # First 15 rows must be identical
        for col in ["home_xO", "away_xO"]:
            np.testing.assert_array_equal(
                result_partial[col].values,
                result_full[col].values[:15],
                err_msg=f"xO {col}: prefix not stable when dataset extended",
            )

    def test_vulnerable_implementation_would_fail(self):
        """Demonstrate that a GLOBAL mean (non-temporal) implementation
        WOULD fail this test — proving the test has discriminating power.

        We simulate what would happen if league_baseline = global mean of ALL HLI.
        """
        df_hist, df_combined = _build_xo_regime_shift_df(
            n_historical=20, n_future=20
        )

        # Simulate vulnerable implementation: global mean baseline
        def _compute_xO_vulnerable(df: pd.DataFrame) -> np.ndarray:
            ca_h = df["corners_avg_against_home"].values.astype(float)
            ca_a = df["corners_avg_against_away"].values.astype(float)
            hli_h = np.where(ca_h > 0, 1.0 / ca_h, 0.0)
            hli_a = np.where(ca_a > 0, 1.0 / ca_a, 0.0)
            row_hli = (hli_h + hli_a) / 2.0
            # VULNERABLE: uses global mean (includes future data)
            global_baseline = np.mean(row_hli)
            ratio = hli_a / global_baseline
            return df["offsides_home"].values * ratio

        # Historical-only
        vuln_hist = _compute_xO_vulnerable(df_hist)
        # Combined (includes future regime shift)
        vuln_combined = _compute_xO_vulnerable(df_combined)[:20]

        # The vulnerable implementation MUST produce different results
        # because the global mean shifts when future data is added
        assert not np.allclose(vuln_hist, vuln_combined, atol=1e-10), (
            "Vulnerable implementation somehow produced identical results — "
            "regime shift may be too weak"
        )


# ===========================================================================
# Test 2: Referee Volatility — Temporal Leakage Regression
# ===========================================================================

class TestRefereeVolatilityTemporalLeakage:
    """Verify referee volatility is immune to non-stationary future data.

    Historical: RefA averages ~2 goals/match (tight, low-variance games)
    Future:     RefA averages ~7 goals/match (wild, high-variance games)

    If volatility computation leaked future high-variance data into
    historical calculations, the std for historical matches would be
    inflated. This test catches that.
    """

    def test_historical_volatility_identical_with_or_without_future(self):
        """Referee volatility for historical matches must be identical
        whether computed from Dataset A or Dataset B.
        """
        historical, combined = _build_referee_regime_shift_matches(
            n_historical=20, n_future=20
        )
        calc = RefereeVolatilityCalculator(min_matches=5)

        # Dataset A: historical only
        vol_a = calc.compute_index(historical)

        # Dataset B: historical + future
        vol_b = calc.compute_index(combined)

        # All historical match volatilities must be identical
        for match in historical:
            assert vol_a[match.id] == pytest.approx(vol_b[match.id], abs=1e-12), (
                f"TEMPORAL LEAKAGE in referee volatility at match {match.id}: "
                f"hist_only={vol_a[match.id]:.8f}, combined={vol_b[match.id]:.8f}, "
                f"delta={abs(vol_a[match.id] - vol_b[match.id]):.2e}"
            )

    def test_regime_shift_actually_non_stationary(self):
        """Verify the future regime has materially different goal stats."""
        historical, combined = _build_referee_regime_shift_matches(
            n_historical=20, n_future=20
        )

        hist_goals = [m.total_goals for m in historical]
        future_goals = [m.total_goals for m in combined[20:]]

        hist_mean = np.mean(hist_goals)
        future_mean = np.mean(future_goals)

        # Future should have much higher mean goals
        assert future_mean > hist_mean * 2.0, (
            f"Regime shift too weak: hist_mean={hist_mean:.1f}, "
            f"future_mean={future_mean:.1f}"
        )

    def test_expanding_volatility_is_prefix_stable(self):
        """Extending the dataset should not change volatility for earlier matches."""
        historical, combined = _build_referee_regime_shift_matches(
            n_historical=20, n_future=20
        )
        calc = RefereeVolatilityCalculator(min_matches=3)

        # Compute at multiple dataset sizes
        for cutoff in [10, 15, 20]:
            partial = calc.compute_index(historical[:cutoff])
            full = calc.compute_index(historical)

            for match in historical[:cutoff]:
                assert partial[match.id] == pytest.approx(full[match.id], abs=1e-12), (
                    f"Prefix instability at match {match.id} "
                    f"(cutoff={cutoff}): "
                    f"partial={partial[match.id]:.8f}, full={full[match.id]:.8f}"
                )

    def test_vulnerable_implementation_would_fail(self):
        """Demonstrate a global-std implementation would fail this test."""
        historical, combined = _build_referee_regime_shift_matches(
            n_historical=20, n_future=20
        )

        # Simulate vulnerable: global std across ALL matches
        def _compute_vulnerable(matches: List[Match]) -> dict:
            all_goals = [m.total_goals for m in matches]
            global_std = float(np.std(all_goals, ddof=0))
            return {m.id: global_std for m in matches}

        vuln_hist = _compute_vulnerable(historical)
        vuln_combined = _compute_vulnerable(combined)

        # Should produce different values for historical matches
        hist_ids = [m.id for m in historical]
        diffs = [abs(vuln_hist[mid] - vuln_combined[mid]) for mid in hist_ids]
        assert max(diffs) > 0.1, (
            "Vulnerable implementation produced identical results — "
            "regime shift too weak or test broken"
        )


# ===========================================================================
# Test 3: Feature Assembler — Combined Temporal Leakage (Integration)
# ===========================================================================

class TestFeatureAssemblerTemporalLeakage:
    """Integration test: full feature pipeline with regime shift."""

    def test_all_features_stable_under_regime_shift(self):
        """Complete feature vector must be identical with or without future data.

        Combines xG efficiency, rolling form, AND referee volatility into
        a single integration test with a multi-dimensional regime shift:
        - Future: different teams dominate (form shift)
        - Future: xG efficiency inverts (overperforming → underperforming)
        - Future: referee becomes wild (volatility shift)
        """
        rng = np.random.default_rng(77)
        base_ts = 1700000000

        # Historical: TeamA consistently wins, RefA has stable low-scoring games
        historical: List[Match] = []
        for i in range(25):
            hg = int(rng.integers(2, 4))  # TeamA scores 2-3
            ag = int(rng.integers(0, 2))  # TeamB scores 0-1
            historical.append(_make_match(
                id=5000 + i,
                date_unix=base_ts + i * 86400,
                home_team="TeamA",
                away_team="TeamB",
                home_goals=hg,
                away_goals=ag,
                home_xg=float(hg) - 0.5,  # overperforming xG
                away_xg=float(ag) + 0.3,  # underperforming xG
                referee="RefA",
            ))

        # Future regime shift: TeamA collapses, wild games
        future: List[Match] = []
        for i in range(25):
            hg = int(rng.integers(0, 1))  # TeamA scores 0
            ag = int(rng.integers(4, 7))  # TeamB dominates
            future.append(_make_match(
                id=6000 + i,
                date_unix=base_ts + (25 + i) * 86400,
                home_team="TeamA",
                away_team="TeamB",
                home_goals=hg,
                away_goals=ag,
                home_xg=float(hg) + 1.5,  # now underperforming xG
                away_xg=float(ag) - 1.0,
                referee="RefA",
            ))

        assembler = FeatureAssembler()

        # Dataset A
        features_a = assembler.assemble(historical)
        # Dataset B
        features_b = assembler.assemble(historical + future)

        # Features for historical matches must be identical
        for fa, fb in zip(features_a, features_b[:25]):
            assert fa.match_id == fb.match_id
            assert fa.home_xg_eff_delta_rolling == pytest.approx(
                fb.home_xg_eff_delta_rolling, abs=1e-10
            ), f"xG eff delta leaked at match {fa.match_id}"
            assert fa.away_xg_eff_delta_rolling == pytest.approx(
                fb.away_xg_eff_delta_rolling, abs=1e-10
            ), f"xG eff delta leaked at match {fa.match_id}"
            assert fa.home_rolling_form == pytest.approx(
                fb.home_rolling_form, abs=1e-10
            ), f"rolling form leaked at match {fa.match_id}"
            assert fa.away_rolling_form == pytest.approx(
                fb.away_rolling_form, abs=1e-10
            ), f"rolling form leaked at match {fa.match_id}"
            assert fa.referee_volatility_index == pytest.approx(
                fb.referee_volatility_index, abs=1e-10
            ), f"ref volatility leaked at match {fa.match_id}"


# ===========================================================================
# Test 4: Missing Odds Cannot Generate a Signal (R03)
# ===========================================================================

class TestMissingOddsSignalSuppression:
    """R03: Missing odds must NEVER create a synthetic betting opportunity."""

    def _make_strategy(self) -> Strategy:
        return Strategy(
            name="Test Over",
            metric="xC",
            market="goals_over_under",
            conditions=(Condition(field="home_xC", op=">", value=1.0),),
            logic="and",
            direction="OVER",
            min_odds=1.01,  # Very low threshold to not filter on odds level
        )

    def test_none_odds_suppress_signal(self):
        """Rows with over_odds=None must produce zero signals."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [5.0, 5.0, 5.0],  # All match condition
            "over_odds": [None, None, None],  # All missing
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0, (
            f"SIGNAL LEAK: {len(signals)} signals generated with None odds"
        )

    def test_nan_odds_suppress_signal(self):
        """Rows with over_odds=NaN must produce zero signals."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [5.0, 5.0],
            "over_odds": [np.nan, np.nan],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0, (
            f"SIGNAL LEAK: {len(signals)} signals generated with NaN odds"
        )

    def test_zero_odds_suppress_signal(self):
        """Rows with over_odds=0.0 must produce zero signals (invalid odds)."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [5.0],
            "over_odds": [0.0],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0

    def test_odds_equal_one_suppress_signal(self):
        """Odds exactly 1.0 are invalid (no profit possible)."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [5.0],
            "over_odds": [1.0],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 0

    def test_valid_odds_produce_signal(self):
        """Sanity: valid odds DO produce signals (test is not vacuously true)."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [5.0],
            "over_odds": [2.10],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        assert len(signals) == 1

    def test_mixed_valid_and_missing_odds(self):
        """Only rows with valid odds produce signals."""
        evaluator = StrategyEvaluator()
        df = pd.DataFrame({
            "home_xC": [5.0, 5.0, 5.0, 5.0, 5.0],
            "over_odds": [2.10, None, np.nan, 0.0, 1.95],
        })
        signals = evaluator.evaluate(df, [self._make_strategy()])
        valid_indices = {s.match_index for s in signals}
        assert valid_indices == {0, 4}, (
            f"Expected signals at indices {{0, 4}}, got {valid_indices}"
        )

    def test_under_direction_missing_odds(self):
        """UNDER direction also suppresses when under_odds is missing."""
        evaluator = StrategyEvaluator()
        strategy = Strategy(
            name="Test Under",
            metric="xC",
            market="goals_over_under",
            conditions=(Condition(field="home_xC", op=">", value=1.0),),
            logic="and",
            direction="UNDER",
            min_odds=1.01,
        )
        df = pd.DataFrame({
            "home_xC": [5.0, 5.0],
            "under_odds": [None, 2.10],
        })
        signals = evaluator.evaluate(df, [strategy])
        assert len(signals) == 1
        assert signals[0].match_index == 1


# ===========================================================================
# Test 5: Missing Closing Odds Cannot Generate CLV
# ===========================================================================

class TestMissingClosingOddsCLV:
    """CLV requires ACTUAL closing market data. No approximation allowed."""

    def test_missing_closing_odds_returns_unavailable(self):
        """CLV must be unavailable when closing_odds is None."""
        result = CLVCalculator.compute(entry_odds=2.10, closing_odds=None)
        assert result.available is False
        assert result.clv_pct is None

    def test_missing_entry_odds_returns_unavailable(self):
        """CLV must be unavailable when entry_odds is None."""
        result = CLVCalculator.compute(entry_odds=None, closing_odds=1.95)
        assert result.available is False
        assert result.clv_pct is None

    def test_both_missing_returns_unavailable(self):
        """Both missing → unavailable."""
        result = CLVCalculator.compute(entry_odds=None, closing_odds=None)
        assert result.available is False
        assert result.clv_pct is None

    def test_closing_odds_lte_one_returns_unavailable(self):
        """Closing odds <= 1.0 are invalid market data."""
        result = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.0)
        assert result.available is False
        assert result.clv_pct is None

        result = CLVCalculator.compute(entry_odds=2.10, closing_odds=0.5)
        assert result.available is False

    def test_entry_odds_lte_one_returns_unavailable(self):
        """Entry odds <= 1.0 are invalid."""
        result = CLVCalculator.compute(entry_odds=1.0, closing_odds=2.00)
        assert result.available is False

    def test_valid_clv_computation(self):
        """Sanity: valid odds produce correct CLV."""
        # Entry=2.10, Close=1.95 → (2.10/1.95 - 1)*100 = 7.69%
        result = CLVCalculator.compute(entry_odds=2.10, closing_odds=1.95)
        assert result.available is True
        assert result.clv_pct == pytest.approx(7.6923, rel=1e-3)

    def test_batch_with_mixed_availability(self):
        """Batch computation respects per-row availability."""
        entry = [2.10, None, 1.90, 2.00]
        closing = [1.95, 2.00, None, 1.0]

        results = CLVCalculator.compute_batch(entry, closing)
        assert results[0].available is True
        assert results[1].available is False
        assert results[2].available is False
        assert results[3].available is False

    def test_aggregate_excludes_unavailable(self):
        """Aggregate CLV only considers available results."""
        results = [
            CLVResult(entry_odds=2.10, closing_odds=1.95, clv_pct=7.69, available=True),
            CLVResult(entry_odds=None, closing_odds=None, clv_pct=None, available=False),
            CLVResult(entry_odds=1.90, closing_odds=2.00, clv_pct=-5.0, available=True),
        ]
        avg = CLVCalculator.aggregate_clv(results)
        assert avg == pytest.approx((7.69 + (-5.0)) / 2, rel=1e-3)

    def test_aggregate_all_unavailable_returns_none(self):
        """If no results are available, aggregate returns None."""
        results = [
            CLVResult(entry_odds=None, closing_odds=None, clv_pct=None, available=False),
            CLVResult(entry_odds=None, closing_odds=None, clv_pct=None, available=False),
        ]
        assert CLVCalculator.aggregate_clv(results) is None


# ===========================================================================
# Test 6: Quarantined Strategies Cannot Be Broadcast as Validated
# ===========================================================================

class TestQuarantineBroadcastGuard:
    """Quarantined (PENDING) strategies must NEVER be broadcast with
    fdr_validated=True. The broadcaster receives validation_passed as an
    external parameter — it must faithfully reflect quarantine state.
    """

    def test_pending_strategy_not_validated(self):
        """A PENDING_QUARANTINE strategy has validation_passed=False."""
        tracker = QuarantineTracker()
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        tracker.enter_quarantine("strategy_alpha", now)

        status = tracker.check_status("strategy_alpha", now)
        assert status == QuarantineStatus.PENDING_QUARANTINE

        # The validation_passed flag for broadcasting should be False
        # (determined by the orchestration layer based on quarantine status)
        validation_passed = (status == QuarantineStatus.PROMOTED)
        assert validation_passed is False

    def test_broadcaster_respects_validation_passed_false(self):
        """Broadcaster must emit fdr_validated=False when told validation_passed=False."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        signal = Signal(
            match_index=0,
            strategy_name="quarantined_strat",
            direction="OVER",
            condition_strength=0.05,
            odds=2.10,
        )
        match_data = [{"home_team": "Arsenal", "away_team": "Chelsea"}]

        payloads = asyncio.run(
            broadcaster.run_once(
                signals=[signal],
                match_data=match_data,
                validation_passed=False,  # NOT validated (quarantined)
            )
        )

        assert len(payloads) == 1
        assert payloads[0].fdr_validated is False, (
            "QUARANTINE BREACH: signal broadcast with fdr_validated=True "
            "despite validation_passed=False"
        )

    def test_broadcaster_only_validates_when_promoted(self):
        """Only PROMOTED strategies get fdr_validated=True."""
        tracker = QuarantineTracker()
        entry_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        tracker.enter_quarantine("strategy_beta", entry_date)

        # After 90 days: promote
        after_90 = entry_date + timedelta(days=91)
        promoted = tracker.promote("strategy_beta", after_90)
        assert promoted is True

        status = tracker.check_status("strategy_beta", after_90)
        validation_passed = (status == QuarantineStatus.PROMOTED)
        assert validation_passed is True

        # Now broadcasting with validation_passed=True is correct
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)
        signal = Signal(
            match_index=0,
            strategy_name="strategy_beta",
            direction="OVER",
            condition_strength=0.08,
            odds=1.95,
        )
        payloads = asyncio.run(
            broadcaster.run_once(
                signals=[signal],
                match_data=[{"home_team": "A", "away_team": "B"}],
                validation_passed=True,
            )
        )
        assert payloads[0].fdr_validated is True

    def test_rejected_strategy_not_validated(self):
        """REJECTED strategies also must not be validated."""
        tracker = QuarantineTracker()
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        tracker.enter_quarantine("strategy_gamma", now)
        tracker.reject("strategy_gamma")

        status = tracker.check_status("strategy_gamma", now)
        assert status == QuarantineStatus.REJECTED
        validation_passed = (status == QuarantineStatus.PROMOTED)
        assert validation_passed is False

    def test_cannot_promote_before_90_days(self):
        """Promotion before 90 days must fail."""
        tracker = QuarantineTracker()
        entry = datetime(2024, 1, 1, tzinfo=timezone.utc)
        tracker.enter_quarantine("early_bird", entry)

        day_89 = entry + timedelta(days=89)
        promoted = tracker.promote("early_bird", day_89)
        assert promoted is False

        status = tracker.check_status("early_bird", day_89)
        assert status == QuarantineStatus.PENDING_QUARANTINE


# ===========================================================================
# Test 7: content_hash Changes When Strategy Definition Changes
# ===========================================================================

class TestContentHashIntegrity:
    """Strategy content_hash must be deterministic and change-sensitive."""

    def _make_strategy(self, **overrides) -> Strategy:
        defaults = {
            "name": "Hash Test Strategy",
            "metric": "xC",
            "market": "corners_over_under",
            "conditions": (Condition(field="home_xC", op=">", value=2.5),),
            "logic": "and",
            "direction": "OVER",
            "min_odds": 1.70,
        }
        defaults.update(overrides)
        return Strategy(**defaults)

    def test_identical_strategy_same_hash(self):
        """Identical definitions produce the same content_hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy()
        s2 = self._make_strategy()

        id1 = registry.register(s1, strategy_id="test-id-1")
        id2 = registry.register(s2, strategy_id="test-id-1")

        # Same content → same version returned
        assert id1.content_hash == id2.content_hash
        assert id1.strategy_version == id2.strategy_version

    def test_name_change_alters_hash(self):
        """Changing strategy name changes the hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(name="Original Name")
        s2 = self._make_strategy(name="Modified Name")

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        assert h1 != h2, "content_hash unchanged despite name change"

    def test_condition_value_change_alters_hash(self):
        """Changing a condition threshold changes the hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(
            conditions=(Condition(field="home_xC", op=">", value=2.5),)
        )
        s2 = self._make_strategy(
            conditions=(Condition(field="home_xC", op=">", value=3.0),)
        )

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        assert h1 != h2, "content_hash unchanged despite condition value change"

    def test_condition_operator_change_alters_hash(self):
        """Changing operator changes the hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(
            conditions=(Condition(field="home_xC", op=">", value=2.5),)
        )
        s2 = self._make_strategy(
            conditions=(Condition(field="home_xC", op=">=", value=2.5),)
        )

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        assert h1 != h2, "content_hash unchanged despite operator change"

    def test_direction_change_alters_hash(self):
        """Changing direction changes the hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(direction="OVER")
        s2 = self._make_strategy(direction="UNDER")

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        assert h1 != h2, "content_hash unchanged despite direction change"

    def test_min_odds_change_alters_hash(self):
        """Changing min_odds changes the hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(min_odds=1.70)
        s2 = self._make_strategy(min_odds=1.85)

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        assert h1 != h2, "content_hash unchanged despite min_odds change"

    def test_logic_change_alters_hash(self):
        """Changing logic combinator changes the hash."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(
            logic="and",
            conditions=(
                Condition(field="home_xC", op=">", value=2.0),
                Condition(field="away_xC", op=">", value=1.5),
            ),
        )
        s2 = self._make_strategy(
            logic="or",
            conditions=(
                Condition(field="home_xC", op=">", value=2.0),
                Condition(field="away_xC", op=">", value=1.5),
            ),
        )

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        assert h1 != h2, "content_hash unchanged despite logic change"

    def test_condition_order_does_not_matter(self):
        """Condition ORDER should affect hash (they're stored as tuple = ordered).

        Note: conditions are stored in an ordered tuple. Different orderings
        represent different strategy definitions (evaluation order matters
        for short-circuit logic in some contexts).
        """
        registry = StrategyRegistry()
        s1 = self._make_strategy(
            conditions=(
                Condition(field="home_xC", op=">", value=2.0),
                Condition(field="away_xC", op=">", value=1.5),
            ),
        )
        s2 = self._make_strategy(
            conditions=(
                Condition(field="away_xC", op=">", value=1.5),
                Condition(field="home_xC", op=">", value=2.0),
            ),
        )

        h1 = registry._compute_hash(s1)
        h2 = registry._compute_hash(s2)
        # Different order = different hash (conditions are ordered)
        assert h1 != h2

    def test_hash_is_valid_sha256(self):
        """Hash must be a valid 64-char hex SHA-256."""
        registry = StrategyRegistry()
        s = self._make_strategy()
        h = registry._compute_hash(s)

        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_version_increments_on_content_change(self):
        """Registry creates new version when content changes."""
        registry = StrategyRegistry()
        s1 = self._make_strategy(name="V1 Strategy", min_odds=1.70)
        s2 = self._make_strategy(name="V1 Strategy", min_odds=2.00)

        id1 = registry.register(s1, strategy_id="strat-001")
        id2 = registry.register(s2, strategy_id="strat-001")

        assert id1.strategy_version == 1
        assert id2.strategy_version == 2
        assert id1.content_hash != id2.content_hash


# ===========================================================================
# Test 8: Deterministic Results (Same Input → Same Output)
# ===========================================================================

class TestDeterministicResults:
    """Same strategy + same dataset must always produce identical results."""

    def test_feature_assembly_deterministic(self):
        """Running feature assembly twice produces bit-identical results."""
        rng = np.random.default_rng(42)
        base_ts = 1700000000

        matches: List[Match] = []
        teams = ["A", "B", "C", "D"]
        for i in range(50):
            ht, at = teams[i % 4], teams[(i + 1) % 4]
            hg = int(rng.integers(0, 4))
            ag = int(rng.integers(0, 4))
            matches.append(_make_match(
                id=7000 + i,
                date_unix=base_ts + i * 86400,
                home_team=ht,
                away_team=at,
                home_goals=hg,
                away_goals=ag,
                home_xg=max(0.0, float(hg) + rng.uniform(-0.5, 0.5)),
                away_xg=max(0.0, float(ag) + rng.uniform(-0.5, 0.5)),
                referee="RefA" if i % 3 == 0 else "RefB",
            ))

        assembler = FeatureAssembler()

        run1 = assembler.assemble(matches)
        run2 = assembler.assemble(matches)

        assert len(run1) == len(run2)
        for f1, f2 in zip(run1, run2):
            assert f1.match_id == f2.match_id
            assert f1.home_xg_eff_delta_rolling == f2.home_xg_eff_delta_rolling
            assert f1.away_xg_eff_delta_rolling == f2.away_xg_eff_delta_rolling
            assert f1.home_rolling_form == f2.home_rolling_form
            assert f1.away_rolling_form == f2.away_rolling_form
            assert f1.referee_volatility_index == f2.referee_volatility_index

    def test_xO_computation_deterministic(self):
        """xO engine produces identical results on repeated calls."""
        df_hist, _ = _build_xo_regime_shift_df(n_historical=30, n_future=0)
        engine = XMetricEngine()

        r1 = engine.compute_xO(df_hist.copy())
        r2 = engine.compute_xO(df_hist.copy())

        np.testing.assert_array_equal(r1["home_xO"].values, r2["home_xO"].values)
        np.testing.assert_array_equal(r1["away_xO"].values, r2["away_xO"].values)

    def test_strategy_evaluation_deterministic(self):
        """Strategy evaluation on same data produces same signals."""
        evaluator = StrategyEvaluator()
        rng = np.random.default_rng(55)

        df = pd.DataFrame({
            "home_xC": rng.uniform(1.5, 4.0, 50),
            "away_xC": rng.uniform(1.5, 4.0, 50),
            "over_odds": rng.uniform(1.60, 2.40, 50),
        })

        strategy = Strategy(
            name="Determinism Test",
            metric="xC",
            market="corners",
            conditions=(Condition(field="home_xC", op=">", value=2.5),),
            logic="and",
            direction="OVER",
            min_odds=1.50,
        )

        signals_1 = evaluator.evaluate(df, [strategy])
        signals_2 = evaluator.evaluate(df, [strategy])

        assert len(signals_1) == len(signals_2)
        for s1, s2 in zip(signals_1, signals_2):
            assert s1.match_index == s2.match_index
            assert s1.condition_strength == s2.condition_strength
            assert s1.odds == s2.odds
            assert s1.direction == s2.direction

    def test_content_hash_deterministic(self):
        """Same strategy definition always produces same content_hash."""
        registry = StrategyRegistry()
        strategy = Strategy(
            name="Deterministic Hash",
            metric="xB",
            market="cards",
            conditions=(
                Condition(field="home_xB", op=">=", value=8.0),
                Condition(field="away_xB", op=">=", value=7.0),
            ),
            logic="and",
            direction="OVER",
            min_odds=1.80,
        )

        hashes = set()
        for _ in range(100):
            hashes.add(registry._compute_hash(strategy))

        assert len(hashes) == 1, (
            f"content_hash non-deterministic: produced {len(hashes)} distinct hashes"
        )

    def test_clv_deterministic(self):
        """CLV computation is deterministic."""
        first_result = CLVCalculator.compute(2.10, 1.95)
        for _ in range(100):
            result = CLVCalculator.compute(2.10, 1.95)
            assert result.clv_pct == first_result.clv_pct
        # Also verify the value is correct
        expected = (2.10 / 1.95 - 1.0) * 100.0
        assert first_result.clv_pct == pytest.approx(expected, abs=1e-10)

    def test_shuffled_input_order_produces_same_features(self):
        """Feature assembly is order-independent (sorted internally)."""
        rng = np.random.default_rng(42)
        base_ts = 1700000000

        matches: List[Match] = []
        for i in range(30):
            hg = int(rng.integers(0, 4))
            ag = int(rng.integers(0, 4))
            matches.append(_make_match(
                id=8000 + i,
                date_unix=base_ts + i * 86400,
                home_team="X",
                away_team="Y",
                home_goals=hg,
                away_goals=ag,
                home_xg=float(hg) + 0.1,
                away_xg=float(ag) + 0.1,
                referee="RefC",
            ))

        assembler = FeatureAssembler()

        # Ordered input
        features_ordered = assembler.assemble(matches)

        # Shuffled input
        shuffled = matches.copy()
        np.random.default_rng(123).shuffle(shuffled)
        features_shuffled = assembler.assemble(shuffled)

        # Results must be identical (assembler sorts internally)
        assert len(features_ordered) == len(features_shuffled)
        for fo, fs in zip(features_ordered, features_shuffled):
            assert fo.match_id == fs.match_id
            assert fo.home_xg_eff_delta_rolling == fs.home_xg_eff_delta_rolling
            assert fo.away_xg_eff_delta_rolling == fs.away_xg_eff_delta_rolling
            assert fo.home_rolling_form == fs.home_rolling_form
            assert fo.away_rolling_form == fs.away_rolling_form
            assert fo.referee_volatility_index == fs.referee_volatility_index
