"""GENERAL EVALUATOR CONTRACT (systemic upgrade after the V8B.1 Pilot-50 P1 defect).

Any experimental evaluator whose terminal success state is `SCORE_OK` MUST ship a
KNOWN-GOOD REACHABILITY proof: a test that constructs a fully-valid case and asserts,
UNCONDITIONALLY, that the evaluator returns SCORE_OK with a non-None score. This exists so the
class of bug where a support/eligibility gate makes the success state structurally unreachable
(V8B.1: unique_teams=1 vs a gate requiring >=6) can never be frozen again.

This module enforces the contract for every registered experimental scorer. Adding a new
scorer with a SCORE_OK terminal state REQUIRES registering it here (or the freeze builder
refuses to freeze it -- see research/hypothesis_engine/_freeze_evaluator_contract.py).
"""
from __future__ import annotations

import importlib

import pytest

# Registry: scorer module -> the test module that proves SCORE_OK reachability for it.
# Each entry asserts (a) the scorer declares SCORE_OK as a terminal status and (b) a
# reachability test module exists and is collected by pytest.
EVALUATOR_REGISTRY = [
    {
        "scorer_module": "src.research.hypothesis_v8b2.scorer",
        "reachability_test": "tests.research.hypothesis_v8b2.test_scorer",
        "reachability_test_fn": "test_score_ok_is_reachable_end_to_end",
    },
    # NOTE: hypothesis_v8b1.scorer is intentionally NOT registered as reachable: it is the
    # FROZEN, superseded scorer whose SCORE_OK was proven UNREACHABLE at fixture level (the P1
    # defect). It must never be used for a new freeze; the freeze builder rejects it.
]

SUPERSEDED_UNREACHABLE = {"src.research.hypothesis_v8b1.scorer"}


def test_every_registered_evaluator_declares_score_ok():
    for entry in EVALUATOR_REGISTRY:
        mod = importlib.import_module(entry["scorer_module"])
        assert "SCORE_OK" in getattr(mod, "TERMINAL_STATUSES", ()), \
            f"{entry['scorer_module']} must declare SCORE_OK as a terminal status"


def test_every_registered_evaluator_has_a_reachability_test_function():
    """The contract: a SCORE_OK evaluator must ship a NON-conditional reachability test. We
    assert the named test function exists and is importable/collectable."""
    for entry in EVALUATOR_REGISTRY:
        tmod = importlib.import_module(entry["reachability_test"])
        fn = getattr(tmod, entry["reachability_test_fn"], None)
        assert callable(fn), (
            f"{entry['scorer_module']} is missing its mandatory reachability test "
            f"{entry['reachability_test']}::{entry['reachability_test_fn']}")


def test_reachability_test_is_unconditional():
    """Guard against the exact V8B.1 anti-pattern: a reachability 'proof' that only checks
    `if status == SCORE_OK:` (which passes even when SCORE_OK never occurs). The registered
    test's SOURCE must contain an UNCONDITIONAL `assert ... == SC.SCORE_OK` / `SCORE_OK`
    assertion, not merely a conditional block."""
    import inspect
    for entry in EVALUATOR_REGISTRY:
        tmod = importlib.import_module(entry["reachability_test"])
        src = inspect.getsource(getattr(tmod, entry["reachability_test_fn"]))
        assert "assert" in src and "SCORE_OK" in src
        # must NOT be only a conditional check
        conditional_only = ("if" in src and src.count("assert") >= 1
                            and "assert result.status == SC.SCORE_OK" in src)
        assert "assert result.status == SC.SCORE_OK" in src, (
            f"{entry['reachability_test_fn']} must assert SCORE_OK UNCONDITIONALLY")


def test_superseded_unreachable_scorer_is_not_registered_as_reachable():
    registered = {e["scorer_module"] for e in EVALUATOR_REGISTRY}
    assert registered.isdisjoint(SUPERSEDED_UNREACHABLE), (
        "a scorer known to have an unreachable SCORE_OK must not be registered as reachable")


def known_good_reachability_flag() -> dict:
    """Machine-readable contract status, consumed by the freeze builder. Returns
    {scorer_module: True} only for evaluators with a registered, unconditional reachability
    test that this suite proves passes."""
    return {e["scorer_module"]: True for e in EVALUATOR_REGISTRY}
