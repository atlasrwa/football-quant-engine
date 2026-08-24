"""Unit tests for the x-Metric vectorized formula engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.engine.xmetrics import XMetricCoefficients, XMetricEngine


class TestXMetricEngine:
    """Tests for XMetricEngine computation methods."""

    def _make_df(self, n: int = 5) -> pd.DataFrame:
        """Create a synthetic DataFrame with all required columns."""
        rng = np.random.default_rng(42)
        return pd.DataFrame({
            "date_unix": np.arange(n) * 86400,
            # xC fields
            "attacks_home": rng.integers(50, 150, n),
            "attacks_away": rng.integers(50, 150, n),
            "dangerous_attacks_home": rng.integers(20, 80, n),
            "dangerous_attacks_away": rng.integers(20, 80, n),
            "shots_off_target_home": rng.integers(1, 10, n),
            "shots_off_target_away": rng.integers(1, 10, n),
            "corners_avg_against_home": rng.uniform(3.0, 7.0, n),
            "corners_avg_against_away": rng.uniform(3.0, 7.0, n),
            # xB fields
            "fouls_home": rng.integers(8, 20, n),
            "fouls_away": rng.integers(8, 20, n),
            "possession_home": rng.uniform(35.0, 65.0, n),
            "possession_away": rng.uniform(35.0, 65.0, n),
            "referee_cards_per_match": rng.uniform(3.0, 6.0, n),
            "xg_against_home": rng.uniform(0.5, 2.5, n),
            "xg_against_away": rng.uniform(0.5, 2.5, n),
            # xO fields
            "offsides_home": rng.integers(0, 6, n),
            "offsides_away": rng.integers(0, 6, n),
            "ppda_home": rng.uniform(5.0, 15.0, n),
            "ppda_away": rng.uniform(5.0, 15.0, n),
        })

    def test_compute_xC_adds_columns(self):
        """xC computation adds home_xC and away_xC columns."""
        engine = XMetricEngine()
        df = self._make_df()
        result = engine.compute_xC(df)

        assert "home_xC" in result.columns
        assert "away_xC" in result.columns
        assert len(result) == len(df)

    def test_compute_xC_formula_correctness(self):
        """Verify xC formula against manual calculation."""
        coeff = XMetricCoefficients(xc_alpha=0.45, xc_beta=0.30, xc_gamma=0.25)
        engine = XMetricEngine(coeff)

        df = pd.DataFrame({
            "attacks_home": [100],
            "dangerous_attacks_home": [60],
            "shots_off_target_home": [4],
            "corners_avg_against_away": [5.0],
            "attacks_away": [80],
            "dangerous_attacks_away": [40],
            "shots_off_target_away": [3],
            "corners_avg_against_home": [6.0],
        })

        result = engine.compute_xC(df)

        # home_xC = 0.45*(60/100) + 0.30*4 + 0.25*5.0
        #         = 0.45*0.6 + 1.2 + 1.25 = 0.27 + 1.2 + 1.25 = 2.72
        expected_home = 0.45 * (60 / 100) + 0.30 * 4 + 0.25 * 5.0
        assert result["home_xC"].iloc[0] == pytest.approx(expected_home, rel=1e-6)

        # away_xC = 0.45*(40/80) + 0.30*3 + 0.25*6.0
        expected_away = 0.45 * (40 / 80) + 0.30 * 3 + 0.25 * 6.0
        assert result["away_xC"].iloc[0] == pytest.approx(expected_away, rel=1e-6)

    def test_compute_xC_division_by_zero(self):
        """xC handles attacks=0 (division by zero) gracefully."""
        engine = XMetricEngine()
        df = pd.DataFrame({
            "attacks_home": [0],
            "dangerous_attacks_home": [10],
            "shots_off_target_home": [2],
            "corners_avg_against_away": [4.0],
            "attacks_away": [50],
            "dangerous_attacks_away": [25],
            "shots_off_target_away": [3],
            "corners_avg_against_home": [5.0],
        })

        result = engine.compute_xC(df)
        # Ratio should be 0.0 when attacks=0
        expected_home = 0.45 * 0.0 + 0.30 * 2 + 0.25 * 4.0
        assert result["home_xC"].iloc[0] == pytest.approx(expected_home, rel=1e-6)

    def test_compute_xC_missing_columns(self):
        """xC produces NaN when required columns are missing."""
        engine = XMetricEngine()
        df = pd.DataFrame({"attacks_home": [100], "attacks_away": [80]})

        result = engine.compute_xC(df)
        # Missing dangerous_attacks → NaN propagation in formula
        assert pd.isna(result["home_xC"].iloc[0])

    def test_compute_xB_adds_columns(self):
        """xB computation adds home_xB and away_xB columns."""
        engine = XMetricEngine()
        df = self._make_df()
        result = engine.compute_xB(df)

        assert "home_xB" in result.columns
        assert "away_xB" in result.columns

    def test_compute_xB_formula_correctness(self):
        """Verify xB formula against manual calculation."""
        coeff = XMetricCoefficients(xb_delta=0.02)
        engine = XMetricEngine(coeff)

        df = pd.DataFrame({
            "fouls_home": [14],
            "fouls_away": [12],
            "possession_home": [55.0],
            "possession_away": [45.0],
            "referee_cards_per_match": [4.4],
            "xg_against_home": [1.5],
            "xg_against_away": [1.2],
        })

        result = engine.compute_xB(df)

        # ref_cards_per_foul = 4.4 / 11.0 = 0.4
        # home_xB = (14 * 0.4) + 0.02 * (100 - 55.0) * (1.2 * 3.5)
        #         = 5.6 + 0.02 * 45.0 * 4.2 = 5.6 + 3.78 = 9.38
        ref_cpf = 4.4 / 11.0
        opp_dribbles_away = 1.2 * 3.5  # xg_against_away * 3.5
        expected_home = 14 * ref_cpf + 0.02 * (100.0 - 55.0) * opp_dribbles_away
        assert result["home_xB"].iloc[0] == pytest.approx(expected_home, rel=1e-6)

    def test_compute_xO_adds_columns(self):
        """xO computation adds home_xO and away_xO columns."""
        engine = XMetricEngine()
        df = self._make_df()
        result = engine.compute_xO(df)

        assert "home_xO" in result.columns
        assert "away_xO" in result.columns

    def test_compute_xO_formula_correctness(self):
        """Verify xO formula against manual calculation."""
        coeff = XMetricCoefficients(xo_eta=1.0)
        engine = XMetricEngine(coeff)

        df = pd.DataFrame({
            "offsides_home": [3],
            "offsides_away": [2],
            "ppda_home": [8.0],
            "ppda_away": [10.0],
        })

        result = engine.compute_xO(df)

        # hli_home = 1/8.0 = 0.125, hli_away = 1/10.0 = 0.1
        # league_baseline = mean([0.125, 0.1]) = 0.1125
        # home_xO = 1.0 * 3 * (hli_away / 0.1125) = 3 * (0.1 / 0.1125)
        hli_home = 1.0 / 8.0
        hli_away = 1.0 / 10.0
        baseline = (hli_home + hli_away) / 2.0
        expected_home = 1.0 * 3 * (hli_away / baseline)
        expected_away = 1.0 * 2 * (hli_home / baseline)

        assert result["home_xO"].iloc[0] == pytest.approx(expected_home, rel=1e-6)
        assert result["away_xO"].iloc[0] == pytest.approx(expected_away, rel=1e-6)

    def test_compute_xO_ppda_zero(self):
        """xO handles ppda=0 (division by zero) gracefully."""
        engine = XMetricEngine()
        df = pd.DataFrame({
            "offsides_home": [3],
            "offsides_away": [2],
            "ppda_home": [0.0],
            "ppda_away": [10.0],
        })

        result = engine.compute_xO(df)
        # ppda_home=0 → hli_home=0, which only affects away_xO's opponent index
        assert not pd.isna(result["home_xO"].iloc[0])

    def test_compute_all_chains_all_metrics(self):
        """compute_all adds all 6 x-Metric columns."""
        engine = XMetricEngine()
        df = self._make_df(10)
        result = engine.compute_all(df)

        expected_cols = ["home_xC", "away_xC", "home_xB", "away_xB", "home_xO", "away_xO"]
        for col in expected_cols:
            assert col in result.columns

    def test_empty_dataframe(self):
        """All computations handle empty DataFrames without error."""
        engine = XMetricEngine()
        df = pd.DataFrame()

        result = engine.compute_xC(df)
        assert "home_xC" in result.columns
        assert len(result) == 0

        result = engine.compute_xB(df)
        assert "home_xB" in result.columns

        result = engine.compute_xO(df)
        assert "home_xO" in result.columns

    def test_does_not_mutate_input(self):
        """Engine returns a copy — original DataFrame is untouched."""
        engine = XMetricEngine()
        df = self._make_df()
        original_cols = set(df.columns)

        engine.compute_all(df)
        assert set(df.columns) == original_cols

    def test_custom_coefficients(self):
        """Custom coefficients alter output values."""
        df = pd.DataFrame({
            "attacks_home": [100],
            "dangerous_attacks_home": [50],
            "shots_off_target_home": [5],
            "corners_avg_against_away": [4.0],
            "attacks_away": [100],
            "dangerous_attacks_away": [50],
            "shots_off_target_away": [5],
            "corners_avg_against_home": [4.0],
        })

        engine_default = XMetricEngine()
        engine_custom = XMetricEngine(XMetricCoefficients(xc_alpha=1.0, xc_beta=0.0, xc_gamma=0.0))

        r1 = engine_default.compute_xC(df)
        r2 = engine_custom.compute_xC(df)

        # With custom (alpha=1, beta=0, gamma=0), xC = just the ratio
        assert r2["home_xC"].iloc[0] == pytest.approx(50 / 100, rel=1e-6)
        assert r1["home_xC"].iloc[0] != r2["home_xC"].iloc[0]
