"""Comprehensive unit tests for the feature engineering module.

Covers edge cases: sparse history, zero-divisors, missing referee data,
first matches of a season, boundary conditions, and look-ahead prevention.
"""

from __future__ import annotations

from typing import List

import pytest

from src.features.assembler import FeatureAssembler
from src.features.referee_volatility import RefereeVolatilityCalculator
from src.features.rolling_form import RollingFormCalculator
from src.features.xg_efficiency import XGEfficiencyCalculator
from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.match import Match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_match(
    id: int = 1,
    date_unix: int = 1700000000,
    home_team: str = "TeamA",
    away_team: str = "TeamB",
    home_goals: int = 2,
    away_goals: int = 1,
    home_xg: float = 1.5,
    away_xg: float = 1.0,
    referee: str | None = "Ref One",
    over_odds: float | None = 1.80,
    under_odds: float | None = 2.10,
) -> Match:
    """Create a Match with sensible defaults for testing."""
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


def _make_sequence(n: int, home: str = "TeamA", away: str = "TeamB") -> List[Match]:
    """Create a sequence of n matches between two teams, 1 day apart."""
    matches = []
    for i in range(n):
        matches.append(
            _make_match(
                id=100 + i,
                date_unix=1700000000 + i * 86400,
                home_team=home,
                away_team=away,
                home_goals=2,
                away_goals=1,
                home_xg=1.5,
                away_xg=1.0,
            )
        )
    return matches


# ===========================================================================
# XGEfficiencyCalculator tests
# ===========================================================================

class TestXGEfficiencyCalculator:
    """Tests for xG Efficiency Delta calculation."""

    def test_compute_delta_basic(self):
        # scored 2, expected 1.5 → (2-1.5)/1.5 = 0.333...
        delta = XGEfficiencyCalculator.compute_delta(2, 1.5)
        assert abs(delta - 0.3333) < 0.001

    def test_compute_delta_underperform(self):
        # scored 0, expected 2.0 → (0-2.0)/2.0 = -1.0
        delta = XGEfficiencyCalculator.compute_delta(0, 2.0)
        assert delta == -1.0

    def test_compute_delta_zero_xg(self):
        # xG=0 should return 0.0 regardless of actual goals
        delta = XGEfficiencyCalculator.compute_delta(3, 0.0)
        assert delta == 0.0

    def test_compute_delta_exact_match(self):
        # scored exactly xG → delta = 0
        delta = XGEfficiencyCalculator.compute_delta(2, 2.0)
        assert delta == 0.0

    def test_first_match_returns_zero(self):
        """First match of a team has no history → rolling delta = 0.0."""
        calc = XGEfficiencyCalculator(window=5)
        matches = [_make_match(id=1, home_goals=3, home_xg=1.0)]
        results = calc.compute_rolling(matches)

        assert results[0] == (1, 0.0, 0.0)

    def test_rolling_builds_up_with_sparse_history(self):
        """With fewer matches than window, uses available history."""
        calc = XGEfficiencyCalculator(window=5)
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="B",
                        home_goals=3, home_xg=2.0, away_goals=1, away_xg=1.0),
            _make_match(id=2, date_unix=200, home_team="A", away_team="B",
                        home_goals=1, home_xg=2.0, away_goals=2, away_xg=1.0),
        ]
        results = calc.compute_rolling(matches)

        # Match 1: no history → (0.0, 0.0)
        assert results[0] == (1, 0.0, 0.0)

        # Match 2: A has 1 prior match with delta=(3-2)/2=0.5, B has delta=(1-1)/1=0.0
        assert abs(results[1][1] - 0.5) < 0.001
        assert abs(results[1][2] - 0.0) < 0.001

    def test_rolling_window_respects_size(self):
        """Rolling window drops old values after window size exceeded."""
        calc = XGEfficiencyCalculator(window=2)
        # Create 4 matches for TeamA with different deltas
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="X",
                        home_goals=4, home_xg=2.0),  # delta=1.0
            _make_match(id=2, date_unix=200, home_team="A", away_team="Y",
                        home_goals=1, home_xg=2.0),  # delta=-0.5
            _make_match(id=3, date_unix=300, home_team="A", away_team="Z",
                        home_goals=3, home_xg=2.0),  # delta=0.5
            _make_match(id=4, date_unix=400, home_team="A", away_team="W",
                        home_goals=2, home_xg=2.0),  # delta=0.0
        ]

        results = calc.compute_rolling(matches)

        # Match 3: A has history [1.0, -0.5] → mean=0.25
        assert abs(results[2][1] - 0.25) < 0.001

        # Match 4: window=2, so history is [-0.5, 0.5] → mean=0.0
        assert abs(results[3][1] - 0.0) < 0.001

    def test_no_look_ahead(self):
        """Current match's delta should not affect its own rolling value."""
        calc = XGEfficiencyCalculator(window=5)
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="B",
                        home_goals=10, home_xg=1.0),  # extreme delta=9.0
        ]
        results = calc.compute_rolling(matches)
        # First match should have 0.0, not be affected by its own delta
        assert results[0][1] == 0.0

    def test_invalid_window_raises(self):
        with pytest.raises(ValueError, match="window must be >= 1"):
            XGEfficiencyCalculator(window=0)

    def test_compute_rolling_map(self):
        calc = XGEfficiencyCalculator(window=5)
        matches = _make_sequence(3)
        result_map = calc.compute_rolling_map(matches)

        assert len(result_map) == 3
        assert 100 in result_map
        assert isinstance(result_map[100], tuple)
        assert len(result_map[100]) == 2


