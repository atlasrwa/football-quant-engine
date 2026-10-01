"""Regression tests for the QFE V2 no-vig market layer."""

import pytest

from src.research.reconciliation.devig import devig, overround


def test_overround_preserves_raw_bookmaker_margin() -> None:
    odds = {"OVER": 1.80, "UNDER": 2.00}
    assert overround(odds) == pytest.approx((1 / 1.80) + (1 / 2.00))
    assert overround(odds) > 1.0


def test_multiplicative_devig_sums_to_one_and_removes_margin() -> None:
    odds = {"OVER": 1.80, "UNDER": 2.00}
    result = devig(odds, method="multiplicative")
    assert sum(result.fair_probabilities.values()) == pytest.approx(1.0)
    assert result.fair_probabilities["OVER"] == pytest.approx(
        (1 / 1.80) / ((1 / 1.80) + (1 / 2.00))
    )
    assert result.margin > 0.0


def test_shin_devig_is_a_normalized_sensitivity_method() -> None:
    result = devig({"OVER": 1.80, "UNDER": 2.00}, method="shin")
    assert sum(result.fair_probabilities.values()) == pytest.approx(1.0)
    assert all(0.0 < p < 1.0 for p in result.fair_probabilities.values())


def test_devig_rejects_invalid_price() -> None:
    with pytest.raises(ValueError):
        devig({"OVER": 0.0, "UNDER": 2.00})
