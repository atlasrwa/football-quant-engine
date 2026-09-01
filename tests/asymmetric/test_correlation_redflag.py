# Feature: asymmetric-matchup-engine, Property 7: Implied-vs-measured correlation red flag
"""Property 7: Implied-vs-measured correlation red flag (task 6.4).

**Property 7** — For any implied cross-market correlation, the Engine reports the
implied value and raises a red flag IF AND ONLY IF the implied correlation lies
outside the measured Correlation_Structure value by more than the reported
tolerance (measured value +/- its 95% CI half-width, floored at the material
threshold). The measured values and CIs are always reported alongside the
comparison.

Validates: Requirements 3.2, 3.3, 3.4.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test that sweeps implied
correlation values across and inside the tolerance boundary for each covered
pair. When task 12.1 lands, convert to ``@given`` drawing implied values and a
material threshold, wrapped with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

import pytest

from src.research.asymmetric.correlation import (
    CARDS_CORNERS_CORR,
    CARDS_GOALS_CORR,
    CORNERS_GOALS_CORR,
    CORRELATION_CI_HALFWIDTH,
    CORRELATION_PAIRS,
    DEFAULT_MATERIAL_THRESHOLD,
    MEASURED_CORRELATIONS,
    PAIR_CARDS_CORNERS,
    PAIR_CARDS_GOALS,
    PAIR_CORNERS_GOALS,
    compare_correlation,
    compare_correlation_structure,
    implied_correlation_from_samples,
    implied_independence_correlation,
)


def _tolerance(pair: str, material: float) -> float:
    _, ci = MEASURED_CORRELATIONS[pair]
    return max(ci, material)


@pytest.mark.parametrize("pair", list(CORRELATION_PAIRS))
@pytest.mark.parametrize("material", [DEFAULT_MATERIAL_THRESHOLD, 0.0, 0.01, 0.1])
def test_red_flag_iff_outside_tolerance(pair, material):
    """Red flag raised IFF |implied - measured| > tolerance (the boundary sweep)."""
    measured, _ = MEASURED_CORRELATIONS[pair]
    tol = _tolerance(pair, material)

    # Sweep implied values relative to the tolerance boundary.
    deltas = [
        -tol - 0.02,   # clearly outside (below)  -> flag
        -tol - 1e-6,   # just outside (below)     -> flag
        -tol + 1e-6,   # just inside (below)      -> no flag
        -tol * 0.5,    # inside                   -> no flag
        0.0,           # at measured-ish          -> no flag
        tol - 1e-6,    # just inside (above)      -> no flag
        tol + 1e-6,    # just outside (above)     -> flag
        tol + 0.02,    # clearly outside (above)  -> flag
    ]
    for delta in deltas:
        implied = measured + delta
        cmp = compare_correlation(pair, implied, material_threshold=material)
        expected_flag = abs(delta) > tol
        assert cmp.red_flag is expected_flag, (
            f"pair={pair} material={material} implied={implied} delta={delta} "
            f"tol={tol}: expected red_flag={expected_flag}, got {cmp.red_flag}"
        )
        # Measured value and CI are always reported alongside (Req 3.4).
        assert cmp.measured == measured
        assert cmp.ci_halfwidth == CORRELATION_CI_HALFWIDTH


@pytest.mark.parametrize("pair", list(CORRELATION_PAIRS))
def test_near_zero_implied_is_not_flagged(pair):
    """The pure-independence implied ~0 is within tolerance of the measured value."""
    cmp = compare_correlation(pair, implied_independence_correlation())
    assert cmp.red_flag is False
    # Independence implies exactly 0.
    assert cmp.implied == 0.0


def test_structure_reports_all_pairs_and_measured_constants():
    """compare_correlation_structure carries measured constants + CIs (Req 3.4)."""
    result = compare_correlation_structure()  # all implied default to ~0
    assert set(result.implied_correlations) == set(CORRELATION_PAIRS)
    assert result.measured_correlations[PAIR_CARDS_CORNERS] == (
        CARDS_CORNERS_CORR, CORRELATION_CI_HALFWIDTH,
    )
    assert result.measured_correlations[PAIR_CARDS_GOALS] == (
        CARDS_GOALS_CORR, CORRELATION_CI_HALFWIDTH,
    )
    assert result.measured_correlations[PAIR_CORNERS_GOALS] == (
        CORNERS_GOALS_CORR, CORRELATION_CI_HALFWIDTH,
    )
    # No red flags for near-zero implied correlations.
    assert result.correlation_red_flags == ()


def test_structure_flags_material_deviation():
    """A materially large implied correlation surfaces as a red flag."""
    result = compare_correlation_structure({PAIR_CARDS_CORNERS: 0.6})
    assert len(result.correlation_red_flags) == 1
    assert PAIR_CARDS_CORNERS in result.correlation_red_flags[0]
    # The other two pairs (defaulted to ~0) are not flagged.
    assert result.implied_correlations[PAIR_CARDS_GOALS] == 0.0


def test_implied_correlation_from_independent_samples_is_near_zero():
    """Independent joint samples imply ~0 correlation (the expected case)."""
    import numpy as np

    rng = np.random.default_rng(7)
    a = rng.poisson(4.0, size=5000).astype(float)
    b = rng.poisson(2.5, size=5000).astype(float)
    implied = implied_correlation_from_samples(a, b)
    assert abs(implied) < 0.05
    # And it is not flagged against the measured near-zero structure.
    assert compare_correlation(PAIR_CORNERS_GOALS, implied).red_flag is False


def test_implied_correlation_from_coupled_samples_detected():
    """A deliberately coupled joint sample yields a large implied correlation."""
    import numpy as np

    rng = np.random.default_rng(11)
    shared = rng.normal(0, 1, size=5000)
    a = shared + rng.normal(0, 0.1, size=5000)
    b = shared + rng.normal(0, 0.1, size=5000)
    implied = implied_correlation_from_samples(a, b)
    assert implied > 0.8
    assert compare_correlation(PAIR_CARDS_CORNERS, implied).red_flag is True


def test_degenerate_samples_return_zero():
    assert implied_correlation_from_samples([1.0], [1.0]) == 0.0
    assert implied_correlation_from_samples([2.0, 2.0, 2.0], [1.0, 3.0, 5.0]) == 0.0


def test_unknown_pair_rejected():
    with pytest.raises(ValueError):
        compare_correlation("cards_sot", 0.0)


def test_negative_material_threshold_rejected():
    with pytest.raises(ValueError):
        compare_correlation(PAIR_CARDS_CORNERS, 0.0, material_threshold=-0.1)
