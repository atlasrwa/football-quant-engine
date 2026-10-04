import numpy as np
import pytest
from scipy.stats import poisson

from src.research.models.cmp_distribution import (
    cmp_pmf_vector,
    convolve_count_pmfs,
    discrete_rps,
    probability_over,
)


@pytest.mark.parametrize("mean", [0.7, 1.3, 4.8, 9.5])
def test_cmp_nu_one_matches_poisson(mean):
    cmp = cmp_pmf_vector(mean, 1.0)
    reference = poisson.pmf(np.arange(len(cmp)), mean)
    reference /= reference.sum()
    assert np.max(np.abs(cmp - reference)) < 1e-12


@pytest.mark.parametrize("nu", [0.60, 0.75, 0.90, 1.10, 1.25, 1.50])
def test_cmp_mean_parameterization_preserves_requested_mean(nu):
    requested = 4.7
    pmf = cmp_pmf_vector(requested, nu)
    implied = float(np.dot(np.arange(len(pmf)), pmf))
    assert implied == pytest.approx(requested, rel=2e-7, abs=2e-7)
    assert pmf.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.all(pmf >= 0)


def test_cmp_dispersion_direction_around_poisson():
    mean = 5.0
    over = cmp_pmf_vector(mean, 0.75)
    equi = cmp_pmf_vector(mean, 1.0)
    under = cmp_pmf_vector(mean, 1.25)
    k_over = np.arange(len(over))
    k_equi = np.arange(len(equi))
    k_under = np.arange(len(under))
    var_over = float(np.dot((k_over - mean) ** 2, over))
    var_equi = float(np.dot((k_equi - mean) ** 2, equi))
    var_under = float(np.dot((k_under - mean) ** 2, under))
    assert var_over > var_equi > var_under


def test_convolution_and_rps_are_coherent():
    home = cmp_pmf_vector(5.0, 0.9)
    away = cmp_pmf_vector(4.0, 0.9)
    total = convolve_count_pmfs(home, away)
    assert total.sum() == pytest.approx(1.0, abs=1e-12)
    assert discrete_rps(total, 9) >= 0.0
    p_over = probability_over(total, 9.5)
    assert 0.0 <= p_over <= 1.0
