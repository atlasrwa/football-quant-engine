"""Tests for Layer 3 distribution candidates."""

from __future__ import annotations

import math

import pytest

from src.research.models.distribution_candidates import (
    OnlineGridSelector,
    binary_log_loss,
    dixon_coles_btts_probability,
    dixon_coles_joint_nll,
    dixon_coles_total_over_probability,
    nb2_side_nll,
    nb2_side_over_probability,
    nb2_total_over_probability,
    poisson_joint_nll,
)


def test_binary_log_loss_prefers_correct_confidence() -> None:
    assert binary_log_loss(0.8, True) < binary_log_loss(0.6, True)
    assert binary_log_loss(0.2, False) < binary_log_loss(0.4, False)


def test_dixon_coles_rho_zero_equals_independent_poisson() -> None:
    for home, away in ((0, 0), (0, 1), (1, 0), (1, 1), (2, 3)):
        assert dixon_coles_joint_nll(
            home, away, 1.4, 1.1, 0.0
        ) == pytest.approx(
            poisson_joint_nll(home, away, 1.4, 1.1)
        )


def test_dixon_coles_probabilities_are_valid() -> None:
    for rho in (-0.15, -0.10, -0.05, 0.0, 0.05):
        over = dixon_coles_total_over_probability(1.5, 1.0, 2.5, rho)
        btts = dixon_coles_btts_probability(1.5, 1.0, rho)
        assert 0.0 <= over <= 1.0
        assert 0.0 <= btts <= 1.0


def test_nb2_alpha_zero_equals_poisson() -> None:
    assert nb2_side_nll(5, 3, 4.8, 3.2, 0.0) == pytest.approx(
        poisson_joint_nll(5, 3, 4.8, 3.2)
    )


def test_nb2_event_probabilities_are_valid() -> None:
    for alpha in (0.0, 0.05, 0.2, 0.5):
        side = nb2_side_over_probability(5.0, 4.5, alpha)
        total = nb2_total_over_probability(5.0, 4.0, 9.5, alpha)
        assert 0.0 <= side <= 1.0
        assert 0.0 <= total <= 1.0


def test_online_selector_uses_anchor_until_min_observations() -> None:
    selector = OnlineGridSelector((0.0, 0.1, 0.2), min_observations=2)
    assert selector.selected == 0.0
    selector.update(lambda value: 1.0 if value == 0.2 else 2.0)
    assert selector.selected == 0.0
    selector.update(lambda value: 1.0 if value == 0.2 else 2.0)
    assert selector.selected == 0.2


def test_online_selector_is_preoutcome_and_deterministic() -> None:
    selector = OnlineGridSelector((0.0, -0.05, -0.1), min_observations=0)
    assert selector.selected == 0.0
    selector.update(lambda value: {0.0: 2.0, -0.05: 1.0, -0.1: 1.0}[value])
    # Tied best values preserve declared grid order.
    assert selector.selected == -0.05


def test_quarter_line_is_rejected_for_binary_event_scoring() -> None:
    with pytest.raises(ValueError):
        dixon_coles_total_over_probability(1.4, 1.0, 2.25, -0.05)
    with pytest.raises(ValueError):
        nb2_total_over_probability(5.0, 4.0, 9.25, 0.2)
