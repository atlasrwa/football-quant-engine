"""Integration tests for canonical content hashing.

Proves:
- same input → same hash
- different input → different hash
- different insertion order → same hash
- semantic change → different hash
- compatibility with domain object methods
"""

import pytest

from src.persistence.hashing import (
    compute_dataset_content_hash,
    compute_feature_version_hash,
    compute_model_version_hash,
    compute_backtest_run_hash,
)
from src.domain.provenance import DatasetVersion, FeatureVersion, ModelVersion
from src.domain.backtest_run import BacktestRun


class TestDatasetHashing:
    def test_deterministic(self):
        ids = [5, 3, 1, 4, 2]
        h1 = compute_dataset_content_hash(ids)
        h2 = compute_dataset_content_hash(ids)
        assert h1 == h2

    def test_order_independent(self):
        h1 = compute_dataset_content_hash([1, 2, 3])
        h2 = compute_dataset_content_hash([3, 1, 2])
        assert h1 == h2  # Sorted internally

    def test_different_ids_differ(self):
        h1 = compute_dataset_content_hash([1, 2, 3])
        h2 = compute_dataset_content_hash([1, 2, 4])
        assert h1 != h2

    def test_matches_domain_object(self):
        ids = [10, 20, 30, 40]
        assert compute_dataset_content_hash(ids) == DatasetVersion.compute_content_hash(ids)

    def test_is_sha256(self):
        h = compute_dataset_content_hash([1])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestFeatureVersionHashing:
    def test_deterministic(self):
        h1 = compute_feature_version_hash("ds-1", 5, 6, 5, None)
        h2 = compute_feature_version_hash("ds-1", 5, 6, 5, None)
        assert h1 == h2

    def test_config_change_differs(self):
        h1 = compute_feature_version_hash("ds-1", 5, 6, 5, None)
        h2 = compute_feature_version_hash("ds-1", 10, 6, 5, None)
        assert h1 != h2

    def test_dataset_change_differs(self):
        h1 = compute_feature_version_hash("ds-1", 5, 6, 5, None)
        h2 = compute_feature_version_hash("ds-2", 5, 6, 5, None)
        assert h1 != h2

    def test_xmetric_coefficients_included(self):
        h1 = compute_feature_version_hash("ds-1", 5, 6, 5, None)
        h2 = compute_feature_version_hash("ds-1", 5, 6, 5, {"xc_alpha": 0.5})
        assert h1 != h2

    def test_matches_domain_object(self):
        h = compute_feature_version_hash("ds-abc", 5, 6, 5, {"k": 0.1})
        assert h == FeatureVersion.compute_content_hash("ds-abc", 5, 6, 5, {"k": 0.1})


class TestModelVersionHashing:
    def test_deterministic(self):
        h1 = compute_model_version_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = compute_model_version_hash("abc", "fv-1", 200, 50, 50, 1.5, 5.0)
        assert h1 == h2

    def test_strategy_change_differs(self):
        h1 = compute_model_version_hash("hash_a", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = compute_model_version_hash("hash_b", "fv-1", 200, 50, 50, 1.5, 5.0)
        assert h1 != h2

    def test_window_change_differs(self):
        h1 = compute_model_version_hash("h", "fv-1", 200, 50, 50, 1.5, 5.0)
        h2 = compute_model_version_hash("h", "fv-1", 100, 50, 50, 1.5, 5.0)
        assert h1 != h2

    def test_matches_domain_object(self):
        h = compute_model_version_hash("x" * 64, "fv-id", 200, 50, 50, 1.5, 5.0)
        assert h == ModelVersion.compute_content_hash("x" * 64, "fv-id", 200, 50, 50, 1.5, 5.0)


class TestBacktestRunHashing:
    def test_deterministic(self):
        h1 = compute_backtest_run_hash("mv-1", "ds-1")
        h2 = compute_backtest_run_hash("mv-1", "ds-1")
        assert h1 == h2

    def test_different_inputs_differ(self):
        h1 = compute_backtest_run_hash("mv-1", "ds-1")
        h2 = compute_backtest_run_hash("mv-1", "ds-2")
        assert h1 != h2

    def test_matches_domain_object(self):
        h = compute_backtest_run_hash("mv-abc", "ds-xyz")
        assert h == BacktestRun.compute_content_hash("mv-abc", "ds-xyz")
