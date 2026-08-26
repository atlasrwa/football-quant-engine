"""Tests for candidate generator and hypothesis creation."""

import pytest

from src.research.candidate_generator import (
    CandidateGenerator,
    GenerationMethod,
    ResearchHypothesis,
    SearchBudget,
)
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    TransformType,
)
from src.research.market import CORNERS_OVER_UNDER, MarketType


class TestResearchHypothesis:
    """Tests for ResearchHypothesis."""

    def test_content_hash_deterministic(self):
        h1 = ResearchHypothesis(
            hypothesis_id="test1",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        h2 = ResearchHypothesis(
            hypothesis_id="test2",  # Different ID but same content
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.HUMAN,  # Method doesn't affect hash
        )
        assert h1.content_hash == h2.content_hash

    def test_content_hash_changes_with_conditions(self):
        h1 = ResearchHypothesis(
            hypothesis_id="test1",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        h2 = ResearchHypothesis(
            hypothesis_id="test2",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 6.0),),  # Different threshold
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        assert h1.content_hash != h2.content_hash

    def test_content_hash_changes_with_direction(self):
        h1 = ResearchHypothesis(
            hypothesis_id="test1",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        h2 = ResearchHypothesis(
            hypothesis_id="test2",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="UNDER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        assert h1.content_hash != h2.content_hash

    def test_generation_methods(self):
        assert GenerationMethod.DETERMINISTIC.value == "DETERMINISTIC"
        assert GenerationMethod.HUMAN.value == "HUMAN"
        assert GenerationMethod.LLM.value == "LLM"


class TestSearchBudget:
    """Tests for SearchBudget constraints."""

    def test_defaults(self):
        budget = SearchBudget()
        assert budget.max_features_per_hypothesis == 3
        assert budget.max_interaction_depth == 2
        assert budget.min_sample_size == 50
        assert budget.max_candidates == 500

    def test_custom_budget(self):
        budget = SearchBudget(max_candidates=100, min_sample_size=30)
        assert budget.max_candidates == 100
        assert budget.min_sample_size == 30


class TestCandidateGenerator:
    """Tests for CandidateGenerator."""

    @pytest.fixture
    def registry(self):
        reg = FeatureRegistry()
        # Register some test features
        features = [
            FeatureDefinition(
                name="corners_avg_5",
                source_fields=("corners_home",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5},
                market_applicability=("CORNERS_TOTAL",),
            ),
            FeatureDefinition(
                name="danger_avg_5",
                source_fields=("dangerous_attacks_home",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5},
                market_applicability=("CORNERS_TOTAL",),
            ),
            FeatureDefinition(
                name="poss_diff",
                source_fields=("possession_home", "possession_away"),
                transform=TransformType.DIFFERENCE,
                market_applicability=("CORNERS_TOTAL",),
            ),
        ]
        reg.register_many(features)
        return reg

    @pytest.fixture
    def feature_values(self, registry):
        """Generate synthetic feature values for testing."""
        import numpy as np
        rng = np.random.default_rng(42)
        features = registry.all_features()
        values = []
        for _ in range(100):
            d = {}
            for f in features:
                d[f.feature_id] = float(rng.normal(5, 2))
            values.append(d)
        return values

    def test_generates_single_feature_hypotheses(self, registry, feature_values):
        gen = CandidateGenerator(registry, SearchBudget(min_sample_size=10))
        hypotheses = gen.generate_single_feature_hypotheses(CORNERS_OVER_UNDER, feature_values)
        assert len(hypotheses) > 0
        # Each hypothesis should have exactly one feature
        for h in hypotheses:
            assert len(h.feature_ids) == 1
            assert len(h.conditions) == 1

    def test_generates_pair_hypotheses(self, registry, feature_values):
        gen = CandidateGenerator(registry, SearchBudget(min_sample_size=10))
        hypotheses = gen.generate_pair_hypotheses(CORNERS_OVER_UNDER, feature_values)
        assert len(hypotheses) > 0
        # Each hypothesis should have two features
        for h in hypotheses:
            assert len(h.feature_ids) == 2
            assert len(h.conditions) == 2

    def test_respects_max_candidates(self, registry, feature_values):
        budget = SearchBudget(max_candidates=5, min_sample_size=10)
        gen = CandidateGenerator(registry, budget)
        hypotheses = gen.generate_all(CORNERS_OVER_UNDER, feature_values)
        assert len(hypotheses) <= 5

    def test_respects_min_sample_size(self):
        """Features with too few values should not generate hypotheses."""
        reg = FeatureRegistry()
        feat = FeatureDefinition(
            name="sparse", source_fields=("x",), transform=TransformType.RAW,
            market_applicability=("CORNERS_TOTAL",),
        )
        reg.register(feat)
        # Only 5 feature values but min_sample=50
        feature_values = [{feat.feature_id: float(i)} for i in range(5)]
        gen = CandidateGenerator(reg, SearchBudget(min_sample_size=50))
        hypotheses = gen.generate_single_feature_hypotheses(CORNERS_OVER_UNDER, feature_values)
        assert len(hypotheses) == 0

    def test_all_hypotheses_have_content_hash(self, registry, feature_values):
        gen = CandidateGenerator(registry, SearchBudget(min_sample_size=10))
        hypotheses = gen.generate_all(CORNERS_OVER_UNDER, feature_values)
        for h in hypotheses:
            assert h.content_hash is not None
            assert len(h.content_hash) == 16

    def test_deterministic_generation(self, registry, feature_values):
        """Same seed should produce same candidates."""
        gen1 = CandidateGenerator(registry, SearchBudget(min_sample_size=10), seed=42)
        gen2 = CandidateGenerator(registry, SearchBudget(min_sample_size=10), seed=42)
        h1 = gen1.generate_all(CORNERS_OVER_UNDER, feature_values)
        h2 = gen2.generate_all(CORNERS_OVER_UNDER, feature_values)
        assert len(h1) == len(h2)
        for a, b in zip(h1, h2):
            assert a.content_hash == b.content_hash

    def test_generation_method_is_deterministic(self, registry, feature_values):
        gen = CandidateGenerator(registry, SearchBudget(min_sample_size=10))
        hypotheses = gen.generate_all(CORNERS_OVER_UNDER, feature_values)
        for h in hypotheses:
            assert h.generation_method == GenerationMethod.DETERMINISTIC

    def test_both_directions_generated(self, registry, feature_values):
        gen = CandidateGenerator(registry, SearchBudget(min_sample_size=10))
        hypotheses = gen.generate_single_feature_hypotheses(CORNERS_OVER_UNDER, feature_values)
        directions = {h.direction for h in hypotheses}
        assert "OVER" in directions
        assert "UNDER" in directions
