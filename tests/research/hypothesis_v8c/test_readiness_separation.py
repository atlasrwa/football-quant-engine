"""REPAIR 5: DEVELOPMENT_REHEARSAL_READY and CONFIRMATORY_READY are different claims.

`V8C_LEDGER_EVIDENCE_V1.json` reported `p1_open = 0` and P1-I CLOSED while its own
`known_limits` said K=8 remains OPEN. A gate that contradicts its own limitations section is
not machine-readable evidence.
"""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import defect_ledger as DL


def test_both_flags_exist_and_are_defined():
    for k in ("DEVELOPMENT_REHEARSAL_READY", "CONFIRMATORY_READY"):
        assert k in DL.READINESS_DEFINITIONS and DL.READINESS_DEFINITIONS[k]


def test_k8_is_an_open_confirmatory_requirement():
    r = DL.CONFIRMATORY_ONLY_REQUIREMENTS["K8_SET_LEVEL_FEASIBILITY"]
    assert r["status"] == DL.OPEN
    assert "CONFIRMATORY_READY" in r["blocks"]
    assert "DEVELOPMENT_REHEARSAL_READY" in r["does_not_block"]


def test_open_k8_blocks_confirmatory_but_not_development():
    out = DL.readiness({"p0_open": 0, "p1_open": 0})
    assert out["DEVELOPMENT_REHEARSAL_READY"] is True
    assert out["CONFIRMATORY_READY"] is False, (
        "an unproven K=8 requirement must block confirmatory readiness")
    assert "K8_SET_LEVEL_FEASIBILITY" in out["confirmatory_open_requirements"]


def test_an_open_requirement_cannot_be_closed_by_a_passing_algorithm_test():
    """The precise failure mode: maximum-matching works, therefore K=8 is fine. It is not."""
    from src.research.hypothesis_v8c import control_coverage as CC
    # the algorithm test genuinely passes ...
    best = CC._max_matching(["s2", "s1"], {"s2": ["c1", "c2"], "s1": ["c1"]})
    assert len(best) == 2
    # ... and the requirement is still OPEN.
    assert DL.CONFIRMATORY_ONLY_REQUIREMENTS["K8_SET_LEVEL_FEASIBILITY"]["status"] == DL.OPEN
    assert DL.readiness({"p0_open": 0, "p1_open": 0})["CONFIRMATORY_READY"] is False


def test_an_open_requirement_cannot_be_closed_by_artifact_presence():
    import os
    art = DL.CONFIRMATORY_ONLY_REQUIREMENTS["K8_SET_LEVEL_FEASIBILITY"]["artifact"]
    present = os.path.exists(f"/home/ubuntu/research/hypothesis_engine/{art}")
    if not present:
        pytest.skip("coverage artifact not in this checkout")
    assert DL.readiness({"p0_open": 0, "p1_open": 0})["CONFIRMATORY_READY"] is False, (
        "the artifact exists, and that must not close the requirement")


def test_p0_open_blocks_even_development_readiness():
    out = DL.readiness({"p0_open": 1, "p1_open": 0})
    assert out["DEVELOPMENT_REHEARSAL_READY"] is False
    assert out["CONFIRMATORY_READY"] is False


def test_readiness_is_derived_never_declared():
    out = DL.readiness({"p0_open": 0, "p1_open": 0})
    assert out["derived_not_declared"] is True
    assert out["development_ready_does_not_imply_confirmatory_ready"] is True


def test_live_model_resolution_is_open_under_mock_transport():
    r = DL.CONFIRMATORY_ONLY_REQUIREMENTS["LIVE_MODEL_RESOLUTION"]
    assert r["status"] == DL.OPEN
    assert any("mock" in c.lower() for c in r["cannot_be_closed_by"])
