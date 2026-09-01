# Feature: asymmetric-matchup-engine, Property 8: Team-level shrinkage monotonicity
"""Property 8: Team-level shrinkage monotonicity (task 4.3).

**Property 8: Team-level shrinkage monotonicity** — for a fixed team mean and
global mean, increasing ``n`` moves the shrunk estimate
``n/(n+k)*team_mean + (k/(n+k))*global_mean`` monotonically toward the team mean
and never away from it; the shrinkage weight ``n/(n+k)`` is strictly increasing
in ``n``.

Validates: Requirements 5.1, 5.6.

Property-based via Hypothesis over ``n``, ``team_mean``, ``global_mean`` with
``@settings(max_examples=100)`` (finalized in task 12.1). The deterministic
anchor cases below are retained as concrete regression checks.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.research.asymmetric.directional_model import (
    SHRINKAGE_K,
    shrink_estimate,
    shrinkage_weight,
)

_MEANS = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=100, deadline=None)
@given(n=st.integers(min_value=0, max_value=5000))
def test_weight_monotone_and_bounded_property(n: int) -> None:
    """``n/(n+k)`` is in [0,1) and strictly greater than the weight at n-1."""
    w = shrinkage_weight(n)
    assert 0.0 <= w < 1.0
    if n > 0:
        assert w > shrinkage_weight(n - 1)


@settings(max_examples=100, deadline=None)
@given(team_mean=_MEANS, global_mean=_MEANS, n=st.integers(min_value=0, max_value=2000))
def test_shrunk_estimate_never_moves_away_from_team_mean_property(
    team_mean: float, global_mean: float, n: int
) -> None:
    """The gap to the team mean is non-increasing as n grows (Property 8)."""
    gap_n = abs(shrink_estimate(team_mean, global_mean, n) - team_mean)
    gap_next = abs(shrink_estimate(team_mean, global_mean, n + 1) - team_mean)
    assert gap_next <= gap_n + 1e-9


@settings(max_examples=100, deadline=None)
@given(team_mean=_MEANS, global_mean=_MEANS)
def test_endpoint_and_convex_combination_property(
    team_mean: float, global_mean: float
) -> None:
    """n=0 -> global mean; any n -> the exact convex combination."""
    assert shrink_estimate(team_mean, global_mean, 0) == global_mean
    for n in (1, 5, 50):
        w = shrinkage_weight(n, SHRINKAGE_K)
        expected = w * team_mean + (1 - w) * global_mean
        assert abs(shrink_estimate(team_mean, global_mean, n) - expected) < 1e-9


def test_weight_strictly_increasing_in_n():
    """``n/(n+k)`` is strictly increasing in n and lands in [0, 1)."""
    prev = shrinkage_weight(0)
    assert prev == 0.0
    for n in range(1, 500):
        w = shrinkage_weight(n)
        assert 0.0 <= w < 1.0
        assert w > prev, f"weight not strictly increasing at n={n}"
        prev = w


def test_shrunk_estimate_moves_monotonically_toward_team_mean():
    """As n grows, the shrunk estimate approaches team_mean monotonically."""
    cases = [
        (10.0, 2.0),   # team above global
        (1.0, 5.0),    # team below global
        (3.0, 3.0),    # equal (should be constant)
        (0.0, 4.5),
        (7.25, -1.5),
    ]
    for team_mean, global_mean in cases:
        prev_gap = None
        prev_est = None
        for n in range(0, 400):
            est = shrink_estimate(team_mean, global_mean, n)
            gap = abs(est - team_mean)
            if prev_gap is not None:
                # Never moves away from the team mean.
                assert gap <= prev_gap + 1e-12, (
                    f"estimate moved away from team mean at n={n} "
                    f"(team={team_mean}, global={global_mean})"
                )
                # And the estimate itself moves monotonically from global->team.
                if team_mean > global_mean:
                    assert est >= prev_est - 1e-12
                elif team_mean < global_mean:
                    assert est <= prev_est + 1e-12
            prev_gap = gap
            prev_est = est
        # In the limit of large n the estimate is essentially the team mean.
        assert abs(shrink_estimate(team_mean, global_mean, 100_000) - team_mean) < 1e-2


def test_endpoints_match_convex_combination_definition():
    """n=0 yields the global mean; large n yields (nearly) the team mean."""
    team_mean, global_mean = 6.0, 2.0
    assert shrink_estimate(team_mean, global_mean, 0) == global_mean
    w = shrinkage_weight(5, SHRINKAGE_K)
    expected = w * team_mean + (1 - w) * global_mean
    assert abs(shrink_estimate(team_mean, global_mean, 5) - expected) < 1e-12
