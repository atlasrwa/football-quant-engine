# Feature: asymmetric-matchup-engine, Property 10: Elastic-net shrinks coefficients and retains correlated features
"""Property 10: Elastic-net regularization behaviour (task 4.5).

**Property 10: Elastic-net regularization shrinks coefficients and retains
correlated features** — increasing the penalty strength ``lambda`` gives a
non-increasing L2 norm of the fitted coefficient vector; and two strongly
correlated informative features BOTH retain non-zero weight (they are not
arbitrarily zeroed as pure L1 would do).

Validates: Requirements 5.4, 5.5.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test on a fixed synthetic
dataset with two strongly correlated informative features, sweeping ``lambda``.
When task 12.1 lands, convert to ``@given(...)`` drawing lambda ladders and
correlation strengths with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

import math

import numpy as np

from src.research.asymmetric.directional_model import DirectionalCountModel
from src.research.models.count_regression import DistributionType


def _make_dataset(seed: int = 0, n: int = 600):
    """Two strongly correlated informative features driving a Poisson count."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, size=n)
    # x1 and x2 are strongly correlated (corr ~0.98) and both informative.
    x1 = z + rng.normal(0, 0.2, size=n)
    x2 = z + rng.normal(0, 0.2, size=n)
    log_lambda = 0.7 + 0.5 * x1 + 0.5 * x2
    lam = np.exp(np.clip(log_lambda, -3, 3))
    counts = rng.poisson(lam)
    rows = [
        {"x1": float(a), "x2": float(b), "count": int(c)}
        for a, b, c in zip(x1, x2, counts)
    ]
    return rows


def _l2_norm(weights: dict[str, float]) -> float:
    return math.sqrt(sum(w * w for w in weights.values()))


def test_increasing_lambda_gives_non_increasing_l2_norm():
    rows = _make_dataset(seed=1)
    lambdas = [0.001, 0.05, 0.5, 2.0, 10.0]
    norms = []
    for lam in lambdas:
        model = DirectionalCountModel(
            target_field="count",
            distribution=DistributionType.POISSON,
            lam=lam,
            alpha_mix=0.5,
        )
        model.fit(rows)
        norms.append(_l2_norm(model.feature_weights))

    # Non-increasing (allow a tiny numerical slack per step).
    for earlier, later in zip(norms, norms[1:]):
        assert later <= earlier + 1e-6, f"L2 norm increased with lambda: {norms}"
    # Strongest penalty should shrink well below the weakest.
    assert norms[-1] < norms[0]


def test_correlated_informative_features_both_retain_weight():
    rows = _make_dataset(seed=2)
    model = DirectionalCountModel(
        target_field="count",
        distribution=DistributionType.POISSON,
        lam=0.05,
        alpha_mix=0.5,
    )
    model.fit(rows)
    w = model.feature_weights
    # Elastic-net keeps BOTH correlated features non-zero (pure L1 would tend to
    # zero one of them out arbitrarily).
    assert abs(w["x1"]) > 1e-3, w
    assert abs(w["x2"]) > 1e-3, w
    # Both should carry the same sign as the true positive effect.
    assert w["x1"] > 0 and w["x2"] > 0, w


def test_alpha_mix_must_stay_below_one():
    """Constructor rejects pure L1 (alpha_mix == 1) to preserve elastic-net."""
    import pytest

    with pytest.raises(ValueError):
        DirectionalCountModel(alpha_mix=1.0)
