"""The published-calibrated-prediction ledger must be STRUCTURALLY isolated from
Pilot C, Pipeline A, the manual predictor, and the edge scanner.

These tests are the enforcement proof for the new calibrated prediction engine's
attestation ledger (task 5 of the refocus brief; ground rule "separate ledger,
test-enforced isolation"). They assert — against the real code, not by convention —
that a calibrated attestation cannot appear in Pilot C's ledger, per-cell counts,
or settled sample, and vice versa.

The separation rests on two facts, both checked here:
  1. PATH separation: calibrated records live in data/forward/calibrated_*.jsonl /
     calibrated_*.json; Pilot C (and the others) only ever read their own literal
     filenames (no directory glob), so a calibrated file is never enumerated.
  2. NAMESPACE separation: calibrated prediction_ids are "calibrated:...", never
     "pilotC:...", "manual:...", or "flagged:...".

Plus: settled predictions are published whether right OR wrong; a published
commitment hash is independently recomputable; and no stake sizing exists in the
module.
"""
import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.forward.attestation_ledger import AttestationLedger  # noqa: E402
from src.research.prediction_engine import attestation as ca  # noqa: E402


# ── 1. STRUCTURAL: calibrated paths are distinct and never pilotC_/manual_/scanner_ ─

def test_calibrated_paths_are_distinct_from_all_pipelines():
    import pilotC_settle as settle
    import pilotC_forward_predict as fpred
    import manual_predict as mp
    import edge_scanner as es

    calibrated_paths = {
        ca.CALIBRATED_COMMIT_LEDGER, ca.CALIBRATED_REVEAL_LEDGER,
        ca.CALIBRATED_PREDICTIONS_LOG, ca.CALIBRATED_SETTLED_LOG,
    }
    pilotc_paths = {
        settle.COMMIT_LEDGER, settle.REVEAL_LEDGER, settle.PRED, settle.LOG,
        fpred.COMMIT_LEDGER, fpred.REVEAL_LEDGER, fpred.OUT,
    }
    manual_paths = {
        mp.MANUAL_COMMIT_LEDGER, mp.MANUAL_REVEAL_LEDGER,
        mp.MANUAL_PRED_LOG, mp.MANUAL_SETTLED_LOG,
    }
    scanner_paths = {
        es.SCANNER_FLAGGED_LOG, es.SCANNER_COMMIT_LEDGER, es.SCANNER_REVEAL_LEDGER,
        es.SCANNER_SETTLED_LOG, es.SCANNER_SCORECARD,
    }
    assert calibrated_paths.isdisjoint(pilotc_paths)
    assert calibrated_paths.isdisjoint(manual_paths)
    assert calibrated_paths.isdisjoint(scanner_paths)
    # And no calibrated filename contains any other pipeline's ledger basename,
    # nor the bare Pipeline A ledger.
    for p in calibrated_paths:
        base = Path(p).name
        assert "calibrated_" in base
        for reserved in ("pilotC_", "manual_", "scanner_"):
            assert reserved not in base
        assert base != "commitments.jsonl"


def test_calibrated_id_prefix_is_unique():
    pid = ca.calibrated_prediction_id("mt_TEST", "corners")
    assert pid.startswith("calibrated:")
    assert not pid.startswith("pilotC:")
    assert not pid.startswith("manual:")
    assert not pid.startswith("flagged:")


def test_calibrated_ledger_refuses_reserved_basenames(tmp_path):
    """Constructing the ledger with another pipeline's basename must be refused."""
    for bad in ("pilotC_commitments.jsonl", "manual_commitments.jsonl",
                "scanner_commitments.jsonl", "commitments.jsonl"):
        with pytest.raises(ValueError):
            ca.CalibratedAttestationLedger(commit_path=str(tmp_path / bad))


def test_pipelines_do_not_reference_calibrated_and_calibrated_does_not_reference_them():
    """No glob in Pilot C's sample reader, and no cross-references between the
    calibrated module and the other pipelines' ledger basenames."""
    settle_src = Path("/home/ubuntu/scripts/pilotC_settle.py").read_text()
    loop_src = Path("/home/ubuntu/scripts/pilotC_forward_loop.py").read_text()
    manual_src = Path("/home/ubuntu/scripts/manual_predict.py").read_text()
    scanner_src = Path("/home/ubuntu/scripts/edge_scanner.py").read_text()
    calibrated_src = Path(
        "/home/ubuntu/src/research/prediction_engine/attestation.py"
    ).read_text()

    # Pilot C's sample enumerator must still not glob the forward dir.
    assert "glob" not in _sample_reading_region(settle_src)
    # None of the other pipelines reference calibrated_* artifacts.
    for src in (settle_src, loop_src, manual_src, scanner_src):
        assert "calibrated_" not in src
    # The calibrated module never references another pipeline's ledger basenames.
    assert "pilotC_commitments" not in calibrated_src
    assert "pilotC_reveals" not in calibrated_src
    assert "pilotC_settled_log" not in calibrated_src
    assert "pilotC_forward_predictions" not in calibrated_src
    assert "manual_commitments" not in calibrated_src
    assert "manual_reveals" not in calibrated_src
    assert "scanner_commitments" not in calibrated_src
    assert "scanner_reveals" not in calibrated_src
    # And it never actually globs a directory (the word may appear in prose that
    # explains WHY it must not glob; guard the real call forms instead).
    assert "glob(" not in calibrated_src
    assert "import glob" not in calibrated_src


