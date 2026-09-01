# Feature: asymmetric-matchup-engine, Property 16: Asymmetry verdict decision logic
"""Property 16: Asymmetry verdict decision logic (task 9.5).

**Property 16** — For any Per_Side_Target comparison, the verdict is "finding"
only if the out-of-sample BSS improvement over the Symmetric_Baseline is strictly
positive with a 95% CI lower bound greater than zero AND the within-league
improvement is significant at alpha 0.05 AND it survives Benjamini-Hochberg at
q=0.05; otherwise the comparison is reported as "fails" (or, per the sibling
properties, "artifact"/"insufficient-sample" — but never "finding" unless all
three conditions hold).

Validates: Requirements 8.1, 8.3, 8.5, 8.6, 8.9.

This sweeps the input flags/estimates (CI-lower sign, point sign, within-league
significance, FDR pass) and asserts ``classify_verdict`` returns "finding" iff
ALL of the finding conditions hold, and otherwise never returns "finding".

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is a deterministic ``pytest`` test sweeping the full boolean cross
product plus representative CI/point magnitudes, exercising the same invariant a
Hypothesis strategy would over the ``estimates`` strategy. When task 12.1 lands,
convert to ``@given(...)`` drawing ``(point, ci_low, ci_high)`` triples (spanning
and not spanning zero) and the boolean flags, with
``@settings(max_examples=100)``; the per-example assertion below maps directly.
"""

from __future__ import annotations

import itertools

from src.research.asymmetric.evaluation import (
    VERDICT_FINDING,
    VERDICT_FAILS,
    classify_verdict,
)


# (ci_lower, point) pairs covering: beat, straddle-zero, negative.
_CI_POINT = [
    (0.05, 0.10),    # beat: ci_lower > 0 and point > 0
    (0.001, 0.20),   # beat, small margin
    (-0.02, 0.10),   # ci straddles zero -> NOT beat
    (0.0, 0.10),     # ci_lower exactly 0 -> NOT beat (strict > 0)
    (-0.30, -0.10),  # clearly negative
    (0.05, 0.0),     # point exactly 0 -> NOT beat (strict > 0)
]


def _beat(ci_lower: float, point: float) -> bool:
    return point > 0.0 and ci_lower > 0.0


def test_finding_iff_all_three_conditions_hold():
    """finding <=> (beat criterion) AND within-league sig AND FDR pass."""
    for (ci_lower, point), within_sig, fdr_passed, pooled_sig in itertools.product(
        _CI_POINT, (True, False), (True, False, None), (True, False)
    ):
        verdict = classify_verdict(
            ci_lower=ci_lower,
            point=point,
            within_league_significant=within_sig,
            pooled_significant=pooled_sig,
            fdr_passed=fdr_passed,
            insufficient_sample=False,
        )
        should_be_finding = _beat(ci_lower, point) and within_sig and (fdr_passed is True)
        if should_be_finding:
            assert verdict == VERDICT_FINDING, (
                f"expected finding for ci_lower={ci_lower}, point={point}, "
                f"within_sig={within_sig}, fdr={fdr_passed}"
            )
        else:
            assert verdict != VERDICT_FINDING, (
                f"must NOT be finding for ci_lower={ci_lower}, point={point}, "
                f"within_sig={within_sig}, fdr={fdr_passed}, pooled={pooled_sig} "
                f"-> got {verdict}"
            )


def test_beat_but_no_within_league_sig_is_not_finding():
    """Beat criterion met but not within-league significant -> not a finding."""
    v = classify_verdict(
        ci_lower=0.05, point=0.1,
        within_league_significant=False,
        pooled_significant=False,
        fdr_passed=True,
        insufficient_sample=False,
    )
    assert v != VERDICT_FINDING


def test_beat_and_within_sig_but_fdr_fail_is_fails():
    """Beat + within-league sig but FDR fails -> 'fails' (not a finding)."""
    v = classify_verdict(
        ci_lower=0.05, point=0.1,
        within_league_significant=True,
        pooled_significant=False,
        fdr_passed=False,
        insufficient_sample=False,
    )
    assert v == VERDICT_FAILS


def test_ci_spanning_zero_never_finding_even_with_sig_and_fdr():
    """A CI that straddles zero fails the beat criterion -> never a finding."""
    for ci_lower, point in [(-0.01, 0.1), (0.0, 0.1), (-0.5, 0.5)]:
        v = classify_verdict(
            ci_lower=ci_lower, point=point,
            within_league_significant=True,
            pooled_significant=True,
            fdr_passed=True,
            insufficient_sample=False,
        )
        assert v != VERDICT_FINDING
