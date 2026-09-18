"""P1-G: the freeze gate must not accept self-certification or stale evidence."""
from __future__ import annotations

import json

from src.research.hypothesis_v8c import defect_ledger as DL
from src.research.hypothesis_v8c import freeze as F
from src.research.hypothesis_v8c import provenance as PROV


# ---- the ledger derives, it does not read ------------------------------------------------
def test_ledger_with_no_evidence_reports_everything_open():
    r = DL.evaluate([])
    assert r["p0_open"] == r["p0_total"] > 0
    assert r["p1_open"] == r["p1_total"] > 0


def test_ledger_closes_only_on_actual_passed_nodes():
    closed = next(d for d in DL.DEFECTS
                  if d["id"] == "P0-B-EXTERNAL-FREEZE-ANCHOR")
    r = DL.evaluate(closed["required_evidence"])
    row = next(x for x in r["defects"] if x["id"] == closed["id"])
    assert row["status"] == DL.CLOSED
    # drop ONE required node -> immediately OPEN again
    r2 = DL.evaluate(closed["required_evidence"][:-1])
    row2 = next(x for x in r2["defects"] if x["id"] == closed["id"])
    assert row2["status"] == DL.OPEN
    assert row2["missing_evidence"]


def test_hand_written_p0_open_zero_cannot_pass(tmp_path, monkeypatch):
    """THE P1-G CASE: an artifact simply declaring p0_open=0 must not satisfy the gate."""
    monkeypatch.setattr(F, "ENG", str(tmp_path))
    art = {"p0_open": 0, "p1_open": 0, "new_sonnet_calls": 0,
           "outcome_seal": "PASS", "cache_isolation": "PASS"}
    art[PROV.PROVENANCE_KEY] = PROV.stamp()          # even WITH valid provenance
    (tmp_path / "V8C_TEST_RESULTS.json").write_text(json.dumps(art))

    v = F.evaluate_gate()
    assert v["conditions"]["P0_OPEN_ZERO"]["value"] is False
    assert v["conditions"]["P1_OPEN_ZERO"]["value"] is False
    assert any("no test-outcome evidence" in r for r in v["failed_reasons"])


def test_declared_p0_open_zero_is_ignored_even_with_passed_nodes(tmp_path, monkeypatch):
    """The literal is never consulted: openness comes from the node list alone."""
    monkeypatch.setattr(F, "ENG", str(tmp_path))
    art = {"p0_open": 0, "p1_open": 0, "passed_node_ids": []}   # lies, with an empty node list
    art[PROV.PROVENANCE_KEY] = PROV.stamp()
    (tmp_path / "V8C_TEST_RESULTS.json").write_text(json.dumps(art))
    v = F.evaluate_gate()
    assert v["conditions"]["P0_OPEN_ZERO"]["value"] is False
    ev = v["conditions"]["P0_OPEN_ZERO"]["evidence"]
    assert ev["derivation"] == "defect_ledger.evaluate(passed_node_ids)"
    assert ev["open_ids"], "the gate did not name what is still open"


# ---- stale evidence --------------------------------------------------------------------
def test_artifact_without_provenance_cannot_satisfy_a_condition(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ENG", str(tmp_path))
    (tmp_path / "V8C_PIT_ADVERSARIAL_RESULTS.json").write_text(json.dumps({"verdict": "PASS"}))
    v = F.evaluate_gate()
    assert v["conditions"]["PIT_PASS"]["value"] is False
    assert any("no provenance block" in str(r) for r in v["failed_reasons"])


def test_stale_evidence_from_older_code_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ENG", str(tmp_path))
    art = {"verdict": "PASS"}
    p = PROV.stamp()
    p["producer_code_hashes"]["grammar"] = "0" * 64          # produced by different code
    art[PROV.PROVENANCE_KEY] = p
    (tmp_path / "V8C_PIT_ADVERSARIAL_RESULTS.json").write_text(json.dumps(art))
    v = F.evaluate_gate()
    assert v["conditions"]["PIT_PASS"]["value"] is False
    assert any("STALE EVIDENCE" in r for r in v["failed_reasons"])


def test_ledger_change_invalidates_prior_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ENG", str(tmp_path))
    art = {"verdict": "PASS"}
    p = PROV.stamp()
    p["ledger_hash"] = "0" * 64
    art[PROV.PROVENANCE_KEY] = p
    (tmp_path / "V8C_PIT_ADVERSARIAL_RESULTS.json").write_text(json.dumps(art))
    v = F.evaluate_gate()
    assert v["conditions"]["PIT_PASS"]["value"] is False


def test_fresh_provenance_verifies():
    art = {"verdict": "PASS", PROV.PROVENANCE_KEY: PROV.stamp(corpus_hash="c")}
    assert PROV.verify(art, expect_corpus="c")["ok"] is True
    assert PROV.verify(art, expect_corpus="different")["ok"] is False


# ---- the gate itself --------------------------------------------------------------------
def test_gate_has_no_override_flag():
    st = F.version_stamp()
    assert st["override_flag"] is None
    assert st["hand_written_p0_open_zero_can_pass"] is False
    assert st["stale_artifact_from_older_code"] == "FAIL"
    assert st["absent_evidence_evaluates_to"] is False


def test_gate_refuses_with_nothing_present(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ENG", str(tmp_path))
    v = F.evaluate_gate()
    assert v["gate"] == "REFUSED"
    assert all(not v["conditions"][k]["value"] for k in F.GATE_CONDITIONS
               if k != "CHAMPION_UNCHANGED")
