"""P1-J: the fresh-pilot population rule must be PREREGISTERED and say something checkable.

A defect must never close because a file exists. These tests read the artifact's CONTENT, so
the ledger entry is backed by an assertion about what was frozen, not by a directory listing.
"""
from __future__ import annotations

import os
import re

import pytest

from src.research.hypothesis_v8c import aggregate as AG

ARTIFACT = "/home/ubuntu/research/hypothesis_engine/V8C_FRESH_PILOT_POPULATION_RULE.md"


@pytest.fixture(scope="module")
def doc():
    assert os.path.exists(ARTIFACT), "the pilot rule artifact is absent"
    return open(ARTIFACT).read()


def test_pilot_N_is_frozen_and_stated(doc):
    m = re.search(r"^N\s*=\s*(\d+)\s*$", doc, re.MULTILINE)
    assert m, "the artifact does not state a single frozen N"
    assert int(m.group(1)) == 60


def test_pilot_N_is_consistent_with_the_frozen_inference_floor(doc):
    """N must be DERIVED from the estimator's own bounds, not chosen for convenience."""
    floor = AG.MIN_QUALIFYING_BLOCKS * AG.MIN_PAIRED_PER_BLOCK        # 3 x 5 = 15
    assert floor == 15
    m = re.search(r"^N\s*=\s*(\d+)\s*$", doc, re.MULTILINE)
    n = int(m.group(1))
    assert n >= floor, "N sits below the paired-inference floor"
    assert str(floor) in doc, "the artifact does not show the floor it was derived from"


def test_eligibility_is_structural_only(doc):
    assert "pre_t_evaluable_candidates >= K_MIN" in doc
    assert "distinct_R_feasible" in doc and "H_feasible" in doc
    assert re.search(r"K_MIN\s*=\s*4", doc), "K_MIN is not stated"
    # and it must say, in terms, that no outcome is read
    assert re.search(r"no criterion reads a target outcome", doc, re.IGNORECASE)


def test_ordering_and_selection_are_deterministic(doc):
    assert "kickoff_unix, fixture_id" in doc, "ordering is not pinned"
    assert re.search(r"first\s+N", doc, re.IGNORECASE), "selection rule is not first-N"


def test_shortfall_handling_is_predeclared(doc):
    """The response to 'fewer than N qualify' must be decided BEFORE the count is known."""
    assert "15 – 59" in doc or "15 - 59" in doc, "the shortfall band is not predeclared"
    assert doc.count("STOP") >= 2, "shortfall handling does not say STOP"


def test_rule_was_frozen_before_any_sealed_scan(doc):
    assert "SEALED_947_PREFLIGHT_RUN = false" in doc
    assert not os.path.exists(
        "/home/ubuntu/research/hypothesis_engine/V8C_SEALED947_STRUCTURAL_PREFLIGHT.json"), (
        "a sealed-947 preflight artifact exists; the rule can no longer be called "
        "preregistered with respect to it")
