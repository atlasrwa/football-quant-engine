"""Shared fixtures for the V8C suite. Everything is SYNTHETIC: no real corpus row, no real
outcome, no Sonnet call. Session-scoped because a universe build is seconds, not milliseconds."""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import universe as UNI

#: Two metrics keeps the enumeration fast while still exercising the full grammar shape.
GOLDEN_METRICS = ("goals", "yellow_cards")
GRAMMAR_KW = {"metrics": list(GOLDEN_METRICS)}


@pytest.fixture(scope="session")
def golden_env():
    return G.build_environment(metrics=GOLDEN_METRICS)


@pytest.fixture(scope="session")
def golden_ctx(golden_env):
    return PC.build_pit_context(golden_env.index, golden_env.target_pos)


@pytest.fixture(scope="session")
def golden_universe(golden_env, golden_ctx):
    return UNI.build_fixture_universe(
        golden_env.index, golden_env.target_pos, ctx=golden_ctx,
        capability=golden_env.capability, fixture_id=golden_env.target_fixture_id,
        grammar_kwargs=GRAMMAR_KW)


@pytest.fixture(scope="session")
def multi_env():
    """A 15-target environment: the smallest cohort the frozen inference rule can support
    (3 qualifying blocks x 5 paired differences)."""
    return G.build_environment(n_targets=15, metrics=GOLDEN_METRICS)
