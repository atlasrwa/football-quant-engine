"""Tests for feature registry and feature transform engine."""

import pytest
import numpy as np

from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)


class TestFeatureDefinition:
    """Tests for FeatureDefinition."""

    def test_content_hash_deterministic(self):
        f1 = FeatureDefinition(
            name="corners_avg_5",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
        )
        f2 = FeatureDefinition(
            name="corners_avg_5",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
        )
        assert f1.content_hash == f2.content_hash

    def test_content_hash_changes_with_params(self):
        f1 = FeatureDefinition(
            name="corners_avg",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
        )
        f2 = FeatureDefinition(
            name="corners_avg",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 10},
        )
        assert f1.content_hash != f2.content_hash

    def test_feature_id_includes_hash(self):
        f = FeatureDefinition(
            name="test_feature",
            source_fields=("x",),
            transform=TransformType.RAW,
        )
        assert f.name in f.feature_id
        assert f.content_hash in f.feature_id

    def test_frozen_immutability(self):
        f = FeatureDefinition(
            name="test",
            source_fields=("x",),
            transform=TransformType.RAW,
        )
        with pytest.raises(Exception):
            f.name = "changed"  # type: ignore


class TestFeatureRegistry:
    """Tests for FeatureRegistry."""

    @pytest.fixture
    def registry(self):
        return FeatureRegistry()

    def test_register_returns_feature_id(self, registry):
        f = FeatureDefinition(
            name="test", source_fields=("x",), transform=TransformType.RAW
        )
        fid = registry.register(f)
        assert fid == f.feature_id

    def test_register_is_idempotent(self, registry):
        f = FeatureDefinition(
            name="test", source_fields=("x",), transform=TransformType.RAW
        )
        fid1 = registry.register(f)
        fid2 = registry.register(f)
        assert fid1 == fid2
        assert registry.count == 1

    def test_register_many(self, registry):
        features = [
            FeatureDefinition(name=f"f{i}", source_fields=("x",), transform=TransformType.RAW)
            for i in range(5)
        ]
        ids = registry.register_many(features)
        assert len(ids) == 5
        assert registry.count == 5

    def test_get_by_id(self, registry):
        f = FeatureDefinition(
            name="test", source_fields=("x",), transform=TransformType.RAW
        )
        fid = registry.register(f)
        retrieved = registry.get(fid)
        assert retrieved is not None
        assert retrieved.name == "test"

    def test_get_nonexistent_returns_none(self, registry):
        assert registry.get("nonexistent") is None

    def test_get_by_name(self, registry):
        f1 = FeatureDefinition(
            name="corners", source_fields=("x",), transform=TransformType.RAW
        )
        f2 = FeatureDefinition(
            name="corners", source_fields=("x",), transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
        )
        registry.register(f1)
        registry.register(f2)
        results = registry.get_by_name("corners")
        assert len(results) == 2

    def test_features_for_market(self, registry):
        f1 = FeatureDefinition(
            name="corners_feat", source_fields=("x",), transform=TransformType.RAW,
            market_applicability=("CORNERS_TOTAL",),
        )
        f2 = FeatureDefinition(
            name="goals_feat", source_fields=("y",), transform=TransformType.RAW,
            market_applicability=("GOALS_TOTAL",),
        )
        f3 = FeatureDefinition(
            name="universal_feat", source_fields=("z",), transform=TransformType.RAW,
            market_applicability=(),  # all markets
        )
        registry.register_many([f1, f2, f3])
        corners_feats = registry.features_for_market("CORNERS_TOTAL")
        assert len(corners_feats) == 2  # f1 + f3

    def test_content_hash_of_registry(self, registry):
        f = FeatureDefinition(
            name="test", source_fields=("x",), transform=TransformType.RAW
        )
        registry.register(f)
        h1 = registry.content_hash()
        h2 = registry.content_hash()
        assert h1 == h2


