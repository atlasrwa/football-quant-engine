# Feature: asymmetric-matchup-engine, Property 8: Team-level shrinkage monotonicity
"""Property 8: Team-level shrinkage monotonicity (task 4.3).

**Property 8: Team-level shrinkage monotonicity** — for a fixed team mean and
global mean, increasing ``n`` moves the shrunk estimate
``n/(n+k)*team_mean + (k/(n+k))*global_mean`` monotonically toward the team mean
and never away from it; the shrinkage weight ``n/(n+k)`` is strictly increasing
in ``n``.

Validates: Requirements 5.1, 5.6.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is therefore written as a deterministic ``pytest`` test that sweeps
``n`` over a wide range for several (team_mean, global_mean) pairs, exercising
the same invariant a Hypothesis strategy would. When task 12.1 lands, convert
to ``@given(...)`` over ``n``, ``team_mean``, ``global_mean`` with
``@settings(max_examples=100)`` — the per-example assertions map directly onto
the checks below.
"""

from __future__ import annotations

from src.research.asymmetric.directional_model import (
    SHRINKAGE_K,
    shrink_estimate,
    shrinkage_weight,
)


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
