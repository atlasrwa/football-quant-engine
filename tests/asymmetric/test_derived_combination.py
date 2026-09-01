# Feature: asymmetric-matchup-engine, Property 6: Derived combination under independence
"""Property 6: Derived combination under independence (task 6.3).

**Property 6** — For any two per-side count PMFs, the derived total equals their
discrete convolution and is itself a valid PMF; the mean of the derived total
equals the sum of the two per-side means (within tolerance); and the derived
BTTS probability equals ``P(sideA >= 1) * P(sideB >= 1)`` under the stated
independence assumption.

Validates: Requirements 2.9, 3.1.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test that sweeps a grid of
per-side PMFs (built from Poisson/NB means and hand-crafted edge cases). When
task 12.1 lands, convert to ``@given`` drawing pairs of PMFs via the
``count_pmfs`` strategy, wrapped with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.stats import poisson

from src.research.asymmetric.derived import (
    DerivedOutcomeCombiner,
    convolve_pmfs,
    is_valid_pmf,
    pmf_mean,
)
from src.research.asymmetric.interaction import DIRECTION_A, DIRECTION_B
from src.research.asymmetric.models import DirectionPrediction

TOL = 1e-6


def _poisson_pmf(mean: float, max_k: int) -> tuple[float, ...]:
    """A truncated + renormalised Poisson PMF over 0..max_k (a valid PMF)."""
    raw = [float(poisson.pmf(k, mean)) for k in range(max_k + 1)]
    total = math.fsum(raw)
    return tuple(v / total for v in raw)


# A grid of per-side PMFs: several Poisson means plus explicit edge cases.
_PMFS: list[tuple[float, ...]] = [
    _poisson_pmf(0.5, 10),
    _poisson_pmf(1.3, 12),
    _poisson_pmf(4.0, 20),
    _poisson_pmf(9.0, 25),
    (1.0,),                    # degenerate: all mass at 0
    (0.0, 1.0),                # degenerate: all mass at 1
    (0.25, 0.25, 0.25, 0.25),  # uniform over 0..3
    (0.6, 0.1, 0.1, 0.1, 0.1),
]


@pytest.mark.parametrize("pmf_a", _PMFS)
@pytest.mark.parametrize("pmf_b", _PMFS)
def test_convolution_is_valid_pmf_and_mean_additive(pmf_a, pmf_b):
    """Total = convolution, is a valid PMF, and mean(total) == mean(A)+mean(B)."""
    total = convolve_pmfs(pmf_a, pmf_b)

    # Valid PMF.
    assert is_valid_pmf(total)
    assert all(0.0 <= x <= 1.0 for x in total)
    assert abs(math.fsum(total) - 1.0) < TOL

    # Support length: (len(a)-1) + (len(b)-1) + 1.
    assert len(total) == len(pmf_a) + len(pmf_b) - 1

    # Mean additivity: E[A + B] == E[A] + E[B].
    expected_mean = pmf_mean(pmf_a) + pmf_mean(pmf_b)
    assert abs(pmf_mean(total) - expected_mean) < 1e-6


@pytest.mark.parametrize("pmf_a", _PMFS)
@pytest.mark.parametrize("pmf_b", _PMFS)
def test_convolution_matches_numpy_reference(pmf_a, pmf_b):
    """Discrete convolution matches numpy's reference convolution (renormalised)."""
    ref = np.convolve(np.asarray(pmf_a), np.asarray(pmf_b))
    ref = ref / ref.sum()
    got = np.asarray(convolve_pmfs(pmf_a, pmf_b))
    assert np.allclose(got, ref, atol=1e-9)


def _dp(direction: str, target: str, dist: tuple[float, ...]) -> DirectionPrediction:
    return DirectionPrediction(
        direction=direction,
        attacker="H" if direction == DIRECTION_A else "A",
        defender="A" if direction == DIRECTION_A else "H",
        target=target,
        distribution=dist,
        expected_value=pmf_mean(dist),
        driving_features=("f",),
    )


@pytest.mark.parametrize("goals_home", _PMFS)
@pytest.mark.parametrize("goals_away", _PMFS)
def test_btts_equals_product_of_at_least_one(goals_home, goals_away):
    """Through the combiner, BTTS == P(home>=1)*P(away>=1) (Req 3.1)."""
    combiner = DerivedOutcomeCombiner()
    # Provide corners/cards/goals for both directions; use goals under test.
    dirs = [
        _dp(DIRECTION_A, "corners", _PMFS[1]),
        _dp(DIRECTION_B, "corners", _PMFS[2]),
        _dp(DIRECTION_A, "cards", _PMFS[3]),
        _dp(DIRECTION_B, "cards", _PMFS[0]),
        _dp(DIRECTION_A, "goals", goals_home),
        _dp(DIRECTION_B, "goals", goals_away),
    ]
    outcomes = combiner.combine(dirs)

    p_home = 1.0 - goals_home[0]
    p_away = 1.0 - goals_away[0]
    assert abs(outcomes.btts_yes - p_home * p_away) < 1e-9

    # Clean sheets: home CS = away scores 0; away CS = home scores 0.
    assert abs(outcomes.clean_sheet_home - goals_away[0]) < 1e-9
    assert abs(outcomes.clean_sheet_away - goals_home[0]) < 1e-9


@pytest.mark.parametrize("goals_home", _PMFS)
@pytest.mark.parametrize("goals_away", _PMFS)
def test_derived_totals_are_valid_pmfs_through_combiner(goals_home, goals_away):
    """Every derived total PMF from combine() sums to 1 and lies in [0,1]."""
    combiner = DerivedOutcomeCombiner()
    dirs = [
        _dp(DIRECTION_A, "corners", _PMFS[2]),
        _dp(DIRECTION_B, "corners", _PMFS[3]),
        _dp(DIRECTION_A, "cards", _PMFS[1]),
        _dp(DIRECTION_B, "cards", _PMFS[0]),
        _dp(DIRECTION_A, "goals", goals_home),
        _dp(DIRECTION_B, "goals", goals_away),
    ]
    outcomes = combiner.combine(dirs)
    for total in (outcomes.total_corners, outcomes.total_cards, outcomes.total_goals):
        assert is_valid_pmf(total)
        assert abs(sum(total) - 1.0) < TOL

    # total_goals mean == home goals mean + away goals mean.
    assert abs(
        pmf_mean(outcomes.total_goals)
        - (pmf_mean(goals_home) + pmf_mean(goals_away))
    ) < 1e-6


def test_empty_pmf_rejected():
    with pytest.raises(ValueError):
        convolve_pmfs([], [1.0])
    with pytest.raises(ValueError):
        convolve_pmfs([1.0], [])


def test_negative_entry_rejected():
    with pytest.raises(ValueError):
        convolve_pmfs([0.5, 0.6, -0.1], [1.0])
