"""Shared fixtures for the V8C suite. Everything here is SYNTHETIC: no real corpus row, no
real outcome, no Sonnet call."""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import universe as UNI


@pytest.fixture(scope="session")
def golden_env():
    """The §16 known-good environment."""
    return G.build_environment()


@pytest.fixture(scope="session")
def golden_universe(golden_env):
    """The full admissible + pre-T evaluable universe at the golden target."""
    ctx = PC.build_pit_context(golden_env.index, golden_env.target_pos)
    return UNI.build_fixture_universe(golden_env.index, golden_env.target_pos, ctx=ctx,
                                      capability=golden_env.capability,
                                      fixture_id=golden_env.target_fixture_id)


@pytest.fixture(scope="session")
def golden_ctx(golden_env):
    return PC.build_pit_context(golden_env.index, golden_env.target_pos)
