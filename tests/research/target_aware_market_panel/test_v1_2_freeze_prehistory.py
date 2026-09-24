import json
from pathlib import Path

import pytest

from research.target_aware_market_panel import v1_2_freeze_prehistory as F


def test_freezer_is_outcome_blind_and_stats_only():
    src = Path("research/target_aware_market_panel/v1_2_freeze_prehistory.py").read_text()
    assert "settle" not in src.lower().replace("target settlement", "")
    for forbidden in ("/odds", "/lineups", "/injuries", "/player-stats", "/shotmap"):
        assert forbidden not in src
    assert '"target_outcomes_read": False' in src
    assert '"model_fit": False' in src
    assert '"oos_executed": False' in src


def test_exact_fixture_index_rejects_duplicates():
    d = {"n_finished_fixtures": 4994, "seasons": [
        {"competition_id": "c", "season_id": "s1", "fixture_ids": ["m"] * 4994}
    ]}
    with pytest.raises(RuntimeError, match="DUPLICATE_EXACT_FIXTURE_ID"):
        F.exact_fixture_index(d)


def test_terminal_wrapper_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "RAW_ROOT", tmp_path)
    mid = "mt_1"
    good = {
        "endpoint": f"/football/matches/{mid}/stats", "http_status": 200,
        "match_id": mid, "payload": {"data": {"match_id": mid}},
    }
    (tmp_path / f"{mid}.json").write_text(json.dumps(good))
    assert F.load_terminal(mid)["http_status"] == 200
    good["payload"]["data"]["match_id"] = "mt_other"
    (tmp_path / f"{mid}.json").write_text(json.dumps(good))
    with pytest.raises(RuntimeError, match="STATS_PAYLOAD_MATCH_ID_MISMATCH"):
        F.load_terminal(mid)


def test_404_must_have_null_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "RAW_ROOT", tmp_path)
    mid = "mt_2"
    bad = {
        "endpoint": f"/football/matches/{mid}/stats", "http_status": 404,
        "match_id": mid, "payload": {"unexpected": True},
    }
    (tmp_path / f"{mid}.json").write_text(json.dumps(bad))
    with pytest.raises(RuntimeError, match="HTTP_404_WITH_PAYLOAD"):
        F.load_terminal(mid)


def test_ledger_binds_terminal_sha_and_attempt_cap(tmp_path, monkeypatch):
    ledger = tmp_path / "attempts.jsonl"
    raw = tmp_path / "m.json"
    raw.write_text("{}")
    sha = F.fsha(raw)
    rows = [
        {"event": "REQUEST_START", "match_id": "m",
         "endpoint": "/football/matches/m/stats"},
        {"event": "REQUEST_TERMINAL", "match_id": "m", "raw_sha256": sha},
    ]
    ledger.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    monkeypatch.setattr(F, "LEDGER", ledger)
    got = F.audit_ledger({"m"}, {"m": sha})
    assert got["n_request_starts"] == 1
    rows.insert(1, rows[0])
    rows.insert(2, rows[0])
    ledger.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    with pytest.raises(RuntimeError, match="ATTEMPT_CAP_EXCEEDED"):
        F.audit_ledger({"m"}, {"m": sha})
