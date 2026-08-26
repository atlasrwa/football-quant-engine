"""Tests for Batch 3 — Candidate Discovery Engine.

Tests cover:
- Candidate identity (deterministic hashing)
- Operators (threshold, difference, ratio, interaction, trend, relative)
- Budget controls (max candidates, max interaction depth, etc.)
- Deduplication (exact and equivalent)
- Missing data handling
- Temporal integrity
- Market compatibility
- Sample-size filtering
- Correlation/redundancy filtering
- Feature families
- Parameter spaces
- Deterministic generation
- Performance benchmark
"""

import time

import numpy as np
import pytest

from src.research.candidates import (
    CandidateCondition,
    CandidateDiscoveryEngine,
    CandidateOperator,
    CandidateStatus,
    DiscoveryBudget,
    GenerationMethod,
    GenerationReport,
    ResearchCandidate,
)
from src.research.feature_families import (
    FeatureFamily,
    FeatureFamilyAssignment,
    FeatureFamilyRegistry,
)
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)
from src.research.parameter_space import (
    ParameterGrid,
    ParameterRange,
    ParameterSet,
    rolling_window_params,
    threshold_quantile_params,
)


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def registry():
    """Feature registry with test features."""
    reg = FeatureRegistry()
    features = [
        FeatureDefinition(
            name="home_corners_avg",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL",),
        ),
        FeatureDefinition(
            name="away_corners_avg",
            source_fields=("corners_away",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL",),
        ),
        FeatureDefinition(
            name="home_dangerous_attacks_avg",
            source_fields=("dangerous_attacks_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL", "GOALS_TOTAL"),
        ),
        FeatureDefinition(
            name="away_dangerous_attacks_avg",
            source_fields=("dangerous_attacks_away",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL", "GOALS_TOTAL"),
        ),
        FeatureDefinition(
            name="home_possession_avg",
            source_fields=("possession_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
        ),
    ]
    reg.register_many(features)
    return reg


@pytest.fixture
def feature_values():
    """Synthetic feature values for 100 matches."""
    rng = np.random.default_rng(42)
    values = []
    features = list(registry_fixture_features())
    for _ in range(100):
        fv = {}
        for feat in features:
            fv[feat.feature_id] = float(rng.uniform(2, 12))
        values.append(fv)
    return values


def registry_fixture_features():
    """Generate the same features as the registry fixture."""
    return [
        FeatureDefinition(
            name="home_corners_avg",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL",),
        ),
        FeatureDefinition(
            name="away_corners_avg",
            source_fields=("corners_away",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL",),
        ),
        FeatureDefinition(
            name="home_dangerous_attacks_avg",
            source_fields=("dangerous_attacks_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL", "GOALS_TOTAL"),
        ),
        FeatureDefinition(
            name="away_dangerous_attacks_avg",
            source_fields=("dangerous_attacks_away",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
            market_applicability=("CORNERS_TOTAL", "GOALS_TOTAL"),
        ),
        FeatureDefinition(
            name="home_possession_avg",
            source_fields=("possession_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5},
            temporal_class=TemporalClass.DERIVED,
        ),
    ]


@pytest.fixture
def feature_values_from_registry(registry):
    """Generate feature values matching the registry."""
    rng = np.random.default_rng(42)
    features = registry.all_features()
    values = []
    for _ in range(100):
        fv = {}
        for feat in features:
            fv[feat.feature_id] = float(rng.uniform(2, 12))
        values.append(fv)
    return values


# ═══════════════════════════════════════════════════════════════
# CANDIDATE IDENTITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestCandidateIdentity:
    """Tests for deterministic candidate hashing."""

    def test_same_candidate_same_hash(self):
        c1 = ResearchCandidate(
            candidate_id="test_1",
            market_type="CORNERS_TOTAL",
            feature_ids=("feat_a", "feat_b"),
            conditions=(
                CandidateCondition("feat_a", ">", 5.0),
                CandidateCondition("feat_b", "<", 3.0),
            ),
            operator_type=CandidateOperator.INTERACTION_AND,
            direction="OVER",
        )
        c2 = ResearchCandidate(
            candidate_id="test_2",  # Different ID
            market_type="CORNERS_TOTAL",
            feature_ids=("feat_a", "feat_b"),
            conditions=(
                CandidateCondition("feat_a", ">", 5.0),
                CandidateCondition("feat_b", "<", 3.0),
            ),
            operator_type=CandidateOperator.INTERACTION_AND,
            direction="OVER",
        )
        assert c1.content_hash == c2.content_hash

    def test_different_threshold_different_hash(self):
        c1 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_a",),
            conditions=(CandidateCondition("feat_a", ">", 5.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        c2 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_a",),
            conditions=(CandidateCondition("feat_a", ">", 6.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        assert c1.content_hash != c2.content_hash

    def test_different_direction_different_hash(self):
        c1 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_a",),
            conditions=(CandidateCondition("feat_a", ">", 5.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        c2 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_a",),
            conditions=(CandidateCondition("feat_a", ">", 5.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="UNDER",
        )
        assert c1.content_hash != c2.content_hash

    def test_different_market_different_hash(self):
        c1 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_a",),
            conditions=(CandidateCondition("feat_a", ">", 5.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        c2 = ResearchCandidate(
            candidate_id="a", market_type="GOALS_TOTAL",
            feature_ids=("feat_a",),
            conditions=(CandidateCondition("feat_a", ">", 5.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        assert c1.content_hash != c2.content_hash

    def test_reordered_features_same_hash(self):
        """Feature IDs are sorted in hash — order doesn't matter."""
        c1 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_a", "feat_b"),
            conditions=(
                CandidateCondition("feat_a", ">", 5.0),
                CandidateCondition("feat_b", ">", 3.0),
            ),
            operator_type=CandidateOperator.INTERACTION_AND, direction="OVER",
        )
        c2 = ResearchCandidate(
            candidate_id="a", market_type="CORNERS_TOTAL",
            feature_ids=("feat_b", "feat_a"),  # Reordered
            conditions=(
                CandidateCondition("feat_b", ">", 3.0),  # Reordered
                CandidateCondition("feat_a", ">", 5.0),
            ),
            operator_type=CandidateOperator.INTERACTION_AND, direction="OVER",
        )
        assert c1.content_hash == c2.content_hash

    def test_hash_length(self):
        c = ResearchCandidate(
            candidate_id="a", market_type="X",
            feature_ids=("f",), conditions=(),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        assert len(c.content_hash) == 16

    def test_created_at_does_not_affect_hash(self):
        c1 = ResearchCandidate(
            candidate_id="a", market_type="X",
            feature_ids=("f",),
            conditions=(CandidateCondition("f", ">", 1.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
            created_at="2024-01-01",
        )
        c2 = ResearchCandidate(
            candidate_id="a", market_type="X",
            feature_ids=("f",),
            conditions=(CandidateCondition("f", ">", 1.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
            created_at="2025-06-15",
        )
        assert c1.content_hash == c2.content_hash


# ═══════════════════════════════════════════════════════════════
# OPERATOR TESTS
# ═══════════════════════════════════════════════════════════════


class TestCandidateCondition:
    """Tests for CandidateCondition evaluation."""

    def test_gt_true(self):
        cond = CandidateCondition("f", ">", 5.0)
        assert cond.evaluate(6.0) is True

    def test_gt_false(self):
        cond = CandidateCondition("f", ">", 5.0)
        assert cond.evaluate(4.0) is False

    def test_lt_true(self):
        cond = CandidateCondition("f", "<", 5.0)
        assert cond.evaluate(3.0) is True

    def test_gte_boundary(self):
        cond = CandidateCondition("f", ">=", 5.0)
        assert cond.evaluate(5.0) is True

    def test_lte_boundary(self):
        cond = CandidateCondition("f", "<=", 5.0)
        assert cond.evaluate(5.0) is True

    def test_missing_data_returns_none(self):
        cond = CandidateCondition("f", ">", 5.0)
        assert cond.evaluate(None) is None

    def test_division_by_zero_safe(self):
        """Conditions don't divide — they compare. But None is safe."""
        cond = CandidateCondition("f", ">", 0.0)
        assert cond.evaluate(0.0) is False


# ═══════════════════════════════════════════════════════════════
# BUDGET TESTS
# ═══════════════════════════════════════════════════════════════


class TestDiscoveryBudget:
    """Tests for budget controls."""

    def test_valid_budget(self):
        budget = DiscoveryBudget(max_candidates=100, min_observations=20)
        assert budget.max_candidates == 100

    def test_invalid_max_candidates(self):
        with pytest.raises(ValueError):
            DiscoveryBudget(max_candidates=0)

    def test_invalid_interaction_depth(self):
        with pytest.raises(ValueError):
            DiscoveryBudget(max_interaction_depth=0)

    def test_invalid_min_observations(self):
        with pytest.raises(ValueError):
            DiscoveryBudget(min_observations=0)

    def test_invalid_correlation_threshold(self):
        with pytest.raises(ValueError):
            DiscoveryBudget(correlation_threshold=0.0)
        with pytest.raises(ValueError):
            DiscoveryBudget(correlation_threshold=1.5)

    def test_max_candidates_enforced(self, registry, feature_values_from_registry):
        budget = DiscoveryBudget(max_candidates=10)
        engine = CandidateDiscoveryEngine(registry, budget=budget)
        candidates, report = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert len(candidates) <= 10

    def test_budget_exhausted_reported(self, registry, feature_values_from_registry):
        budget = DiscoveryBudget(max_candidates=5)
        engine = CandidateDiscoveryEngine(registry, budget=budget)
        _, report = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert report.budget_exhausted


# ═══════════════════════════════════════════════════════════════
# DEDUPLICATION TESTS
# ═══════════════════════════════════════════════════════════════


class TestDeduplication:
    """Tests for candidate deduplication."""

    def test_exact_duplicates_removed(self, registry, feature_values_from_registry):
        engine = CandidateDiscoveryEngine(registry)
        candidates, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        hashes = [c.content_hash for c in candidates]
        assert len(hashes) == len(set(hashes))  # No duplicates

    def test_different_parameters_not_deduplicated(self):
        """Different thresholds are distinct candidates."""
        c1 = ResearchCandidate(
            candidate_id="a", market_type="X", feature_ids=("f",),
            conditions=(CandidateCondition("f", ">", 5.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        c2 = ResearchCandidate(
            candidate_id="b", market_type="X", feature_ids=("f",),
            conditions=(CandidateCondition("f", ">", 7.0),),
            operator_type=CandidateOperator.THRESHOLD_GT, direction="OVER",
        )
        assert c1.content_hash != c2.content_hash


# ═══════════════════════════════════════════════════════════════
# SAMPLE SIZE TESTS
# ═══════════════════════════════════════════════════════════════


class TestSampleSizeFiltering:
    """Tests for insufficient data rejection."""

    def test_insufficient_data_rejected(self, registry):
        """With very few matches, candidates should be filtered out."""
        budget = DiscoveryBudget(min_observations=100)
        engine = CandidateDiscoveryEngine(registry, budget=budget)
        # Only 10 matches — below min_observations
        rng = np.random.default_rng(42)
        small_values = []
        for _ in range(10):
            fv = {}
            for feat in registry.all_features():
                fv[feat.feature_id] = float(rng.uniform(2, 12))
            small_values.append(fv)

        candidates, report = engine.discover("CORNERS_TOTAL", small_values)
        assert len(candidates) == 0
        assert report.final_count == 0

    def test_sufficient_data_accepted(self, registry, feature_values_from_registry):
        budget = DiscoveryBudget(min_observations=50)
        engine = CandidateDiscoveryEngine(registry, budget=budget)
        candidates, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert len(candidates) > 0


# ═══════════════════════════════════════════════════════════════
# MARKET COMPATIBILITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestMarketCompatibility:
    """Tests for market-aware candidate generation."""

    def test_market_specific_features_used(self, registry, feature_values_from_registry):
        engine = CandidateDiscoveryEngine(registry)
        candidates, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        # Should have candidates (features marked for CORNERS_TOTAL)
        assert len(candidates) > 0

    def test_different_markets_different_candidates(self, registry, feature_values_from_registry):
        engine = CandidateDiscoveryEngine(registry)
        corners_cands, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        goals_cands, _ = engine.discover("GOALS_TOTAL", feature_values_from_registry)
        # Hash sets should differ (different markets in hash)
        corners_hashes = {c.content_hash for c in corners_cands}
        goals_hashes = {c.content_hash for c in goals_cands}
        # Some may overlap (features applicable to both), but market changes hash
        assert corners_hashes != goals_hashes


# ═══════════════════════════════════════════════════════════════
# DETERMINISM TESTS
# ═══════════════════════════════════════════════════════════════


class TestDeterminism:
    """Tests proving deterministic generation."""

    def test_same_seed_same_candidates(self, registry, feature_values_from_registry):
        engine1 = CandidateDiscoveryEngine(registry, seed=42)
        engine2 = CandidateDiscoveryEngine(registry, seed=42)
        c1, _ = engine1.discover("CORNERS_TOTAL", feature_values_from_registry)
        c2, _ = engine2.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert len(c1) == len(c2)
        assert [c.content_hash for c in c1] == [c.content_hash for c in c2]

    def test_same_data_same_hashes(self, registry, feature_values_from_registry):
        engine = CandidateDiscoveryEngine(registry, seed=42)
        c1, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        c2, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert [c.content_hash for c in c1] == [c.content_hash for c in c2]


# ═══════════════════════════════════════════════════════════════
# FEATURE FAMILY TESTS
# ═══════════════════════════════════════════════════════════════


class TestFeatureFamilies:
    """Tests for feature family system."""

    def test_auto_detection_corners(self):
        fr = FeatureFamilyRegistry()
        feat = FeatureDefinition(
            name="home_corners_avg",
            source_fields=("corners_home",),
            transform=TransformType.ROLLING_MEAN,
        )
        assert fr.get_family(feat) == FeatureFamily.CORNERS

    def test_auto_detection_attacks(self):
        fr = FeatureFamilyRegistry()
        feat = FeatureDefinition(
            name="dangerous_attacks_home_avg",
            source_fields=("dangerous_attacks_home",),
            transform=TransformType.ROLLING_MEAN,
        )
        assert fr.get_family(feat) == FeatureFamily.ATTACKING

    def test_auto_detection_xmetrics(self):
        fr = FeatureFamilyRegistry()
        feat = FeatureDefinition(
            name="home_xC_avg",
            source_fields=("home_xC",),
            transform=TransformType.ROLLING_MEAN,
        )
        assert fr.get_family(feat) == FeatureFamily.XMETRICS

    def test_explicit_assignment_overrides(self):
        fr = FeatureFamilyRegistry()
        feat = FeatureDefinition(
            name="custom_feature",
            source_fields=("random_field",),
            transform=TransformType.RAW,
        )
        # Default: GENERAL
        assert fr.get_family(feat) == FeatureFamily.GENERAL
        # Override
        fr.assign(feat.feature_id, FeatureFamily.TEMPO)
        assert fr.get_family(feat) == FeatureFamily.TEMPO

    def test_market_priority_families(self):
        fr = FeatureFamilyRegistry()
        corners_families = fr.get_market_families("CORNERS_TOTAL")
        assert FeatureFamily.CORNERS in corners_families
        assert FeatureFamily.ATTACKING in corners_families

    def test_custom_market_priority(self):
        fr = FeatureFamilyRegistry()
        fr.set_market_priority("CUSTOM_MARKET", [FeatureFamily.FORM])
        assert fr.get_market_families("CUSTOM_MARKET") == [FeatureFamily.FORM]


# ═══════════════════════════════════════════════════════════════
# PARAMETER SPACE TESTS
# ═══════════════════════════════════════════════════════════════


class TestParameterSpace:
    """Tests for parameter space definitions."""

    def test_range_values(self):
        r = ParameterRange(name="window", start=3, stop=10, step=1)
        assert r.values == [3, 4, 5, 6, 7, 8, 9, 10]
        assert r.count == 8

    def test_range_float_step(self):
        r = ParameterRange(name="threshold", start=0.5, stop=1.0, step=0.25)
        assert len(r.values) == 3  # 0.5, 0.75, 1.0

    def test_range_invalid_step(self):
        with pytest.raises(ValueError):
            ParameterRange(name="x", start=0, stop=10, step=0)

    def test_range_invalid_bounds(self):
        with pytest.raises(ValueError):
            ParameterRange(name="x", start=10, stop=5, step=1)

    def test_set_values(self):
        s = ParameterSet(name="quantile", values=(0.25, 0.50, 0.75))
        assert s.count == 3

    def test_grid_total_combinations(self):
        grid = ParameterGrid(dimensions=(
            ParameterSet(name="window", values=(3, 5, 10)),
            ParameterSet(name="quantile", values=(0.25, 0.75)),
        ))
        assert grid.total_combinations == 6

    def test_grid_iteration(self):
        grid = ParameterGrid(dimensions=(
            ParameterSet(name="a", values=(1, 2)),
            ParameterSet(name="b", values=(10, 20)),
        ))
        combos = list(grid.iterate())
        assert len(combos) == 4
        assert {"a": 1, "b": 10} in combos
        assert {"a": 2, "b": 20} in combos

    def test_grid_budget_enforced(self):
        grid = ParameterGrid(
            dimensions=(
                ParameterRange(name="x", start=0, stop=100, step=1),
                ParameterRange(name="y", start=0, stop=100, step=1),
            ),
            max_combinations=50,
        )
        assert not grid.is_within_budget
        combos = list(grid.iterate())
        assert len(combos) == 50

    def test_grid_content_hash_deterministic(self):
        grid = ParameterGrid(dimensions=(
            ParameterSet(name="w", values=(3, 5)),
        ))
        h1 = grid.content_hash()
        h2 = grid.content_hash()
        assert h1 == h2

    def test_default_rolling_params(self):
        p = rolling_window_params()
        assert p.name == "window"
        assert 5 in p.values

    def test_default_quantile_params(self):
        p = threshold_quantile_params()
        assert 0.50 in p.values


# ═══════════════════════════════════════════════════════════════
# CORRELATION FILTERING TESTS
# ═══════════════════════════════════════════════════════════════


class TestCorrelationFiltering:
    """Tests for optional redundancy filtering."""

    def test_disabled_by_default(self, registry, feature_values_from_registry):
        budget = DiscoveryBudget(correlation_threshold=None)
        engine = CandidateDiscoveryEngine(registry, budget=budget)
        cands, report = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        # Without filtering, dedup = redundancy filtered count
        assert report.total_after_dedup == report.total_after_redundancy

    def test_enabled_reduces_candidates(self, registry, feature_values_from_registry):
        budget_no_filter = DiscoveryBudget(correlation_threshold=None)
        budget_filter = DiscoveryBudget(correlation_threshold=0.9)

        engine1 = CandidateDiscoveryEngine(registry, budget=budget_no_filter, seed=42)
        engine2 = CandidateDiscoveryEngine(registry, budget=budget_filter, seed=42)

        c1, _ = engine1.discover("CORNERS_TOTAL", feature_values_from_registry)
        c2, _ = engine2.discover("CORNERS_TOTAL", feature_values_from_registry)

        # Filtering should reduce or maintain count
        assert len(c2) <= len(c1)


# ═══════════════════════════════════════════════════════════════
# GENERATION REPORT TESTS
# ═══════════════════════════════════════════════════════════════


class TestGenerationReport:
    """Tests for generation report."""

    def test_report_has_all_fields(self, registry, feature_values_from_registry):
        engine = CandidateDiscoveryEngine(registry)
        _, report = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert report.total_generated >= 0
        assert report.total_after_dedup >= 0
        assert report.total_after_redundancy >= 0
        assert report.total_after_sample_filter >= 0
        assert report.final_count >= 0
        assert report.generation_time_ms >= 0

    def test_counts_decrease_through_pipeline(self, registry, feature_values_from_registry):
        engine = CandidateDiscoveryEngine(registry)
        _, report = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        assert report.total_generated >= report.total_after_dedup
        assert report.total_after_dedup >= report.total_after_redundancy
        assert report.total_after_redundancy >= report.total_after_sample_filter
        assert report.total_after_sample_filter >= report.final_count


# ═══════════════════════════════════════════════════════════════
# PERFORMANCE BENCHMARK
# ═══════════════════════════════════════════════════════════════


class TestPerformanceBenchmark:
    """Performance benchmark for bounded candidate generation."""

    def test_100_features_bounded_generation(self):
        """Generate candidates from 100 features within budget."""
        rng = np.random.default_rng(42)

        # Create registry with 100 features
        reg = FeatureRegistry()
        for i in range(100):
            feat = FeatureDefinition(
                name=f"feature_{i}",
                source_fields=(f"field_{i}",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5},
                temporal_class=TemporalClass.DERIVED,
                market_applicability=("CORNERS_TOTAL",),
            )
            reg.register(feat)

        # Generate feature values for 200 matches
        features = reg.all_features()
        values = []
        for _ in range(200):
            fv = {f.feature_id: float(rng.uniform(0, 20)) for f in features}
            values.append(fv)

        # Run with budget
        budget = DiscoveryBudget(max_candidates=200, max_candidates_per_market=200)
        engine = CandidateDiscoveryEngine(reg, budget=budget, seed=42)

        start = time.time()
        candidates, report = engine.discover("CORNERS_TOTAL", values)
        elapsed = time.time() - start

        # Assertions
        assert len(candidates) <= 200  # Budget respected
        assert report.final_count == len(candidates)
        assert elapsed < 10.0  # Should complete in < 10 seconds
        assert report.generation_time_ms < 10000

        # Determinism check
        engine2 = CandidateDiscoveryEngine(reg, budget=budget, seed=42)
        candidates2, _ = engine2.discover("CORNERS_TOTAL", values)
        assert [c.content_hash for c in candidates] == [c.content_hash for c in candidates2]


# ═══════════════════════════════════════════════════════════════
# TEMPORAL CAUSALITY TESTS
# ═══════════════════════════════════════════════════════════════


class TestTemporalCausality:
    """Tests proving candidate generation preserves temporal integrity."""

    def test_candidates_use_derived_features_only(self, registry, feature_values_from_registry):
        """All features in candidates should be DERIVED (from historical data)."""
        engine = CandidateDiscoveryEngine(registry)
        candidates, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        for c in candidates:
            for fid in c.feature_ids:
                feat = registry.get(fid)
                if feat is not None:
                    # Must be DERIVED or PRE_MATCH (never raw POST_MATCH)
                    assert feat.temporal_class in (
                        TemporalClass.DERIVED, TemporalClass.PRE_MATCH
                    ), f"Feature {fid} has temporal_class {feat.temporal_class}"

    def test_candidate_preserves_required_observations(self, registry, feature_values_from_registry):
        """Every candidate states its minimum data requirement."""
        engine = CandidateDiscoveryEngine(registry)
        candidates, _ = engine.discover("CORNERS_TOTAL", feature_values_from_registry)
        for c in candidates:
            assert c.required_observations >= engine.budget.min_observations