# ===========================================================================
# RollingFormCalculator tests
# ===========================================================================

class TestRollingFormCalculator:
    """Tests for rolling form calculation."""

    def test_match_points_home_win(self):
        match = _make_match(home_goals=2, away_goals=1)
        assert RollingFormCalculator.match_points("TeamA", match) == 3

    def test_match_points_away_win(self):
        match = _make_match(home_goals=0, away_goals=2)
        assert RollingFormCalculator.match_points("TeamB", match) == 3

    def test_match_points_draw(self):
        match = _make_match(home_goals=1, away_goals=1)
        assert RollingFormCalculator.match_points("TeamA", match) == 1
        assert RollingFormCalculator.match_points("TeamB", match) == 1

    def test_match_points_home_loss(self):
        match = _make_match(home_goals=0, away_goals=3)
        assert RollingFormCalculator.match_points("TeamA", match) == 0

    def test_match_points_invalid_team_raises(self):
        match = _make_match()
        with pytest.raises(ValueError, match="not found"):
            RollingFormCalculator.match_points("UnknownTeam", match)

    def test_first_match_form_is_zero(self):
        """First match of a team has no prior history → form = 0.0."""
        calc = RollingFormCalculator(window=6)
        matches = [_make_match(id=1)]
        results = calc.compute_rolling(matches)

        assert results[0] == (1, 0.0, 0.0)

    def test_perfect_form(self):
        """A team winning all prior matches should have form approaching 1.0."""
        calc = RollingFormCalculator(window=3)
        # TeamA wins all 3, then compute at 4th
        matches = [
            _make_match(id=i, date_unix=100 * i, home_team="A", away_team="B",
                        home_goals=2, away_goals=0)
            for i in range(1, 5)
        ]
        results = calc.compute_rolling(matches)

        # 4th match: A has 3 wins (9 points / 9 max) = 1.0
        assert abs(results[3][1] - 1.0) < 0.001
        # B has 3 losses (0 points / 9 max) = 0.0
        assert abs(results[3][2] - 0.0) < 0.001

    def test_all_draws_form(self):
        """All draws should give form = 1/3."""
        calc = RollingFormCalculator(window=3)
        matches = [
            _make_match(id=i, date_unix=100 * i, home_team="A", away_team="B",
                        home_goals=1, away_goals=1)
            for i in range(1, 5)
        ]
        results = calc.compute_rolling(matches)

        # 4th match: 3 draws = 3 points / 9 max = 0.333
        assert abs(results[3][1] - 1.0 / 3.0) < 0.001
        assert abs(results[3][2] - 1.0 / 3.0) < 0.001

    def test_sparse_history_uses_available(self):
        """With 2 matches and window=6, should use 2-match history."""
        calc = RollingFormCalculator(window=6)
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="B",
                        home_goals=3, away_goals=0),  # A wins
            _make_match(id=2, date_unix=200, home_team="A", away_team="B",
                        home_goals=3, away_goals=0),  # A wins
            _make_match(id=3, date_unix=300, home_team="A", away_team="B",
                        home_goals=0, away_goals=0),
        ]
        results = calc.compute_rolling(matches)

        # Match 3: A has 2 wins → 6 points / (3*2) = 1.0
        assert abs(results[2][1] - 1.0) < 0.001
        # B has 2 losses → 0 / (3*2) = 0.0
        assert abs(results[2][2] - 0.0) < 0.001

    def test_window_drops_old_results(self):
        """After window exceeded, old results drop off."""
        calc = RollingFormCalculator(window=2)
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="B",
                        home_goals=3, away_goals=0),  # A wins (3pts)
            _make_match(id=2, date_unix=200, home_team="A", away_team="B",
                        home_goals=0, away_goals=3),  # A loses (0pts)
            _make_match(id=3, date_unix=300, home_team="A", away_team="B",
                        home_goals=0, away_goals=3),  # A loses (0pts)
            _make_match(id=4, date_unix=400, home_team="A", away_team="B",
                        home_goals=0, away_goals=0),
        ]
        results = calc.compute_rolling(matches)

        # Match 4: A's window=[0pts, 0pts] → 0/(3*2)=0.0 (first win dropped)
        assert abs(results[3][1] - 0.0) < 0.001

    def test_invalid_window_raises(self):
        with pytest.raises(ValueError, match="window must be >= 1"):
            RollingFormCalculator(window=0)

    def test_compute_rolling_map(self):
        calc = RollingFormCalculator(window=6)
        matches = _make_sequence(5)
        result_map = calc.compute_rolling_map(matches)

        assert len(result_map) == 5
        assert all(isinstance(v, tuple) and len(v) == 2 for v in result_map.values())


