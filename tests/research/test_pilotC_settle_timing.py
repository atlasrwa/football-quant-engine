"""Tests for FIX 2 — settlement timing / authoritative status refresh.

The settle pass must consult the AUTHORITATIVE /matches/{mid} status for any
committed-and-awaiting fixture regardless of league, rather than relying on a frozen
fixture-list status plus a kickoff+3h heuristic. This closes the same-day gap for
afternoon kickoffs: a fixture that finished this afternoon settles the SAME day via
its authoritative status even though the frozen list status still says "scheduled"
and it is well within the old kickoff+3h wait.
"""

import json
import sys
import time

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.forward.attestation_ledger import AttestationLedger
import pilotC_settle as settle


class _StubAPI:
    """Cache-first stub of thestatsapi_client for settlement.

    Returns a FINISHED match detail with a final score and gradeable stats for the
    configured fixture, so settlement can grade goals/corners without the network.
    """

    def __init__(self, mid, status="finished"):
        self.mid = mid
        self.status = status
        self.calls = []

    def get_json(self, path, params=None, cache_key=None, allow_status=(200,)):
        self.calls.append(path)
        if path.endswith("/stats"):
            data = {"data": {"overview": {
                "corner_kicks": {"all": {"home": 6, "away": 5}},
                "yellow_cards": {"all": {"home": 2, "away": 1}},
                "red_cards": {"all": {"home": 0, "away": 0}},
            }}}
            return data, {"http_status": 200, "from_cache": False, "cache_key": cache_key}
        # match detail
        data = {"data": {"status": self.status,
                         "score": {"home": 2, "away": 1}}}
        return data, {"http_status": 200, "from_cache": False, "cache_key": cache_key}


def test_afternoon_kickoff_settles_same_day_via_authoritative_status(
        tmp_path, monkeypatch):
    now = time.time()
    # Kickoff was ~2 hours ago — an afternoon kickoff that has FINISHED but is still
    # INSIDE the old kickoff+3h wait window. The frozen list status is stale
    # ("scheduled"). Only the authoritative status ("finished") can settle it today.
    kickoff = now - 2 * 3600
    mid = "mt_AFTERNOON"

    commit_ledger = tmp_path / "commitments.jsonl"
    reveal_ledger = tmp_path / "reveals.jsonl"
    settled_log = tmp_path / "settled_log.json"
    fixture_list = tmp_path / "fixture_list.json"
    pred_file = tmp_path / "predictions.json"

    # Pre-commit the prediction BEFORE (simulated) kickoff so reveal is allowed.
    class _Clock:
        def __init__(self, t): self.t = t
        def __call__(self): return self.t

    led = AttestationLedger(commit_path=commit_ledger, reveal_path=reveal_ledger,
                            clock=_Clock(kickoff - 3600))
    pred_id = f"pilotC:{mid}:corners:9.5"
    res = led.commit(prediction_id=pred_id, fixture_id=mid, model="corners_9.5",
                     kickoff_unix=kickoff, p_over=0.5, p_under=0.5,
                     reference_price=None)
    assert res.committed

    # Frozen fixture list says "scheduled" (stale) — the bug's trap.
    fixture_list.write_text(json.dumps({"meta": {
        mid: {"comp": "comp_8321", "home": "Leeds", "away": "Norwich",
              "ts": kickoff, "status": "scheduled"}}}))
    pred_file.write_text(json.dumps({"predictions": [
        {"match_id": mid, "market": "corners", "line": 9.5, "model_p": 0.5,
         "kickoff_ts": kickoff, "status": "scheduled"}]}))
    settled_log.write_text(json.dumps({"settled": []}))

    monkeypatch.setattr(settle, "PRED", str(pred_file))
    monkeypatch.setattr(settle, "LIST", str(fixture_list))
    monkeypatch.setattr(settle, "LOG", str(settled_log))
    monkeypatch.setattr(settle, "COMMIT_LEDGER", str(commit_ledger))
    monkeypatch.setattr(settle, "REVEAL_LEDGER", str(reveal_ledger))

    stub = _StubAPI(mid, status="finished")
    monkeypatch.setitem(sys.modules, "thestatsapi_client", stub)

    stats = settle.score(verbose=False)

    # Settled the SAME day via the authoritative status (NOT the kickoff+3h backstop,
    # which has not even elapsed yet).
    assert stats["settled_via_authoritative_status"] == 1
    assert stats["settled_via_kickoff_backstop"] == 0
    assert stats["graded"] == 1
    assert stats["revealed"] == 1

    # And the corners cell is genuinely revealed in the ledger.
    revealed = set(led.reveals_by_prediction().keys())
    assert pred_id in revealed


def test_future_kickoff_is_not_fetched_or_settled(tmp_path, monkeypatch):
    """A committed fixture whose kickoff is still in the FUTURE must be skipped
    without spending any budget (no API call)."""
    now = time.time()
    kickoff = now + 5 * 86400
    mid = "mt_FUTURE"

    commit_ledger = tmp_path / "commitments.jsonl"
    reveal_ledger = tmp_path / "reveals.jsonl"

    class _Clock:
        def __init__(self, t): self.t = t
        def __call__(self): return self.t

    led = AttestationLedger(commit_path=commit_ledger, reveal_path=reveal_ledger,
                            clock=_Clock(now))
    pred_id = f"pilotC:{mid}:corners:9.5"
    led.commit(prediction_id=pred_id, fixture_id=mid, model="corners_9.5",
               kickoff_unix=kickoff, p_over=0.5, p_under=0.5, reference_price=None)

    (tmp_path / "fixture_list.json").write_text(json.dumps({"meta": {
        mid: {"comp": "comp_8321", "home": "Leeds", "away": "Norwich",
              "ts": kickoff, "status": "scheduled"}}}))
    (tmp_path / "predictions.json").write_text(json.dumps({"predictions": [
        {"match_id": mid, "market": "corners", "line": 9.5, "model_p": 0.5,
         "kickoff_ts": kickoff, "status": "scheduled"}]}))
    (tmp_path / "settled_log.json").write_text(json.dumps({"settled": []}))

    monkeypatch.setattr(settle, "PRED", str(tmp_path / "predictions.json"))
    monkeypatch.setattr(settle, "LIST", str(tmp_path / "fixture_list.json"))
    monkeypatch.setattr(settle, "LOG", str(tmp_path / "settled_log.json"))
    monkeypatch.setattr(settle, "COMMIT_LEDGER", str(commit_ledger))
    monkeypatch.setattr(settle, "REVEAL_LEDGER", str(reveal_ledger))

    stub = _StubAPI(mid, status="finished")
    monkeypatch.setitem(sys.modules, "thestatsapi_client", stub)

    stats = settle.score(verbose=False)

    assert stats["skipped_awaiting_kickoff"] == 1
    assert stats["graded"] == 0
    assert stub.calls == [], "future fixture must NOT trigger any API call"
