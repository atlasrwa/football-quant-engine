import json
from pathlib import Path

from research.target_aware_market_panel import v1_2_stats_backfill as B


def test_backfill_plan_is_exact_and_stats_only():
    p = json.loads(Path("research/target_aware_market_panel/V1_2_STATS_BACKFILL_PLAN_V1.json").read_text())
    assert p["n_exact_fixture_ids"] == 4994
    assert p["endpoint_template"] == "/football/matches/{match_id}/stats"
    assert p["request_policy"]["hidden_client_retries"] == 0
    assert p["request_policy"]["minimum_interval_seconds"] == 1.0
    assert p["request_policy"]["concurrency"] == 1
    assert p["request_policy"]["max_process_attempts_per_unresolved_id"] == 2
    assert set(p["forbidden_calls"]) == {"odds", "lineups", "injuries", "player-stats", "shotmap"}


def test_runner_has_no_forbidden_provider_endpoints():
    src = Path("research/target_aware_market_panel/v1_2_stats_backfill.py").read_text()
    assert 'f"{BASE_URL}/football/matches/{mid}/stats"' in src
    for forbidden in ("/odds", "/lineups", "/injuries", "/player-stats", "/shotmap"):
        assert forbidden not in src
    assert "target_outcomes_read" in src
    assert "model_fit" in src
    assert "oos_executed" in src


def test_exact_ids_are_bound_to_frozen_discovery():
    ids = B.load_exact_ids()
    assert len(ids) == 4994
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_terminal_wrapper_validation_and_skip_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "RAW_ROOT", tmp_path)
    mid = "mt_123"
    assert B.terminal_wrapper(mid) is None
    good = {
        "provider": "thestatsapi",
        "match_id": mid,
        "endpoint": f"/football/matches/{mid}/stats",
        "retrieved_at_unix": 1,
        "retrieved_at_utc": "x",
        "http_status": 200,
        "payload": {"data": {}},
    }
    B.atomic_json(B.raw_path(mid), good)
    assert B.terminal_wrapper(mid)["http_status"] == 200
    bad = dict(good, http_status=500)
    B.atomic_json(B.raw_path(mid), bad)
    try:
        B.terminal_wrapper(mid)
    except RuntimeError:
        pass
    else:
        raise AssertionError("non-terminal wrapper did not fail closed")


def test_attempt_ledger_counts_only_request_starts(tmp_path, monkeypatch):
    ledger = tmp_path / "attempts.jsonl"
    monkeypatch.setattr(B, "LEDGER", ledger)
    B.append_ledger({"event": "REQUEST_START", "match_id": "mt_1"})
    B.append_ledger({"event": "REQUEST_TERMINAL", "match_id": "mt_1"})
    B.append_ledger({"event": "REQUEST_START", "match_id": "mt_2"})
    assert B.attempt_counts() == {"mt_1": 1, "mt_2": 1}
