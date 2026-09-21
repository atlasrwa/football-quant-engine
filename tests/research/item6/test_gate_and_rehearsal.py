"""GATE falsifiability + rehearsal reproducibility tests.

The instrument must be able to BOTH pass and fail. We assert:
  - a synthetic 'rich' generator PASSES the frozen gate,
  - a synthetic 'poor' generator FAILS,
  - the deterministic control (ARM G-D) FAILS,
  - the stand-in rehearsal artifact reproduces byte-identically.
"""
from __future__ import annotations

import json
import subprocess

from src.research.item6 import stage1_gate
from src.research.item6.stage1_metrics import Stage1Endpoints

PY = "/home/ubuntu/.venv/bin/python"
REHEARSAL = "/home/ubuntu/research/item6/out/STANDIN_REHEARSAL.json"


def _ep(**kw):
    base = dict(
        n_fixtures=100, n_fixtures_abstained=0, n_mechanisms_total=500,
        baseline_equivalent_rate=0.2, semantic_duplicate_rate=0.1,
        novel_measurable_family_rate=0.9, novel_measurable_family_rate_mech=0.6,
        multivariable_interaction_rate=0.6, new_family_count=40,
        grounding_pass_rate=0.99, falsifiability_pass_rate=0.95,
        formalization_survival_rate=0.9, abstention_rate=0.0,
        f_class_counts={}, extension_family_ids=[],
    )
    base.update(kw)
    return Stage1Endpoints(**base)


def test_gate_passes_on_strong_endpoints():
    assert stage1_gate.evaluate_gate(_ep()).passed


def test_gate_fails_on_baseline_dominated():
    r = stage1_gate.evaluate_gate(_ep(baseline_equivalent_rate=0.95,
                                      novel_measurable_family_rate=0.0,
                                      new_family_count=0,
                                      multivariable_interaction_rate=0.0,
                                      formalization_survival_rate=0.0))
    assert not r.passed
    assert "BASELINE_EQUIVALENT_RATE" in r.failed_primary
    assert "NOVEL_MEASURABLE_FAMILY_RATE" in r.failed_primary


def test_gate_fails_on_high_duplication():
    r = stage1_gate.evaluate_gate(_ep(semantic_duplicate_rate=0.85))
    assert not r.passed
    assert "SEMANTIC_DUPLICATE_RATE" in r.failed_primary


def test_gate_fails_when_new_family_count_below_min():
    r = stage1_gate.evaluate_gate(_ep(new_family_count=2))
    assert not r.passed
    assert "NEW_FAMILY_COUNT" in r.failed_primary


def test_rehearsal_modes_behave_as_designed():
    data = json.load(open(REHEARSAL))
    res = data["results"]
    assert res["MODE_RICH"]["gate_passed"] is True
    assert res["MODE_POOR"]["gate_passed"] is False
    assert res["ARM_GD_CONTROL"]["gate_passed"] is False
    assert res["ARM_GD_CONTROL"]["n_novel_families"] == 0
    assert res["MODE_RICH"]["n_novel_families"] > 0


def test_rehearsal_reproduces_byte_identically():
    before = open(REHEARSAL, "rb").read()
    subprocess.run([PY, "research/item6/_run_standin_rehearsal.py"],
                   cwd="/home/ubuntu", check=True, capture_output=True)
    after = open(REHEARSAL, "rb").read()
    assert before == after, "stand-in rehearsal is not reproducible"
