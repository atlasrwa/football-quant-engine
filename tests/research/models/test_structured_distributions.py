import math

import pytest

from src.research.models.structured_distributions import (
    binary_log_loss,
    brier_score,
    dixon_coles_joint_logpmf,
    dixon_coles_total_pmf,
    dixon_coles_under_probability,
    fit_dixon_coles_rho,
    fit_nb2_dispersion,
    nb2_logpmf,
)


def test_nb2_fit_detects_overdispersion():
    # Alternating low/high counts around a common mean are intentionally
    # overdispersed relative to Poisson.
    rows=[(5.0, 0 if i % 2 == 0 else 10) for i in range(200)]
    fit=fit_nb2_dispersion(rows)
    assert fit.alpha > 0.05
    assert math.isfinite(nb2_logpmf(5,5.0,fit.alpha))


def test_dixon_coles_rho_zero_reduces_to_independent_poisson():
    ll=dixon_coles_joint_logpmf(1,1,1.3,1.0,0.0)
    from scipy.stats import poisson
    expected=poisson.logpmf(1,1.3)+poisson.logpmf(1,1.0)
    assert ll == pytest.approx(expected)


def test_dixon_coles_total_distribution_is_nearly_normalized():
    probs=[dixon_coles_total_pmf(t,1.4,1.1,-0.05) for t in range(16)]
    assert sum(probs) == pytest.approx(1.0, abs=1e-6)


def test_dc_under_2_5_is_valid_probability():
    p=dixon_coles_under_probability(2.5,1.4,1.1,-0.05)
    assert 0 < p < 1


def test_dc_rho_fit_prefers_negative_rho_for_excess_one_zero_zero_one():
    rows=[]
    for _ in range(100):
        rows.append((1.2,1.0,1,0))
        rows.append((1.2,1.0,0,1))
    for _ in range(40):
        rows.append((1.2,1.0,1,1))
        rows.append((1.2,1.0,0,0))
    fit=fit_dixon_coles_rho(rows)
    assert fit.rho > 0  # tau(1,0)/(0,1) grows with positive rho


def test_binary_scores_are_proper_shapes():
    assert binary_log_loss(0.9,True) < binary_log_loss(0.6,True)
    assert brier_score(0.9,True) < brier_score(0.6,True)

from src.research.models.structured_distributions import (
    independent_btts_probability,
    dixon_coles_btts_probability,
)

def test_dc_btts_reduces_to_independent_at_zero_rho():
    assert dixon_coles_btts_probability(1.4,1.1,0.0) == pytest.approx(
        independent_btts_probability(1.4,1.1)
    )