class TestFeatureTransformEngine:
    """Tests for FeatureTransformEngine."""

    @pytest.fixture
    def engine(self):
        return FeatureTransformEngine()

    @pytest.fixture
    def sample_matches(self):
        """10 matches with simple data for one team."""
        return [
            {
                "home_team": "TeamA",
                "away_team": "TeamB",
                "date_unix": 1000000 + i * 86400,
                "corners_home": 5 + i,
                "corners_away": 3 + i,
                "shots_home": 10 + i,
                "shots_away": 8,
                "total_corners": 8 + 2 * i,
            }
            for i in range(10)
        ]

    def test_raw_feature(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="raw_corners",
            source_fields=("corners_home",),
            transform=TransformType.RAW,
        )
        results = engine.compute_features(sample_matches, [feat])
        assert len(results) == 10
        assert results[0][feat.feature_id] == 5.0
        assert results[5][feat.feature_id] == 10.0

    def test_rolling_mean_temporal_causality(self, engine, sample_matches):
        """Rolling mean at index i must NOT include match i."""
        feat = FeatureDefinition(
            name="corners_avg_3",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 3, "team_field": "home_team", "min_periods": 3},
        )
        results = engine.compute_features(sample_matches, [feat])
        # First 3 matches should have None (min_periods=3)
        assert feat.feature_id not in results[0]
        assert feat.feature_id not in results[1]
        assert feat.feature_id not in results[2]
        # Match 3: average of matches 0,1,2 = (5+6+7)/3 = 6.0
        assert abs(results[3][feat.feature_id] - 6.0) < 0.001

    def test_rolling_mean_window_respected(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="corners_avg_3",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 3, "team_field": "home_team", "min_periods": 3},
        )
        results = engine.compute_features(sample_matches, [feat])
        # Match 5: avg of matches 2,3,4 = (7+8+9)/3 = 8.0
        assert abs(results[5][feat.feature_id] - 8.0) < 0.001

    def test_rolling_std(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="corners_std_5",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_STD,
            params={"window": 5, "team_field": "home_team", "min_periods": 3},
        )
        results = engine.compute_features(sample_matches, [feat])
        # Should be computable from match 3 onwards
        assert feat.feature_id in results[3]

    def test_ewma(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="corners_ewma",
            source_fields=("corners_home",),
            transform=TransformType.EWMA,
            params={"alpha": 0.3, "team_field": "home_team", "min_periods": 3},
        )
        results = engine.compute_features(sample_matches, [feat])
        assert feat.feature_id not in results[0]
        assert feat.feature_id not in results[1]
        assert feat.feature_id not in results[2]
        assert feat.feature_id in results[3]

    def test_difference(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="corner_diff",
            source_fields=("corners_home", "corners_away"),
            transform=TransformType.DIFFERENCE,
        )
        results = engine.compute_features(sample_matches, [feat])
        # corners_home[0]=5, corners_away[0]=3, diff=2
        assert results[0][feat.feature_id] == 2.0

    def test_ratio(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="corner_ratio",
            source_fields=("corners_home", "corners_away"),
            transform=TransformType.RATIO,
        )
        results = engine.compute_features(sample_matches, [feat])
        # corners_home[0]=5, corners_away[0]=3, ratio=5/3
        assert abs(results[0][feat.feature_id] - 5.0 / 3.0) < 0.001

    def test_ratio_zero_denominator_returns_none(self, engine):
        matches = [{"field_a": 5.0, "field_b": 0.0}]
        feat = FeatureDefinition(
            name="ratio_zero",
            source_fields=("field_a", "field_b"),
            transform=TransformType.RATIO,
        )
        results = engine.compute_features(matches, [feat])
        assert feat.feature_id not in results[0]

    def test_zscore(self, engine):
        # Create matches with known pattern
        matches = [{"value": float(i), "home_team": "A"} for i in range(20)]
        feat = FeatureDefinition(
            name="value_zscore",
            source_fields=("value",),
            transform=TransformType.Z_SCORE,
            params={"min_periods": 10},
        )
        results = engine.compute_features(matches, [feat])
        # First 10 should be None
        for i in range(10):
            assert feat.feature_id not in results[i]
        # From 10 onwards should have values
        assert feat.feature_id in results[10]

    def test_interaction(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="interaction",
            source_fields=("corners_home", "corners_away"),
            transform=TransformType.INTERACTION,
        )
        results = engine.compute_features(sample_matches, [feat])
        # 5 * 3 = 15
        assert results[0][feat.feature_id] == 15.0

    def test_trend(self, engine, sample_matches):
        feat = FeatureDefinition(
            name="trend",
            source_fields=("corners_home",),
            transform=TransformType.TREND,
            params={"window": 5, "team_field": "home_team", "min_periods": 4},
        )
        results = engine.compute_features(sample_matches, [feat])
        # Linear increasing data → positive slope
        assert feat.feature_id not in results[0]
        assert feat.feature_id in results[4]
        assert results[4][feat.feature_id] > 0  # Upward trend

    def test_momentum(self, engine):
        # Create matches with a momentum shift
        matches = [
            {"value": 5.0, "home_team": "A"} for _ in range(8)
        ] + [
            {"value": 10.0, "home_team": "A"} for _ in range(5)
        ]
        feat = FeatureDefinition(
            name="momentum",
            source_fields=("value",),
            transform=TransformType.MOMENTUM,
            params={"short_window": 3, "long_window": 10, "team_field": "home_team"},
        )
        results = engine.compute_features(matches, [feat])
        # After shift, short mean should exceed long mean → positive momentum
        assert feat.feature_id in results[12]
        assert results[12][feat.feature_id] > 0

    def test_none_values_handled(self, engine):
        matches = [
            {"value": None, "home_team": "A"},
            {"value": 5.0, "home_team": "A"},
        ]
        feat = FeatureDefinition(
            name="raw",
            source_fields=("value",),
            transform=TransformType.RAW,
        )
        results = engine.compute_features(matches, [feat])
        assert feat.feature_id not in results[0]
        assert results[1][feat.feature_id] == 5.0

    def test_multiple_features_computed_together(self, engine, sample_matches):
        features = [
            FeatureDefinition(name="raw", source_fields=("corners_home",), transform=TransformType.RAW),
            FeatureDefinition(name="diff", source_fields=("corners_home", "corners_away"), transform=TransformType.DIFFERENCE),
        ]
        results = engine.compute_features(sample_matches, features)
        assert len(results) == 10
        assert features[0].feature_id in results[0]
        assert features[1].feature_id in results[0]



