# Feature: asymmetric-matchup-engine, Property 17: Pooled-only significance is an artifact
"""Property 17: Pooled-only significance is an artifact (task 9.6).

**Property 17** — For any comparison that is significant at the 0.05 level ONLY
when leagues are POOLED and is NOT significant within its own league, the verdict
is "artifact" and never "finding".

Validates: Requirements 8.7.

This sweeps the flags: whenever ``pooled_significant`` is True and
``within_league_significant`` is False (with a non-insufficient sample), the
verdict must be "artifact" regardless of the CI/point magnitudes or FDR flag; and
it must never be "finding".

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is a deterministic ``pytest`` test sweeping the relevant flag cross
product and representative estimates, exercising the same invariant a Hypothesis
strategy would. When task 12.1 lands, convert to ``@given(...)`` over the
``estimates`` strategy plus the boolean flags, with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

import itertools

from src.research.asymmetric.evaluation import (
    VERDICT_ARTIFACT,
    VERDICT_FINDING,
    classify_verdict,
)


_ESTIMATES = [
    (0.05, 0.10),    # even a "beat"-looking CI
    (-0.02, 0.10),   # straddling zero
    (-0.30, -0.10),  # negative
    (0.0, 0.0),      # degenerate
]


def test_pooled_only_significant_is_artifact():
    """pooled sig + NOT within-league sig -> 'artifact', never 'finding'."""
    for (ci_lower, point), fdr_passed in itertools.product(
        _ESTIMATES, (True, False, None)
    ):
        verdict = classify_verdict(
            ci_lower=ci_lower,
            point=point,
            within_league_significant=False,
            pooled_significant=True,
            fdr_passed=fdr_passed,
            insufficient_sample=False,
        )
        assert verdict == VERDICT_ARTIFACT, (
            f"pooled-only should be artifact, got {verdict} "
            f"(ci_lower={ci_lower}, point={point}, fdr={fdr_passed})"
        )
        assert verdict != VERDICT_FINDING


def test_within_league_significant_is_not_artifact():
    """When within-league significant, pooled significance does not make it an
    artifact — it is a candidate finding (subject to the beat criterion + FDR)."""
    verdict = classify_verdict(
        ci_lower=0.05,
        point=0.10,
        within_league_significant=True,
        pooled_significant=True,
        fdr_passed=True,
        insufficient_sample=False,
    )
    assert verdict != VERDICT_ARTIFACT
    assert verdict == VERDICT_FINDING


def test_neither_pooled_nor_within_is_not_artifact():
    """No significance anywhere -> 'fails', not 'artifact'."""
    verdict = classify_verdict(
        ci_lower=-0.1,
        point=-0.05,
        within_league_significant=False,
        pooled_significant=False,
        fdr_passed=None,
        insufficient_sample=False,
    )
    assert verdict != VERDICT_ARTIFACT
    assert verdict != VERDICT_FINDING
