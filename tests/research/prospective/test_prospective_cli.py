"""Tests for the prospective collector CLI."""

from __future__ import annotations

from pathlib import Path

from src.research.prospective.capture import ProspectiveApiClient
from src.research.prospective.cli import ProspectiveCollector, main
from src.research.prospective.storage import CaptureStore

KICKOFF = 1_700_000_000.0


def _odds_payload():
    return {"data": {"match_id": "mt_1", "bookmakers": [{
        "bookmaker": "Pinnacle",
        "markets": {"total_goals": {"2.5": {"over": {"last_seen": "1.90"},
                                            "under": {"last_seen": "2.00"}}}}}]}}


def _lineup_payload():
    return {"data": {"match_id": "mt_1", "confirmed": True,
        "home": {"id": "tm_h", "formation": "4-3-3",
                 "starting_xi": [{"id": "pl_1", "position": "G", "jersey_number": 1}],
                 "substitutes": []},
        "away": {"id": "tm_a", "formation": "4-4-2",
                 "starting_xi": [{"id": "pl_2", "position": "G", "jersey_number": 1}],
                 "substitutes": []}}}


def _make_collector(tmp_path, monkeypatch, responses):
    monkeypatch.setenv("THESTATSAPI_API_KEY", "k")

    def transport(url, headers, params):
        # Match by URL suffix so "/football/matches" (list) does not shadow the
        # per-match sub-paths "/odds" and "/lineups".
        if url.endswith("/odds"):
            frag = "/odds"
        elif url.endswith("/lineups"):
            frag = "/lineups"
        else:
            frag = "/football/matches"
        body = responses.get(frag)
        return (200, body) if body is not None else (404, None)

    client = ProspectiveApiClient(transport=transport)
    store = CaptureStore(path=tmp_path / "cap.jsonl")
    clock = iter([KICKOFF - 3600 + i for i in range(100)])
    return ProspectiveCollector(client, store, clock=lambda: next(clock)), store


def test_capture_odds_records_snapshot(tmp_path, monkeypatch):
    coll, store = _make_collector(tmp_path, monkeypatch, {"/odds": _odds_payload()})
    n = coll.capture_odds("mt_1", kickoff_ts=KICKOFF)
    assert n == 2  # over + under
    recs = list(store.read_all())
    assert all(r.raw_status == "PROSPECTIVE_SNAPSHOT" for r in recs)
    assert all(r.observed_at < KICKOFF for r in recs)


def test_capture_lineup_missing_handled(tmp_path, monkeypatch):
    coll, _ = _make_collector(tmp_path, monkeypatch, {"/lineups": None})
    assert coll.capture_lineup("mt_1") == 0  # 404 => graceful zero


def test_capture_upcoming_counts(tmp_path, monkeypatch):
    responses = {
        "/football/matches": {"data": [{"id": "mt_1"}]},
        "/odds": _odds_payload(),
        "/lineups": _lineup_payload(),
    }
    coll, store = _make_collector(tmp_path, monkeypatch, responses)
    result = coll.capture_upcoming(hours=30)
    assert result.fixtures_seen == 1
    assert result.odds_captured == 2
    assert result.lineups_captured == 1


def test_main_fails_closed_without_key(monkeypatch, capsys):
    monkeypatch.delenv("THESTATSAPI_API_KEY", raising=False)
    rc = main(["capture-odds", "--match", "mt_1"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "fails closed" in err