class TestLeagueNormalizeTransform:
    """Tests for LEAGUE_NORMALIZE transform."""

    @pytest.fixture
    def engine(self):
        return FeatureTransformEngine()

    def test_normalizes_relative_to_league_history(self, engine):
        """Value normalized against prior league values."""
        # 25 matches in same league, all with value=10, then one with value=20
        matches = [{"league_id": 1, "value": 10.0} for _ in range(25)]
        matches.append({"league_id": 1, "value": 20.0})

        feat = FeatureDefinition(
            name="val_league_norm",
            source_fields=("value",),
            transform=TransformType.LEAGUE_NORMALIZE,
            params={"min_periods": 20, "league_field": "league_id"},
        )
        results = engine.compute_features(matches, [feat])

        # First 20 matches: not enough history
        for i in range(20):
            assert feat.feature_id not in results[i]

        # Match 20: has enough history (all 10s), value=10 → z=0
        assert feat.feature_id in results[20]
        assert abs(results[20][feat.feature_id] - 0.0) < 0.001

        # Match 25: value=20, history is all 10s, std=0 (after adding match 20's 10)
        # Actually history is [10]*25, mean=10, std=0 → returns 0.0 (std==0 branch)
        # But wait: match 21-24 also add 10.0 to history. And match 25's value is 20.
        # History at match 25 = [10]*25, mean=10, std=0 → 0.0
        assert feat.feature_id in results[25]
        assert results[25][feat.feature_id] == 0.0

    def test_different_leagues_separate_histories(self, engine):
        """Each league has its own normalization pool."""
        matches = []
        # League A: all values = 100
        for _ in range(25):
            matches.append({"league_id": "A", "value": 100.0})
        # League B: all values = 10
        for _ in range(25):
            matches.append({"league_id": "B", "value": 10.0})
        # Add one more to league B with value 20
        matches.append({"league_id": "B", "value": 20.0})

        feat = FeatureDefinition(
            name="val_league_norm",
            source_fields=("value",),
            transform=TransformType.LEAGUE_NORMALIZE,
            params={"min_periods": 20, "league_field": "league_id"},
        )
        results = engine.compute_features(matches, [feat])

        # League B's history is all 10s (std=0) so last match returns 0.0
        # (zero std protection)
        assert results[50][feat.feature_id] == 0.0

    def test_excludes_current_match_from_normalization(self, engine):
        """The current match's value must NOT be in the normalization pool."""
        # 22 matches with value=5, then one with value=1000
        matches = [{"league_id": 1, "value": 5.0} for _ in range(22)]
        matches.append({"league_id": 1, "value": 1000.0})

        feat = FeatureDefinition(
            name="val_league_norm",
            source_fields=("value",),
            transform=TransformType.LEAGUE_NORMALIZE,
            params={"min_periods": 20, "league_field": "league_id"},
        )
        results = engine.compute_features(matches, [feat])

        # At match 22 (index 22): history is [5]*22, mean=5, std=0 → 0.0
        # Value 1000 would make std non-zero if included → proves exclusion
        assert results[22][feat.feature_id] == 0.0


