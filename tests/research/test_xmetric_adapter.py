"""Tests for XMetric integration adapter.

Verifies that the adapter correctly bridges the existing XMetricEngine
into the research laboratory's feature system without modifying the engine.
"""

import pytest
import numpy as np

from src.engine.xmetrics import XMetricCoefficients, XMetricEngine
from src.research.data_source import ResearchMatch
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)
from src.research.synthetic_data import SyntheticResearchDataSource
from src.research.xmetric_adapter import (
    XMetricAdapter,
    XMetricProvenance,
    create_xmetric_rolling_features,
)


class TestXMetricAdapter:
    """Tests for the XMetricAdapter."""

    @pytest.fixture
    def adapter(self):
        return XMetricAdapter()

    @pytest.fixture
    def source(self):
        return SyntheticResearchDataSource(seed=42, num_seasons=1)

    def test_register_features(self, adapter):
        """Adapter registers 6 XMetric features in the registry."""
        registry = FeatureRegistry()
        ids = adapter.register_features(registry)
        assert len(ids) == 6
        assert registry.count == 6

    def test_registered_features_have_correct_markets(self, adapter):
        """Each XMetric is associated with its correct market."""
        registry = FeatureRegistry()
        adapter.register_features(registry)

        corners_feats = registry.features_for_market("CORNERS_TOTAL")
        cards_feats = registry.features_for_market("CARDS_TOTAL")
        offsides_feats = registry.features_for_market("OFFSIDES_TOTAL")

        corner_names = {f.name for f in corners_feats}
        assert "home_xC" in corner_names
        assert "away_xC" in corner_names

        card_names = {f.name for f in cards_feats}
        assert "home_xB" in card_names
        assert "away_xB" in card_names

        offside_names = {f.name for f in offsides_feats}
        assert "home_xO" in offside_names
        assert "away_xO" in offside_names

    def test_compute_from_research_matches(self, adapter, source):
        """Adapter computes XMetrics from ResearchMatch objects."""
        matches = source.get_matches()[:20]
        results = adapter.compute(matches)

        assert len(results) == 20
        # At least some results should have values
        has_values = sum(1 for r in results if len(r) > 0)
        assert has_values > 0

    def test_compute_from_dicts(self, adapter, source):
        """Adapter computes from dict representations."""
        matches = source.get_matches()[:20]
        match_dicts = [m.to_dict() for m in matches]
        results = adapter.compute_from_dicts(match_dicts)

        assert len(results) == 20
        has_values = sum(1 for r in results if len(r) > 0)
        assert has_values > 0

    def test_xC_values_non_negative(self, adapter, source):
        """xC values should be non-negative (based on formula)."""
        matches = source.get_matches()[:50]
        results = adapter.compute(matches)

        xc_features = [f for f in adapter.XMETRIC_FEATURES if "xC" in f.name]
        for r in results:
            for feat in xc_features:
                if feat.feature_id in r:
                    assert r[feat.feature_id] >= 0, f"xC should be non-negative"

    def test_xO_values_non_negative(self, adapter, source):
        """xO values should be non-negative (based on formula)."""
        matches = source.get_matches()[:50]
        results = adapter.compute(matches)

        xo_features = [f for f in adapter.XMETRIC_FEATURES if "xO" in f.name]
        for r in results:
            for feat in xo_features:
                if feat.feature_id in r:
                    assert r[feat.feature_id] >= 0, f"xO should be non-negative"

    def test_empty_input(self, adapter):
        """Empty input produces empty output."""
        assert adapter.compute([]) == []
        assert adapter.compute_from_dicts([]) == []

    def test_provenance_available(self, adapter):
        """Provenance records are accessible."""
        prov = adapter.provenance
        assert "xC" in prov
        assert "xB" in prov
        assert "xO" in prov
        assert prov["xC"].version == "1.0.0"
        assert prov["xC"].content_hash is not None
        assert len(prov["xC"].content_hash) == 16

    def test_features_have_post_match_temporal_class(self, adapter):
        """XMetric raw values are POST_MATCH (computed from match stats)."""
        for feat in adapter.XMETRIC_FEATURES:
            assert feat.temporal_class == TemporalClass.POST_MATCH

    def test_registration_is_idempotent(self, adapter):
        """Registering twice doesn't duplicate features."""
        registry = FeatureRegistry()
        ids1 = adapter.register_features(registry)
        ids2 = adapter.register_features(registry)
        assert ids1 == ids2
        assert registry.count == 6


