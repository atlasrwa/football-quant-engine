# Feature: asymmetric-matchup-engine, Property 15: Confidence interval on every estimate and CI-spanning-zero suppression
"""Property 15: CI presence and CI-spanning-zero suppression (task 10.2).

**Property 15** — for any reported estimate, ``ci_low <= point <= ci_high``
holds, and the estimate is treated as a result if and only if its CI does not
span zero; an estimate whose CI spans zero is labelled "not a result".

Validates: Requirements 10.8, 10.9.

Implemented as a single Hypothesis property test over the ``estimates`` strategy
with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

from hypothesis import given, settings

from src.research.asymmetric.models import Estimate
from src.research.asymmetric.reporting import NOT_A_RESULT_LABEL, format_estimate
from tests.asymmetric.strategies import estimates


@settings(max_examples=200)
@given(est=estimates())
def test_ci_present_and_spanning_zero_suppressed(est: Estimate) -> None:
    # Req 10.8: the CI brackets the point estimate.
    assert est.ci_low <= est.point <= est.ci_high

    rendered = format_estimate(est)
    # Req 10.8: the rendered estimate always shows the CI bounds.
    assert "95% CI" in rendered
    assert f"{est.ci_low:+.4f}" in rendered
    assert f"{est.ci_high:+.4f}" in rendered

    # Req 10.9: "result" iff CI does not span zero; spanning-zero is labelled.
    spans_zero = est.ci_low <= 0.0 <= est.ci_high
    assert est.spans_zero is spans_zero
    assert est.is_result is (not spans_zero)
    if spans_zero:
        assert NOT_A_RESULT_LABEL in rendered
    else:
        assert NOT_A_RESULT_LABEL not in rendered


def test_boundary_touching_zero_is_not_a_result() -> None:
    """A CI whose bound exactly touches zero counts as spanning zero (closed CI)."""
    touching_low = Estimate(point=0.05, ci_low=0.0, ci_high=0.10)
    touching_high = Estimate(point=-0.05, ci_low=-0.10, ci_high=0.0)
    for est in (touching_low, touching_high):
        assert est.spans_zero is True
        assert est.is_result is False
        assert NOT_A_RESULT_LABEL in format_estimate(est)

    strictly_positive = Estimate(point=0.05, ci_low=0.01, ci_high=0.10)
    assert strictly_positive.is_result is True
    assert NOT_A_RESULT_LABEL not in format_estimate(strictly_positive)