# ===========================================================================
# RefereeVolatilityCalculator tests
# ===========================================================================

class TestRefereeVolatilityCalculator:
    """Tests for referee volatility index calculation."""

    def test_single_referee_above_threshold(self):
        """Referee with enough PRIOR matches gets their own volatility.
        R02 fix: volatility is computed from PRIOR matches only (expanding window).
        Match N sees volatility computed from matches 1..N-1.
        """
        calc = RefereeVolatilityCalculator(min_matches=3)
        matches = [
            _make_match(id=i, date_unix=100 * i, referee="RefA",
                        home_goals=i, away_goals=0)
            for i in range(1, 6)  # goals: 1,2,3,4,5
        ]
        result = calc.compute_index(matches)

        # Match 1: 0 prior matches → league fallback (0 history) = 0.0
        assert result[1] == 0.0
        # Match 4: 3 prior matches (goals: 1,2,3) → ref has min_matches=3 prior → use ref std
        import numpy as np
        expected_std_m4 = float(np.std([1, 2, 3], ddof=0))
        assert abs(result[4] - expected_std_m4) < 0.001
        # Match 5: 4 prior (goals: 1,2,3,4) → std([1,2,3,4])
        expected_std_m5 = float(np.std([1, 2, 3, 4], ddof=0))
        assert abs(result[5] - expected_std_m5) < 0.001

    def test_referee_below_threshold_uses_fallback(self):
        """Referee with fewer than min_matches PRIOR uses league-wide fallback.
        R02 fix: temporal expanding window. Match N uses history[0..N-1].
        """
        calc = RefereeVolatilityCalculator(min_matches=5)
        # RefA has 3 matches, RefB has 5 matches
        matches = [
            _make_match(id=1, date_unix=100, referee="RefA", home_goals=2, away_goals=1),
            _make_match(id=2, date_unix=200, referee="RefA", home_goals=0, away_goals=0),
            _make_match(id=3, date_unix=300, referee="RefA", home_goals=4, away_goals=2),
            _make_match(id=4, date_unix=400, referee="RefB", home_goals=1, away_goals=1),
            _make_match(id=5, date_unix=500, referee="RefB", home_goals=3, away_goals=0),
            _make_match(id=6, date_unix=600, referee="RefB", home_goals=2, away_goals=2),
            _make_match(id=7, date_unix=700, referee="RefB", home_goals=1, away_goals=0),
            _make_match(id=8, date_unix=800, referee="RefB", home_goals=0, away_goals=1),
        ]
        result = calc.compute_index(matches)

        # Match 1: first match, 0 prior → league vol = 0.0 (no history)
        assert result[1] == 0.0
        # Match 8 (RefB): prior RefB goals = [2,3,4,1] (4 < 5) → league fallback
        # League prior to match 8: goals [3,0,6,2,3,4,1] → std
        import numpy as np
        prior_goals_m8 = [3, 0, 6, 2, 3, 4, 1]
        expected_league_vol = float(np.std(prior_goals_m8, ddof=0))
        assert abs(result[8] - expected_league_vol) < 0.001

    def test_null_referee_uses_fallback(self):
        """Matches with no referee use league-wide expanding fallback.
        R02 fix: temporal. Match 1 (first) has no prior data → 0.0.
        """
        calc = RefereeVolatilityCalculator(min_matches=3)
        matches = [
            _make_match(id=1, date_unix=100, referee=None, home_goals=2, away_goals=1),
            _make_match(id=2, date_unix=200, referee="RefA", home_goals=3, away_goals=0),
            _make_match(id=3, date_unix=300, referee="RefA", home_goals=1, away_goals=1),
            _make_match(id=4, date_unix=400, referee="RefA", home_goals=0, away_goals=0),
        ]
        result = calc.compute_index(matches)

        # Match 1: first match, no prior data → 0.0
        assert result[1] == 0.0
        # Match 4 (RefA): has 2 prior RefA matches (< min_matches=3) → league fallback
        # League prior to match 4: goals [3, 3, 2] → std
        import numpy as np
        league_prior_m4 = [3, 3, 2]
        expected = float(np.std(league_prior_m4, ddof=0))
        assert abs(result[4] - expected) < 0.001

    def test_all_same_goals_volatility_zero(self):
        """If all matches have same total goals, volatility = 0."""
        calc = RefereeVolatilityCalculator(min_matches=3)
        matches = [
            _make_match(id=i, date_unix=100 * i, referee="RefA",
                        home_goals=1, away_goals=1)
            for i in range(1, 6)  # all 2 goals
        ]
        result = calc.compute_index(matches)
        assert result[1] == 0.0

    def test_single_match_std_is_zero(self):
        """A single match can't have meaningful std."""
        calc = RefereeVolatilityCalculator(min_matches=1)
        matches = [_make_match(id=1, referee="RefA", home_goals=3, away_goals=0)]
        result = calc.compute_index(matches)
        # std of single value = 0.0
        assert result[1] == 0.0

    def test_invalid_min_matches_raises(self):
        with pytest.raises(ValueError, match="min_matches must be >= 1"):
            RefereeVolatilityCalculator(min_matches=0)

    def test_compute_referee_stats(self):
        calc = RefereeVolatilityCalculator(min_matches=3)
        matches = [
            _make_match(id=i, date_unix=100 * i, referee="RefA",
                        home_goals=i, away_goals=0)
            for i in range(1, 5)
        ]
        stats = calc.compute_referee_stats(matches)

        assert "RefA" in stats
        assert stats["RefA"]["count"] == 4
        assert stats["RefA"]["uses_fallback"] == 0.0  # 4 >= 3


