# Feature: asymmetric-matchup-engine, Property 14: Gate stops modelling on any failure
"""Property 14: The Feature_Verification_Gate stops modelling on any failure.

**Property 14: Gate stops modelling on any failure** — for any gate run in which
at least one check fails, the resulting ``GateResult`` has ``passed=False`` and
``stopped_modelling=True``, and no downstream modelling is performed.

Validates: Requirements 6.1, 6.7, 6.8.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is therefore written as a deterministic ``pytest`` test that forces
each check, in turn, to fail and asserts the stop semantics — exercising the same
invariant a Hypothesis strategy would over a space of forced-failure masks. When
task 12.1 lands, convert this to a ``@given(...)`` property test with
``@settings(max_examples=100)`` over a strategy that chooses which subset of the
five checks fails; the assertions below map directly onto the per-example check.
"""

from __future__ import annotations

from itertools import combinations

import pytest

from src.research.asymmetric import gates as gates_mod
from src.research.asymmetric.gates import (
    FEATURE_VERIFICATION_GATE,
    FeatureVerificationGate,
)
from src.research.asymmetric.models import GateCheckResult, GateResult


CHECK_METHODS = (
    "_check_identity_trace",
    "_check_known_signal",
    "_check_orientation",
    "_check_look_ahead",
    "_check_shuffle_null",
)


def _passing(name: str) -> GateCheckResult:
    return GateCheckResult(name=name, passed=True, detail="ok", metric=1.0)


def _failing(name: str) -> GateCheckResult:
    return GateCheckResult(name=name, passed=False, detail="forced failure", metric=0.0)


def _patch_checks(monkeypatch, gate: FeatureVerificationGate, failing_idx: set[int]):
    """Force the checks at ``failing_idx`` to fail and the rest to pass."""
    for i, method in enumerate(CHECK_METHODS):
        name = method.lstrip("_")
        result = _failing(name) if i in failing_idx else _passing(name)
        # Bind a lambda that ignores its args and returns the canned result.
        monkeypatch.setattr(
            gate, method, (lambda *_a, _r=result, **_k: _r)
        )


def test_any_single_failing_check_stops_modelling(monkeypatch):
    """Each check failing individually yields passed=False, stopped_modelling=True."""
    for i in range(len(CHECK_METHODS)):
        gate = FeatureVerificationGate()
        _patch_checks(monkeypatch, gate, {i})
        result: GateResult = gate.run(matches=[])
        assert result.gate == FEATURE_VERIFICATION_GATE
        assert result.passed is False, f"check index {i} failing should fail gate"
        assert result.stopped_modelling is True, (
            f"check index {i} failing must set stopped_modelling"
        )
        # Every check is still reported (Req 6.7).
        assert len(result.checks) == len(CHECK_METHODS)


def test_multiple_failing_subsets_all_stop(monkeypatch):
    """Any non-empty subset of failing checks stops modelling (Property 14)."""
    idxs = list(range(len(CHECK_METHODS)))
    for r in range(1, len(idxs) + 1):
        for subset in combinations(idxs, r):
            gate = FeatureVerificationGate()
            _patch_checks(monkeypatch, gate, set(subset))
            result = gate.run(matches=[])
            assert result.passed is False
            assert result.stopped_modelling is True


def test_all_passing_does_not_stop(monkeypatch):
    """When every check passes, the gate passes and does NOT stop modelling."""
    gate = FeatureVerificationGate()
    _patch_checks(monkeypatch, gate, set())
    result = gate.run(matches=[])
    assert result.passed is True
    assert result.stopped_modelling is False
    assert all(c.passed for c in result.checks)
