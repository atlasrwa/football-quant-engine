# Feature: asymmetric-matchup-engine, Property 4: Valid predictive distributions
"""Property 4: Valid predictive distributions (task 4.6).

**Property 4: Valid predictive distributions** — ``predict_distribution``
returns a valid PMF: every entry lies in ``[0, 1]`` and the entries sum to 1
within tolerance, across corners / goals / SOT / cards-style count targets and
both the Poisson and negative-binomial paths.

Validates: Requirements 2.4, 2.5, 2.6, 2.7.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test over several fitted
models and feature rows. When task 12.1 lands, convert to ``@given(...)``
drawing count samples and feature rows with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.research.asymmetric.directional_model import DirectionalCountModel
from src.research.models.count_regression import DistributionType


def _fit(counts, feat_a, feat_b, distribution):
    rows = [
        {"x_att": float(a), "x_def": float(b), "count": int(c)}
        for a, b, c in zip(counts, feat_a, feat_b)
    ]
    model = DirectionalCountModel(target_field="count", distribution=distribution)
    model.fit(rows)
    return model


def _assert_valid_pmf(pmf, max_k):
    assert len(pmf) == max_k + 1
    for p in pmf:
        assert 0.0 <= p <= 1.0, f"pmf entry out of [0,1]: {p}"
    assert abs(sum(pmf) - 1.0) < 1e-9, f"pmf sums to {sum(pmf)}"


@pytest.mark.parametrize("distribution", [DistributionType.POISSON, DistributionType.NEGATIVE_BINOMIAL])
@pytest.mark.parametrize("mean_count", [1.5, 4.0, 9.0])  # SOT / goals, cards, corners-ish
def test_predict_distribution_is_valid_pmf(distribution, mean_count):
    rng = np.random.default_rng(int(mean_count * 10) + (1 if "poisson" in distribution else 2))
    n = 400
    if distribution == DistributionType.NEGATIVE_BINOMIAL:
        # Overdispersed sample around the requested mean.
        counts = rng.negative_binomial(3, 3.0 / (3.0 + mean_count), size=n)
    else:
        counts = rng.poisson(mean_count, size=n)
    feat_a = rng.normal(0, 1, size=n)
    feat_b = rng.normal(0, 1, size=n)

    model = _fit(counts, feat_a, feat_b, distribution)

    for row in ({"x_att": 0.0, "x_def": 0.0},
                {"x_att": 1.5, "x_def": -0.7},
                {"x_att": -2.0, "x_def": 2.0}):
        for max_k in (10, 20, 40):
            _assert_valid_pmf(model.predict_distribution(row, max_k=max_k), max_k)


def test_expected_count_positive_and_finite():
    rng = np.random.default_rng(99)
    counts = rng.poisson(5.0, size=300)
    feat = rng.normal(0, 1, size=300)
    model = _fit(counts, feat, feat, DistributionType.POISSON)
    lam = model.predict_expected_count({"x_att": 0.3, "x_def": -0.4})
    assert lam > 0.0
    assert np.isfinite(lam)


def test_unfitted_model_returns_valid_pmf():
    """Even before fitting, predict_distribution returns a valid PMF."""
    model = DirectionalCountModel(target_field="count", line=2.5)
    pmf = model.predict_distribution({"x_att": 0.0}, max_k=15)
    _assert_valid_pmf(pmf, 15)