# ===========================================================================
# FeatureAssembler tests
# ===========================================================================

class TestFeatureAssembler:
    """Tests for the FeatureAssembler pipeline."""

    def test_assemble_returns_match_features(self):
        matches = _make_sequence(10)
        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        assert len(features) == 10
        assert all(isinstance(f, MatchFeatures) for f in features)

    def test_empty_input_returns_empty(self):
        assembler = FeatureAssembler()
        features = assembler.assemble([])
        assert features == []

    def test_single_match_produces_features(self):
        """Even a single match should produce a feature vector (with defaults)."""
        assembler = FeatureAssembler()
        matches = [_make_match(id=1)]
        features = assembler.assemble(matches)

        assert len(features) == 1
        f = features[0]
        assert f.match_id == 1
        assert f.home_rolling_form == 0.0
        assert f.away_rolling_form == 0.0
        assert f.home_xg_eff_delta_rolling == 0.0
        assert f.away_xg_eff_delta_rolling == 0.0

    def test_chronological_ordering_preserved(self):
        """Output should be chronologically ordered."""
        matches = [
            _make_match(id=3, date_unix=300),
            _make_match(id=1, date_unix=100),
            _make_match(id=2, date_unix=200),
        ]
        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        assert [f.match_id for f in features] == [1, 2, 3]

    def test_features_bounded_correctly(self):
        """Rolling form should always be in [0, 1]."""
        from tests.conftest import SyntheticMatchGenerator
        gen = SyntheticMatchGenerator(seed=42)
        matches = gen.generate(n_matches=100)

        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        for f in features:
            assert 0.0 <= f.home_rolling_form <= 1.0, (
                f"home_form={f.home_rolling_form} out of bounds"
            )
            assert 0.0 <= f.away_rolling_form <= 1.0, (
                f"away_form={f.away_rolling_form} out of bounds"
            )
            assert f.referee_volatility_index >= 0.0, (
                f"ref_vol={f.referee_volatility_index} negative"
            )

    def test_sparse_history_first_five_matches(self):
        """First 5 matches of a season have sparse history — should not crash."""
        config = StrategyConfig(
            xg_rolling_window=5,
            form_rolling_window=6,
            referee_min_matches=5,
        )
        assembler = FeatureAssembler(config=config)

        matches = [
            _make_match(
                id=i,
                date_unix=1700000000 + i * 86400,
                home_team=f"Team{i % 3}",
                away_team=f"Team{(i + 1) % 3}",
                home_goals=i % 4,
                away_goals=(i + 1) % 3,
                home_xg=float(i % 4) * 0.8,
                away_xg=float((i + 1) % 3) * 0.9,
                referee="Ref1" if i < 3 else None,
            )
            for i in range(5)
        ]

        features = assembler.assemble(matches)
        assert len(features) == 5

        # First match should have zero deltas and form
        assert features[0].home_xg_eff_delta_rolling == 0.0
        assert features[0].home_rolling_form == 0.0

    def test_zero_xg_both_teams(self):
        """Matches where both teams have 0 xG should not produce errors."""
        matches = [
            _make_match(id=1, date_unix=100, home_xg=0.0, away_xg=0.0,
                        home_goals=1, away_goals=0),
            _make_match(id=2, date_unix=200, home_xg=0.0, away_xg=0.0,
                        home_goals=0, away_goals=2),
            _make_match(id=3, date_unix=300, home_xg=0.0, away_xg=0.0,
                        home_goals=3, away_goals=3),
        ]
        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        assert len(features) == 3
        # With 0 xG, delta should be 0.0
        for f in features:
            assert f.home_xg_eff_delta_rolling == 0.0
            assert f.away_xg_eff_delta_rolling == 0.0

    def test_all_null_referees(self):
        """All matches with null referee should use league expanding fallback.
        R02 fix: With temporal computation, the league fallback evolves as
        more data accumulates. All null-referee matches use the expanding
        league-wide volatility at their timestamp (not a global constant).
        """
        matches = [
            _make_match(id=i, date_unix=100 * i, referee=None,
                        home_goals=i % 4, away_goals=(i + 1) % 3)
            for i in range(1, 8)
        ]
        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        assert len(features) == 7
        # First match: no prior data → volatility = 0.0
        assert features[0].referee_volatility_index == 0.0
        # Later matches have expanding volatility (should be non-negative)
        for f in features:
            assert f.referee_volatility_index >= 0.0

    def test_mixed_referees_different_volatility(self):
        """Different referees should potentially have different volatilities."""
        # RefA: consistent low-scoring games
        # RefB: wild high-scoring games
        matches = []
        for i in range(6):
            matches.append(_make_match(
                id=100 + i, date_unix=100 + i * 100,
                referee="RefA", home_goals=1, away_goals=1,
            ))
        for i in range(6):
            matches.append(_make_match(
                id=200 + i, date_unix=700 + i * 100,
                referee="RefB", home_goals=i, away_goals=i,
                home_xg=float(i), away_xg=float(i),
            ))

        config = StrategyConfig(referee_min_matches=5)
        assembler = FeatureAssembler(config=config)
        features = assembler.assemble(matches)

        # RefA matches all have total_goals=2, std=0
        ref_a_features = [f for f in features if f.match_id < 200]
        ref_b_features = [f for f in features if f.match_id >= 200]

        # RefA should have lower volatility than RefB
        ref_a_vol = ref_a_features[-1].referee_volatility_index
        ref_b_vol = ref_b_features[-1].referee_volatility_index
        assert ref_a_vol < ref_b_vol

    def test_assemble_single(self):
        """assemble_single should work for a single target match with history."""
        history = _make_sequence(10, home="A", away="B")
        target = _make_match(
            id=999, date_unix=1700000000 + 20 * 86400,
            home_team="A", away_team="B",
            home_goals=1, away_goals=0,
            home_xg=1.5, away_xg=0.8,
        )

        assembler = FeatureAssembler()
        feature = assembler.assemble_single(target, history)

        assert feature.match_id == 999
        assert isinstance(feature, MatchFeatures)
        # Should have non-zero form since A has been winning
        assert feature.home_rolling_form > 0.0

    def test_assemble_with_fixture_data(self):
        """Integration: assemble from real fixture file."""
        from src.ingestion import MockProvider

        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")

        assembler = FeatureAssembler()
        features = assembler.assemble(matches)

        assert len(features) == 64
        # Verify no NaN or extreme values
        for f in features:
            assert f.home_rolling_form >= 0.0
            assert f.away_rolling_form >= 0.0
            assert f.referee_volatility_index >= 0.0
            assert -10.0 <= f.home_xg_eff_delta_rolling <= 10.0
            assert -10.0 <= f.away_xg_eff_delta_rolling <= 10.0

    def test_custom_config_applied(self):
        """Config window sizes should affect calculations."""
        # Create matches with varied results so windows matter
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="B",
                        home_goals=3, away_goals=0, home_xg=1.0),  # A wins
            _make_match(id=2, date_unix=200, home_team="A", away_team="B",
                        home_goals=0, away_goals=3, home_xg=2.0),  # A loses
            _make_match(id=3, date_unix=300, home_team="A", away_team="B",
                        home_goals=3, away_goals=0, home_xg=1.0),  # A wins
            _make_match(id=4, date_unix=400, home_team="A", away_team="B",
                        home_goals=0, away_goals=3, home_xg=2.0),  # A loses
            _make_match(id=5, date_unix=500, home_team="A", away_team="B",
                        home_goals=3, away_goals=0, home_xg=1.0),  # A wins
            _make_match(id=6, date_unix=600, home_team="A", away_team="B",
                        home_goals=0, away_goals=3, home_xg=2.0),  # A loses
            _make_match(id=7, date_unix=700, home_team="A", away_team="B",
                        home_goals=3, away_goals=0, home_xg=1.0),  # A wins
            _make_match(id=8, date_unix=800, home_team="A", away_team="B",
                        home_goals=3, away_goals=0, home_xg=1.0),  # A wins
            _make_match(id=9, date_unix=900, home_team="A", away_team="B",
                        home_goals=3, away_goals=0, home_xg=1.0),  # A wins
            _make_match(id=10, date_unix=1000, home_team="A", away_team="B",
                        home_goals=2, away_goals=1, home_xg=1.5),
        ]

        config_short = StrategyConfig(xg_rolling_window=2, form_rolling_window=2)
        config_long = StrategyConfig(xg_rolling_window=8, form_rolling_window=8)

        features_short = FeatureAssembler(config=config_short).assemble(matches)
        features_long = FeatureAssembler(config=config_long).assemble(matches)

        # At match 10: short window (2) sees only last 2 wins → form=1.0
        # Long window (8) sees a mix of W/L → form < 1.0
        assert features_short[9].home_rolling_form != features_long[9].home_rolling_form

    def test_no_look_ahead_in_features(self):
        """Feature values at time T should not depend on matches after T."""
        matches = [
            _make_match(id=1, date_unix=100, home_team="A", away_team="B",
                        home_goals=5, away_goals=0, home_xg=1.0),
            _make_match(id=2, date_unix=200, home_team="A", away_team="B",
                        home_goals=0, away_goals=5, home_xg=1.0),
            _make_match(id=3, date_unix=300, home_team="A", away_team="B",
                        home_goals=2, away_goals=1, home_xg=1.5),
        ]

        assembler = FeatureAssembler()

        # Compute with all 3 matches
        features_all = assembler.assemble(matches)

        # Compute with only first 2 matches
        features_partial = assembler.assemble(matches[:2])

        # Match 1 and 2 features should be identical regardless of match 3
        assert features_all[0].home_xg_eff_delta_rolling == features_partial[0].home_xg_eff_delta_rolling
        assert features_all[0].home_rolling_form == features_partial[0].home_rolling_form
        assert features_all[1].home_xg_eff_delta_rolling == features_partial[1].home_xg_eff_delta_rolling
        assert features_all[1].home_rolling_form == features_partial[1].home_rolling_form
