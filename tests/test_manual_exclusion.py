"""Manual predictions must be STRUCTURALLY excluded from the Pilot C sample.

These tests are the enforcement proof requested in the manual-ledger brief: they assert
— against the real code, not by convention — that a manual prediction cannot appear in
Pilot C's settled sample, per-cell counts toward 385, or health enumeration.

The separation rests on two facts, both checked here:
  1. PATH separation: manual records live in data/forward/manual_*.jsonl /
     manual_settled_log.json; Pilot C only ever reads literal pilotC_* filenames (no
     directory glob), so a manual file is never enumerated.
  2. NAMESPACE separation: manual prediction_ids are "manual:...", never "pilotC:...",
     so even a hypothetical file mixup could not collide with a Pilot C id.
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import manual_predict as mp  # noqa: E402
from src.research.forward.attestation_ledger import AttestationLedger  # noqa: E402


# ── 1. STRUCTURAL: manual paths are distinct and never pilotC_* ──────────────

def test_manual_paths_are_distinct_from_pilotc():
    import pilotC_settle as settle
    import pilotC_forward_predict as fpred

    manual_paths = {
        mp.MANUAL_COMMIT_LEDGER, mp.MANUAL_REVEAL_LEDGER,
        mp.MANUAL_PRED_LOG, mp.MANUAL_SETTLED_LOG,
    }
    pilotc_paths = {
        settle.COMMIT_LEDGER, settle.REVEAL_LEDGER, settle.PRED, settle.LOG,
        fpred.COMMIT_LEDGER, fpred.REVEAL_LEDGER, fpred.OUT,
    }
    # No manual artifact shares a filename with any Pilot C artifact.
    assert manual_paths.isdisjoint(pilotc_paths)
    # And none of the manual filenames contain the pilotC ledger/log basenames.
    for p in manual_paths:
        base = Path(p).name
        assert "pilotC_commitments" not in base
        assert "pilotC_reveals" not in base
        assert "pilotC_forward_predictions" not in base
        assert "pilotC_settled_log" not in base


def test_manual_id_prefix_is_not_pilotc():
    pid = mp._pred_id("mt_TEST", "goals", 2.5)
    assert pid.startswith("manual:")
    assert not pid.startswith("pilotC:")


def test_pilotc_sample_readers_use_literal_paths_no_glob():
    """Guard against a future refactor that globs data/forward/*.jsonl (which WOULD
    pick up manual records). Pilot C's readers must reference literal pilotC_* names."""
    settle_src = Path("/home/ubuntu/scripts/pilotC_settle.py").read_text()
    loop_src = Path("/home/ubuntu/scripts/pilotC_forward_loop.py").read_text()
    # The sample enumerators must not glob the forward dir for ledgers/logs.
    assert "glob" not in _sample_reading_region(settle_src)
    # The per-cell tally reads the literal settled-log filename.
    assert "pilotC_settled_log.json" in loop_src
    assert "manual_" not in settle_src  # settle never references manual artifacts
    assert "manual_" not in loop_src


def _sample_reading_region(src: str) -> str:
    """The body of score() where the sample is enumerated — must not glob."""
    start = src.find("def score(")
    end = src.find("def topup(")
    return src[start:end if end > 0 else len(src)]


# ── 2. BEHAVIORAL: write manual records, run Pilot C readers, assert no leakage ─

@pytest.fixture
def isolated_manual(tmp_path, monkeypatch):
    """Point the manual module at temp files and write one committed+revealed record."""
    commit = tmp_path / "manual_commitments.jsonl"
    reveal = tmp_path / "manual_reveals.jsonl"
    pred = tmp_path / "manual_predictions.jsonl"
    settled = tmp_path / "manual_settled_log.json"
    monkeypatch.setattr(mp, "MANUAL_COMMIT_LEDGER", str(commit))
    monkeypatch.setattr(mp, "MANUAL_REVEAL_LEDGER", str(reveal))
    monkeypatch.setattr(mp, "MANUAL_PRED_LOG", str(pred))
    monkeypatch.setattr(mp, "MANUAL_SETTLED_LOG", str(settled))

    # Commit a manual prediction well before a far-future kickoff so it attests.
    led = AttestationLedger(commit_path=str(commit), reveal_path=str(reveal))
    future = 9_999_999_999.0
    pid = mp._pred_id("mt_MANUAL_TEST", "goals", 2.5)
    res = led.commit(prediction_id=pid, fixture_id="mt_MANUAL_TEST", model="goals_2.5",
                     kickoff_unix=future, p_over=0.55, p_under=0.45,
                     reference_price={"book": "betfair-exchange", "over_odds": 1.9,
                                      "under_odds": 2.1, "fair_p": 0.525, "overround": 0.01},
                     extra={"source": "manual", "p_over": 0.55, "p_under": 0.45})
    assert res.committed
    # Reveal it (as if settled) so it also exists in the manual reveal chain.
    rev = led.reveal(prediction_id=pid, fixture_id="mt_MANUAL_TEST", model="goals_2.5",
                     outcome={"actual": 1.0, "actual_value": 3, "model_p": 0.55,
                              "line": 2.5, "brier_contribution": 0.2025},
                     extra={"source": "manual"})
    assert rev.committed
    # Also write a manual settled-log row.
    settled.write_text(json.dumps({"settled": [{
        "source": "manual", "prediction_id": pid, "match_id": "mt_MANUAL_TEST",
        "market": "goals", "line": 2.5, "model_p": 0.55, "actual": 1.0,
        "actual_value": 3, "brier_contribution": 0.2025, "settled_at": "now"}],
        "n_settled_total": 1}))
    return {"pid": pid, "commit": commit, "reveal": reveal, "settled": settled}


def test_manual_record_absent_from_pilotc_commit_ledger(isolated_manual):
    """The Pilot C ledger (its real path) must not contain the manual prediction id."""
    import pilotC_settle as settle
    led = AttestationLedger(commit_path=settle.COMMIT_LEDGER, reveal_path=settle.REVEAL_LEDGER)
    pilotc_ids = set(led.commitments_by_prediction().keys())
    assert isolated_manual["pid"] not in pilotc_ids
    # And nothing in the real Pilot C ledger uses the manual namespace.
    assert not any(i.startswith("manual:") for i in pilotc_ids)


def test_manual_settled_row_absent_from_pilotc_per_cell_counts(isolated_manual):
    """_per_cell_settled_counts reads ONLY pilotC_settled_log.json — the manual settled
    row (in a different file) must not increment any cell."""
    loop = importlib.import_module("pilotC_forward_loop")
    counts = loop._per_cell_settled_counts()
    # The manual record is a goals@2.5 row; prove it did NOT leak into that cell by
    # comparing against the count derived from the Pilot C log alone.
    pilotc_log = Path("/home/ubuntu/data/discovery/pilotC_settled_log.json")
    expected = {f"{m}@{l}": 0 for m, l in loop.PREREG_CELLS}
    if pilotc_log.exists():
        data = json.loads(pilotc_log.read_text())
        for r in data.get("settled", []):
            cell = f"{r['market']}@{r['line']}"
            if cell in expected:
                expected[cell] += 1
    assert counts == expected  # identical => manual row contributed nothing

    # Stronger: none of the counted settled ids are the manual id.
    if pilotc_log.exists():
        ids = {r["prediction_id"] for r in json.loads(pilotc_log.read_text()).get("settled", [])}
        assert isolated_manual["pid"] not in ids
        assert not any(i.startswith("manual:") for i in ids)


def test_pilotc_settle_score_never_reveals_manual(isolated_manual, monkeypatch):
    """Run the REAL pilotC_settle.score() and assert it never touches the manual id.

    score() reveals against its hardcoded pilotC commit ledger; a manual id committed to
    a different file cannot be revealed by it. We stub the network fetch so the test is
    offline and deterministic."""
    import pilotC_settle as settle
    # Make settlement offline: pretend nothing is fetchable (grading returns ungradeable),
    # which is fine — we only assert the manual id is never in scope.
    monkeypatch.setattr(settle, "_fetch_final", lambda api, mid: {
        "home_goals": None, "away_goals": None, "total_goals": None,
        "total_corners": None, "total_cards": None})

    class _StubApi:
        def budget_snapshot(self):
            return {"last_monthly_remaining": "9999"}
    monkeypatch.setitem(sys.modules, "thestatsapi_client", _StubApi())

    stats = settle.score(verbose=False)
    # The manual reveal must not appear in the Pilot C reveal ledger.
    led = AttestationLedger(commit_path=settle.COMMIT_LEDGER, reveal_path=settle.REVEAL_LEDGER)
    pilotc_reveal_ids = set(led.reveals_by_prediction().keys())
    assert isolated_manual["pid"] not in pilotc_reveal_ids
    assert not any(i.startswith("manual:") for i in pilotc_reveal_ids)


def test_manual_commit_hash_independently_recomputable(isolated_manual, monkeypatch):
    """A published manual commitment hash must recompute from the record alone."""
    result = mp.verify_hash("mt_MANUAL_TEST")
    assert result["rows_checked"] >= 1
    assert all(d["recomputed_matches"] for d in result["detail"])
    assert result["chain_verifies"]
