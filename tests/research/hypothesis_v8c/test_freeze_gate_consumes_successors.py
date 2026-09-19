"""AUDIT FINDING 7 (gate half): readiness cannot be certified without the successor artifacts.

The freeze gate derives its booleans from artifacts on disk. If the artifacts produced by the
composed run are not REQUIRED, the gate can certify readiness while the composed evidence is
absent -- i.e. from helper tests and declarations alone.
"""
from __future__ import annotations

from src.research.hypothesis_v8c import defect_ledger as DL
from src.research.hypothesis_v8c import freeze as F

SUCCESSORS = ("V8C_EXPOSED50_REHEARSAL_V2.json",
              "V8C_R_ACTION_SPACE_COVERAGE_V2.json",
              "V8C_LEDGER_EVIDENCE_V1.json")

NEW_MODULES = ("anchor", "control_coverage", "historical_similarity", "prompt")


def test_gate_requires_every_successor_artifact():
    required = {fn for fn, req in F.REQUIRED_ARTIFACTS.values() if req}
    missing = [a for a in SUCCESSORS if a not in required]
    assert not missing, f"the gate does not require {missing}"


def test_gate_binds_the_new_scientific_modules():
    """A change to any of these must invalidate a freeze certified under the old bytes."""
    missing = [m for m in NEW_MODULES if m not in F.CODE_MODULES]
    assert not missing, f"freeze manifest does not bind {missing}"


def test_absent_artifact_is_a_refusal_not_a_default_true():
    """Absent evidence must evaluate FALSE. Nothing may default to ready."""
    artifacts = {k: {"present": False, "sha256": None}
                 for k in F.REQUIRED_ARTIFACTS}
    code = {m: None for m in F.CODE_MODULES}      # code hashes present but artifacts absent
    verdict = F.evaluate_gate(artifacts=artifacts, code=code, inputs={})
    assert verdict["gate"] != "PASS", "the gate certified readiness with no artifacts at all"


def test_sealed947_preflight_artifact_is_still_required_and_absent():
    """Gate A does not authorise the reserve preflight, so its artifact must still be missing
    and the gate must still refuse on it."""
    import os
    assert F.REQUIRED_ARTIFACTS["sealed947_preflight"][1] is True
    assert not os.path.exists(
        "/home/ubuntu/research/hypothesis_engine/V8C_SEALED947_STRUCTURAL_PREFLIGHT.json")


def test_ledger_cannot_close_a_bound_defect_without_its_artifact():
    """P1-H and P1-I are artifact-gated as well as test-gated."""
    for did in ("P1-H-REAL-CORPUS-REACHABILITY", "P1-I-R-ACTION-SPACE-COVERAGE"):
        d = [x for x in DL.DEFECTS if x["id"] == did][0]
        assert d.get("required_artifact"), f"{did} is not artifact-gated"
        r = DL.evaluate(d["required_evidence"],
                        artifact_dir="/nonexistent",
                        evidence_binding={did: {"code_hashes": DL.module_hashes(
                            d["bound_modules"]), "commit": "X"}})
        row = [x for x in r["defects"] if x["id"] == did][0]
        assert row["status"] == DL.OPEN