class TestHomeAwayNormalizeTransform:
    """Tests for HOME_AWAY_NORMALIZE transform."""

    @pytest.fixture
    def engine(self):
        return FeatureTransformEngine()

    def test_normalizes_relative_to_venue_history(self, engine):
        """Value normalized against prior home/away averages."""
        # 25 home matches with value=6
        matches = [{"home_team": f"T{i}", "value": 6.0} for i in range(25)]
        # Then one home match with value=12
        matches.append({"home_team": "T25", "value": 12.0})

        feat = FeatureDefinition(
            name="val_ha_norm",
            source_fields=("value",),
            transform=TransformType.HOME_AWAY_NORMALIZE,
            params={"min_periods": 20, "venue_field": "home_team"},
        )
        results = engine.compute_features(matches, [feat])

        # First 20: not enough history
        for i in range(20):
            assert feat.feature_id not in results[i]

        # Match 20 onwards: history is all 6.0, std=0 → 0.0
        assert results[20][feat.feature_id] == 0.0

    def test_excludes_current_match(self, engine):
        """Current match excluded from venue normalization."""
        matches = [{"home_team": f"T{j}", "value": 5.0} for j in range(22)]
        matches.append({"home_team": "T_new", "value": 500.0})

        feat = FeatureDefinition(
            name="val_ha_norm",
            source_fields=("value",),
            transform=TransformType.HOME_AWAY_NORMALIZE,
            params={"min_periods": 20, "venue_field": "home_team"},
        )
        results = engine.compute_features(matches, [feat])

        # History is all 5.0, std=0 → returns 0.0 (not infinity or error)
        assert results[22][feat.feature_id] == 0.0


class TestVolatilityTransform:
    """Tests for VOLATILITY transform."""

    @pytest.fixture
    def engine(self):
        return FeatureTransformEngine()

    def test_computes_rolling_std_for_team(self, engine):
        """Volatility = rolling std of prior observations."""
        # Team A with increasing values: 1, 2, 3, 4, 5, 6, 7, 8
        matches = [
            {"home_team": "A", "value": float(i + 1)}
            for i in range(8)
        ]

        feat = FeatureDefinition(
            name="val_volatility",
            source_fields=("value",),
            transform=TransformType.VOLATILITY,
            params={"window": 5, "team_field": "home_team", "min_periods": 4},
        )
        results = engine.compute_features(matches, [feat])

        # First 4 matches: not enough history
        for i in range(4):
            assert feat.feature_id not in results[i]

        # Match 4: history = [1,2,3,4], std(ddof=1)
        expected_std = float(np.std([1, 2, 3, 4], ddof=1))
        assert abs(results[4][feat.feature_id] - expected_std) < 0.001

    def test_excludes_current_match(self, engine):
        """Volatility at match i uses only prior data."""
        # All 5.0 then a spike at the end
        matches = [{"home_team": "A", "value": 5.0} for _ in range(6)]
        matches.append({"home_team": "A", "value": 100.0})

        feat = FeatureDefinition(
            name="val_volatility",
            source_fields=("value",),
            transform=TransformType.VOLATILITY,
            params={"window": 5, "team_field": "home_team", "min_periods": 4},
        )
        results = engine.compute_features(matches, [feat])

        # At match 6 (spike): history is all 5.0, std(ddof=1) = 0
        assert results[6][feat.feature_id] == 0.0

    def test_high_volatility_detected(self, engine):
        """Alternating values should show higher volatility than constant."""
        # Team A: alternates between 2 and 8
        matches = [
            {"home_team": "A", "value": 2.0 if i % 2 == 0 else 8.0}
            for i in range(8)
        ]

        feat = FeatureDefinition(
            name="val_volatility",
            source_fields=("value",),
            transform=TransformType.VOLATILITY,
            params={"window": 5, "team_field": "home_team", "min_periods": 4},
        )
        results = engine.compute_features(matches, [feat])

        # Should show non-zero volatility
        assert results[4][feat.feature_id] > 2.0  # std of [2,8,2,8] is ~3.16
