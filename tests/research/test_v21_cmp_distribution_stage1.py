import numpy as np
import pytest

from src.research.evaluation.v21_cmp_distribution_stage1 import (
    CORNERS_NB2_WEIGHT,
    _decision,
    _mixture,
)
from src.research.models.cmp_distribution import convolve_count_pmfs


def _metrics(joint, total_rps=1.0, binary=0.60):
    return {
        "n_fixtures": 100,
        "joint_log_score": joint,
        "total_log_score": 2.0,
        "side_mean_rps": 1.0,
        "total_rps": total_rps,
        "binary_log_loss": binary,
        "brier": 0.21,
    }


def test_cmp_gate_requires_primary_fold_and_distribution_support():
    result = _decision(
        _metrics(2.0, total_rps=1.0, binary=0.60),
        _metrics(1.99, total_rps=0.99, binary=0.6005),
        3,
    )
    assert result["passes_stage1_gate"] is True

    no_folds = _decision(
        _metrics(2.0),
        _metrics(1.99, total_rps=0.99, binary=0.59),
        2,
    )
    assert no_folds["passes_stage1_gate"] is False


def test_cmp_gate_rejects_rps_or_binary_regression():
    rps_bad = _decision(
        _metrics(2.0, total_rps=1.0),
        _metrics(1.99, total_rps=1.00001, binary=0.59),
        4,
    )
    assert rps_bad["passes_stage1_gate"] is False

    binary_bad = _decision(
        _metrics(2.0, total_rps=1.0, binary=0.60),
        _metrics(1.99, total_rps=0.99, binary=0.60101),
        4,
    )
    assert binary_bad["passes_stage1_gate"] is False



def test_fixture_level_mixture_total_is_mixture_of_total_marginals():
    pois_h = np.array([0.7, 0.3])
    pois_a = np.array([0.6, 0.4])
    nb_h = np.array([0.4, 0.6])
    nb_a = np.array([0.3, 0.7])
    correct = _mixture(
        convolve_count_pmfs(pois_h, pois_a),
        convolve_count_pmfs(nb_h, nb_a),
        CORNERS_NB2_WEIGHT,
    )
    marginal_h = _mixture(pois_h, nb_h, CORNERS_NB2_WEIGHT)
    marginal_a = _mixture(pois_a, nb_a, CORNERS_NB2_WEIGHT)
    wrong_cross_mixture = convolve_count_pmfs(marginal_h, marginal_a)
    assert correct.sum() == pytest.approx(1.0)
    assert not np.allclose(correct, wrong_cross_mixture)
