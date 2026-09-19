"""AUDIT FINDING 7: ledger closures must be bound to evidence, and stale evidence must not close.

P1-A/B/E/H/I were forced OPEN by a `status_override`. Removing the override is not a repair --
flipping them CLOSED on a passing node id alone would let evidence produced against DIFFERENT
code certify the code running now. These tests pin the binding.
"""
from __future__ import annotations

from src.research.hypothesis_v8c import defect_ledger as DL

BOUND = ("P1-A-REAL-SONNET-RUNNER", "P1-B-PROMPT-TOOL-CONTRACT", "P1-E-TREATMENT-PROVENANCE",
         "P1-H-REAL-CORPUS-REACHABILITY", "P1-I-R-ACTION-SPACE-COVERAGE")


def _defect(did):
    return [d for d in DL.DEFECTS if d["id"] == did][0]


def _all_nodes():
    nodes = set()
    for d in DL.DEFECTS:
        nodes.update(d.get("required_evidence") or ())
    return nodes


def test_no_defect_is_forced_open_by_an_override():
    forced = [d["id"] for d in DL.DEFECTS if d.get("status_override")]
    assert not forced, f"status_override still forces {forced}"


def test_every_previously_forced_defect_declares_real_evidence():
    for did in BOUND:
        d = _defect(did)
        assert d["required_evidence"], f"{did} declares no required evidence"
        assert d["repair"], f"{did} declares no repair"
        assert d.get("bound_modules"), f"{did} binds no producer modules"


def test_passing_nodes_alone_cannot_close_a_bound_defect():
    """Without an evidence binding, a bound defect stays OPEN even with every node passing."""
    r = DL.evaluate(_all_nodes())
    for did in BOUND:
        row = [x for x in r["defects"] if x["id"] == did][0]
        assert row["status"] == DL.OPEN
        assert any("evidence binding" in m for m in row["missing_evidence"])


def test_current_code_binding_permits_closure():
    binding = {did: {"code_hashes": DL.module_hashes(_defect(did)["bound_modules"]),
                     "commit": "TEST"} for did in BOUND}
    r = DL.evaluate(_all_nodes(), evidence_binding=binding)
    for did in BOUND:
        row = [x for x in r["defects"] if x["id"] == did][0]
        # Artifact-gated defects may still be OPEN on a missing artifact; the staleness term
        # must not be what is missing.
        assert not any("STALE" in m or "evidence binding" in m
                       for m in row["missing_evidence"]), row["missing_evidence"]


def test_changed_bound_code_invalidates_the_evidence():
    """THE point: evidence produced against other code must not close a defect."""
    did = "P1-A-REAL-SONNET-RUNNER"
    binding = {did: {"code_hashes": {m: "0" * 64 for m in _defect(did)["bound_modules"]},
                     "commit": "STALE"}}
    r = DL.evaluate(_all_nodes(), evidence_binding=binding)
    row = [x for x in r["defects"] if x["id"] == did][0]
    assert row["status"] == DL.OPEN
    assert any("STALE" in m for m in row["missing_evidence"])


def test_artifact_gated_defects_name_a_successor_artifact():
    assert _defect("P1-H-REAL-CORPUS-REACHABILITY")["required_artifact"] \
        == "V8C_EXPOSED50_REHEARSAL_V2.json"
    assert _defect("P1-I-R-ACTION-SPACE-COVERAGE")["required_artifact"] \
        == "V8C_R_ACTION_SPACE_COVERAGE_V2.json"


def test_similarity_self_inclusion_finding_stays_repaired():
    n1 = [f for f in DL.NEW_FINDINGS if f["id"].startswith("N1")][0]
    assert n1["status"] == DL.REPAIRED
    assert n1["severity"] == "P0"