def _sample_reading_region(src: str) -> str:
    start = src.find("def score(")
    end = src.find("def topup(")
    return src[start:end if end > 0 else len(src)]


# ── 2. BEHAVIORAL: write a calibrated record, run Pilot C readers, assert no leak ─

@pytest.fixture
def isolated_calibrated(tmp_path):
    """A calibrated ledger on temp files with one committed+settled prediction."""
    commit = tmp_path / "calibrated_commitments.jsonl"
    reveal = tmp_path / "calibrated_reveals.jsonl"
    settled = tmp_path / "calibrated_settled_log.json"
    led = ca.CalibratedAttestationLedger(
        commit_path=str(commit), reveal_path=str(reveal), settled_log=str(settled)
    )
    future = 9_999_999_999.0
    res = led.commit_prediction(
        fixture_id="mt_CAL_TEST", market="corners", kickoff_unix=future,
        p_over=0.55, p_under=0.45,
        extra={"directional_call": "home takes more corners than away",
               "call_probability": 0.72, "window": 10, "status": "validated"},
    )
    assert res.committed
    return {"led": led, "commit": commit, "reveal": reveal, "settled": settled,
            "pid": ca.calibrated_prediction_id("mt_CAL_TEST", "corners")}


def test_calibrated_record_absent_from_pilotc_commit_ledger(isolated_calibrated):
    import pilotC_settle as settle
    led = AttestationLedger(commit_path=settle.COMMIT_LEDGER, reveal_path=settle.REVEAL_LEDGER)
    pilotc_ids = set(led.commitments_by_prediction().keys())
    assert isolated_calibrated["pid"] not in pilotc_ids
    assert not any(i.startswith("calibrated:") for i in pilotc_ids)


def test_calibrated_settled_row_absent_from_pilotc_per_cell_counts(isolated_calibrated):
    """Settle the calibrated prediction (into its OWN temp settled log), then confirm
    Pilot C's per-cell tally — which reads only pilotC_settled_log.json — is unchanged."""
    import importlib
    isolated_calibrated["led"].settle_prediction(
        fixture_id="mt_CAL_TEST", market="corners",
        outcome={"actual_value": 11, "over_line": 9.5, "hit": True},
    )
    loop = importlib.import_module("pilotC_forward_loop")
    counts = loop._per_cell_settled_counts()
    pilotc_log = Path("/home/ubuntu/data/discovery/pilotC_settled_log.json")
    expected = {f"{m}@{l}": 0 for m, l in loop.PREREG_CELLS}
    if pilotc_log.exists():
        data = json.loads(pilotc_log.read_text())
        for r in data.get("settled", []):
            cell = f"{r['market']}@{r['line']}"
            if cell in expected:
                expected[cell] += 1
    assert counts == expected  # calibrated settled row contributed nothing
    if pilotc_log.exists():
        ids = {r.get("prediction_id") for r in json.loads(pilotc_log.read_text()).get("settled", [])}
        assert isolated_calibrated["pid"] not in ids
        assert not any(str(i).startswith("calibrated:") for i in ids)


# ── 3. POLICY: settled predictions published whether right OR wrong ──────────────

def test_settled_published_whether_right_or_wrong(isolated_calibrated):
    led = isolated_calibrated["led"]
    # a MISS is still published
    led.settle_prediction(
        fixture_id="mt_CAL_TEST", market="corners",
        outcome={"actual_value": 6, "over_line": 9.5, "hit": False},
    )
    data = json.loads(isolated_calibrated["settled"].read_text())
    settled = data["settled"]
    assert len(settled) == 1
    assert settled[0]["outcome"]["hit"] is False  # the miss was published


# ── 4. INTEGRITY: commit hash independently recomputable; never backdated ────────

def test_calibrated_commit_hash_independently_recomputable(isolated_calibrated):
    res = ca.verify_commitment(
        isolated_calibrated["pid"],
        commit_path=str(isolated_calibrated["commit"]),
        reveal_path=str(isolated_calibrated["reveal"]),
    )
    assert res.found
    assert res.recomputed_matches
    assert res.pre_kickoff is True
    assert res.chain_ok


def test_calibrated_commit_refused_after_kickoff(tmp_path):
    """A prediction whose kickoff has passed cannot be committed (never backdated)."""
    led = ca.CalibratedAttestationLedger(
        commit_path=str(tmp_path / "calibrated_commitments.jsonl"),
        reveal_path=str(tmp_path / "calibrated_reveals.jsonl"),
        settled_log=str(tmp_path / "calibrated_settled_log.json"),
    )
    past = 1.0  # long past
    res = led.commit_prediction(
        fixture_id="mt_PAST", market="corners", kickoff_unix=past,
        p_over=0.5, p_under=0.5,
    )
    assert not res.committed
    assert "kicked off" in (res.reason or "")


# ── 5. NO STAKE SIZING anywhere in the calibrated attestation module ─────────────

def test_no_stake_sizing_in_calibrated_module():
    src = Path("/home/ubuntu/src/research/prediction_engine/attestation.py").read_text()
    tree = ast.parse(src)
    banned = ("kelly", "stake", "bankroll", "position_size")
    offending = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        for nm in names:
            if any(b in nm.lower() for b in banned):
                offending.append(nm)
    assert not offending, f"forbidden staking construct(s) in code: {sorted(set(offending))}"