class TestXMetricProvenance:
    """Tests for XMetric provenance tracking."""

    def test_content_hash_deterministic(self):
        prov = XMetricProvenance(
            metric_name="xC",
            version="1.0.0",
            coefficients={"alpha": 0.45, "beta": 0.30, "gamma": 0.25},
            timestamp_semantics="POST_MATCH",
            input_fields=("attacks_home",),
        )
        h1 = prov.content_hash
        h2 = prov.content_hash
        assert h1 == h2

    def test_content_hash_changes_with_version(self):
        prov1 = XMetricProvenance(
            metric_name="xC", version="1.0.0",
            coefficients={"alpha": 0.45},
            timestamp_semantics="POST_MATCH",
            input_fields=("attacks_home",),
        )
        prov2 = XMetricProvenance(
            metric_name="xC", version="2.0.0",
            coefficients={"alpha": 0.45},
            timestamp_semantics="POST_MATCH",
            input_fields=("attacks_home",),
        )
        assert prov1.content_hash != prov2.content_hash

    def test_content_hash_changes_with_coefficients(self):
        prov1 = XMetricProvenance(
            metric_name="xC", version="1.0.0",
            coefficients={"alpha": 0.45},
            timestamp_semantics="POST_MATCH",
            input_fields=("attacks_home",),
        )
        prov2 = XMetricProvenance(
            metric_name="xC", version="1.0.0",
            coefficients={"alpha": 0.50},
            timestamp_semantics="POST_MATCH",
            input_fields=("attacks_home",),
        )
        assert prov1.content_hash != prov2.content_hash


class TestXMetricRollingFeatures:
    """Tests for derived rolling XMetric features."""

    def test_creates_rolling_features(self):
        """create_xmetric_rolling_features generates correct count."""
        features = create_xmetric_rolling_features(windows=(3, 5))
        # 6 xmetric fields × 2 windows = 12 features
        assert len(features) == 12

    def test_all_are_derived_temporal_class(self):
        """Derived XMetric features are DERIVED (safe for pre-match use)."""
        features = create_xmetric_rolling_features(windows=(5,))
        for f in features:
            assert f.temporal_class == TemporalClass.DERIVED

    def test_all_are_rolling_mean(self):
        features = create_xmetric_rolling_features(windows=(5,))
        for f in features:
            assert f.transform == TransformType.ROLLING_MEAN

    def test_correct_market_applicability(self):
        features = create_xmetric_rolling_features(windows=(5,))
        for f in features:
            if "xC" in f.name:
                assert "CORNERS_TOTAL" in f.market_applicability
            elif "xB" in f.name:
                assert "CARDS_TOTAL" in f.market_applicability
            elif "xO" in f.name:
                assert "OFFSIDES_TOTAL" in f.market_applicability

    def test_register_in_registry(self):
        """Rolling features can be registered alongside raw XMetrics."""
        registry = FeatureRegistry()
        adapter = XMetricAdapter()
        adapter.register_features(registry)

        rolling = create_xmetric_rolling_features(windows=(3, 5))
        registry.register_many(rolling)

        # 6 raw + 12 rolling = 18
        assert registry.count == 18


class TestXMetricCoexistence:
    """Test that XMetrics coexist with research-discovered features."""

    def test_xmetric_and_research_features_in_same_registry(self):
        """XMetric features and dynamically discovered features coexist."""
        registry = FeatureRegistry()

        # Register XMetrics
        adapter = XMetricAdapter()
        adapter.register_features(registry)

        # Register research-discovered features
        discovered = FeatureDefinition(
            name="discovered_corner_signal",
            source_fields=("dangerous_attacks_home", "corners_home"),
            transform=TransformType.INTERACTION,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("CORNERS_TOTAL",),
            description="Hypothetical discovered interaction feature",
        )
        registry.register(discovered)

        # All should coexist
        assert registry.count == 7  # 6 xmetrics + 1 discovered
        corners = registry.features_for_market("CORNERS_TOTAL")
        corner_names = {f.name for f in corners}
        assert "home_xC" in corner_names
        assert "away_xC" in corner_names
        assert "discovered_corner_signal" in corner_names
