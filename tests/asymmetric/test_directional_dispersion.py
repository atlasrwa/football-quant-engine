# Feature: asymmetric-matchup-engine, Property 9: Dispersion-driven distribution selection
"""Property 9: Dispersion-driven distribution selection (task 4.4).

**Property 9: Dispersion-driven distribution selection** — the model selects the
negative-binomial distribution when the empirical variance/mean ratio of the
count target exceeds the overdispersion threshold, and Poisson otherwise; the
empirical dispersion ratio is reported after fitting.

Validates: Requirements 5.3.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test that constructs an
overdispersed count sample and an (approximately) equidispersed count sample and
checks the selection + reported ratio. When task 12.1 lands, convert to
``@given(...)`` drawing count samples of varying dispersion with
``@settings(max_examples=100)``.
"""

from __future__ import annotations

import numpy as np

from src.research.asymmetric.directional_model import DirectionalCountModel
from src.research.models.count_regression import DistributionType


def _rows(counts, feat_a, feat_b, target="count"):
    """Build fittable rows: one continuous feature plus the count target."""
    rows = []
    for c, a, b in zip(counts, feat_a, feat_b):
        rows.append({"x_att": float(a), "x_def": float(b), target: int(c)})
    return rows


def test_negative_binomial_selected_for_overdispersed_counts():
    rng = np.random.default_rng(7)
    n = 400
    # Negative-binomial counts: variance >> mean (overdispersed).
    # numpy nbinom(n=r, p) has mean r(1-p)/p; choose params giving var/mean > 1.2.
    counts = rng.negative_binomial(2, 0.2, size=n)
    feat_a = rng.normal(0, 1, size=n)
    feat_b = rng.normal(0, 1, size=n)

    model = DirectionalCountModel(target_field="count", distribution=DistributionType.AUTO)
    model.fit(_rows(counts, feat_a, feat_b))

    assert model.dispersion_ratio is not None
    assert model.dispersion_ratio > 1.2, model.dispersion_ratio
    assert model.distribution_used == DistributionType.NEGATIVE_BINOMIAL


def test_poisson_selected_for_equidispersed_counts():
    rng = np.random.default_rng(11)
    n = 400
    # Poisson counts: variance ~= mean (equidispersed).
    counts = rng.poisson(3.0, size=n)
    feat_a = rng.normal(0, 1, size=n)
    feat_b = rng.normal(0, 1, size=n)

    model = DirectionalCountModel(target_field="count", distribution=DistributionType.AUTO)
    model.fit(_rows(counts, feat_a, feat_b))

    assert model.dispersion_ratio is not None
    # Poisson data should have a ratio near 1 (comfortably below the 1.2 gate).
    assert model.dispersion_ratio < 1.2, model.dispersion_ratio
    assert model.distribution_used == DistributionType.POISSON


def test_reported_dispersion_ratio_matches_empirical():
    rng = np.random.default_rng(3)
    counts = rng.poisson(4.0, size=200)
    feat = rng.normal(0, 1, size=200)
    model = DirectionalCountModel(target_field="count")
    model.fit(_rows(counts, feat, feat))

    arr = counts.astype(float)
    expected = float(np.var(arr, ddof=1)) / float(arr.mean())
    assert abs(model.dispersion_ratio - expected) < 1e-9
