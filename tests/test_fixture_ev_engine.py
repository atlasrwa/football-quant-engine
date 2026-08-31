"""Safety and behavior tests for the on-demand fixture EV engine."""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")
import fixture_ev_engine as eng  # noqa: E402


def _match(mid, date, home="Aston Villa", away="Arsenal"):
    return {"id": mid, "date_unix": date, "home_name": home, "away_name": away,
            "homeGoalCount": 1, "awayGoalCount": 1, "totalGoalCount": 2,
            "team_a_xg": 1.2, "team_b_xg": 1.0, "team_a_shots": 10,
            "team_b_shots": 9, "team_a_shotsOnTarget": 4, "team_b_shotsOnTarget": 3,
            "team_a_possession": 52, "team_b_possession": 48, "team_a_corners": 5,
            "team_b_corners": 4, "team_a_yellow_cards": 2, "team_b_yellow_cards": 2,
            "team_a_fouls": 10, "team_b_fouls": 11, "team_a_attacks": 90,
            "team_b_attacks": 85, "team_a_dangerous_attacks": 40,
            "team_b_dangerous_attacks": 38}


def test_two_season_history_is_strictly_before_cutoff(monkeypatch):
    cutoff = 1_000.0
    rows = [_match("before", 999), _match("equal", 1000), _match("after", 1001)]
    monkeypatch.setattr(eng, "_load_season_pages", lambda sid: rows)
    monkeypatch.setattr(eng, "hydrate_history_from_thestats",
                        lambda *a, **k: ([], {"used": True, "live_requests": 0,
                                              "missing_seasons": [], "errors": [], "note": "test"}))
    selected, meta = eng.load_two_season_history("Aston Villa", "Arsenal", cutoff)
    assert [m["id"] for m in selected] == ["before"]
    assert meta["strict_cutoff_unix"] == cutoff
    assert meta["latest_history_unix"] < cutoff


def test_missing_history_uses_thestatsapi_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(eng, "_load_season_pages", lambda sid: [])
    def fallback(home, away, cutoff, missing):
        calls.append((home, away, cutoff, missing))
        return [_match("api-row", cutoff-1)], {"used": True, "live_requests": 1,
            "missing_seasons": [s for s, _ in missing], "errors": [],
            "note": "TheStatsAPI fallback"}
    monkeypatch.setattr(eng, "hydrate_history_from_thestats", fallback)
    selected, meta = eng.load_two_season_history("Aston Villa", "Arsenal", 2000)
    assert calls, "TheStatsAPI fallback must run when required data is not cached"
    assert selected[0]["id"] == "api-row"
    assert meta["fallback"]["used"] is True


def test_thestats_adapter_never_proxies_unavailable_fields():
    fx = {"id": "mt_x", "utc_date": "2026-01-01T12:00:00Z",
          "home_team": {"name": "Aston Villa"}, "away_team": {"name": "Arsenal"},
          "score": {"home": 2, "away": 1}}
    payload = {"data": {"overview": {
        "total_shots": {"all": {"home": 12, "away": 8}},
        "shots_on_target": {"all": {"home": 5, "away": 3}},
    }}}
    row = eng.adapt_thestats_fixture(fx, payload)
    assert row["team_a_shots"] == 12
    for field in ("attacks", "dangerous_attacks", "freekicks", "throwins"):
        assert row[f"team_a_{field}"] == -1
        assert row[f"team_b_{field}"] == -1


def test_uncertainty_gate_is_conservative():
    # A 5pp raw edge should not survive the default finite-history uncertainty for
    # a 76-match/team context around a 50% outcome.
    uncertainty = eng.uncertainty_pp(0.5, 76, 0.01)
    adjusted = 5.0 - uncertainty - eng.COMMISSION_BUFFER_PP
    assert uncertainty > 5.0
    assert adjusted < 0


def test_recent_odds_cache_costs_zero_live_requests(tmp_path, monkeypatch):
    ch = tmp_path / "ch"; ch.mkdir()
    monkeypatch.setattr(eng, "CH", ch)
    payload = {"data": {"bookmakers": [{"markets": {"btts": {
        "yes": {"last_seen": 2.0}, "no": {"last_seen": 2.0}}}}]}}
    for book in eng.BOOKS:
        p = ch / f"pilotC_odds_mt_test_{book}.json"
        p.write_text(json.dumps(payload)); os.utime(p, (time.time(), time.time()))

    class FakeApi:
        MAX_LIVE_REQUESTS = 100
        @staticmethod
        def live_requests_made(): return 0
        @staticmethod
        def budget_snapshot(): return {"last_monthly_remaining": "100", "last_monthly_limit": "10000"}
        @staticmethod
        def get_json(*args, **kwargs): raise AssertionError("must not fetch recent cache")
    monkeypatch.setitem(sys.modules, "thestatsapi_client", FakeApi)
    raw, usage = eng.capture_odds("mt_test", tmp_path / "sources")
    assert set(raw) == set(eng.BOOKS)
    assert usage["live_requests"] == 0
    assert len(usage["sources"]) == 3


def test_research_paths_are_structurally_separate_from_pilotc():
    import pilotC_settle
    research = {str(eng.RESEARCH_COMMIT_LEDGER), str(eng.RESEARCH_REVEAL_LEDGER),
                str(eng.RESEARCH_ROOT)}
    pilotc = {pilotC_settle.COMMIT_LEDGER, pilotC_settle.REVEAL_LEDGER,
              pilotC_settle.PRED, pilotC_settle.LOG}
    assert research.isdisjoint(pilotc)
    assert all("pilotC_commitments" not in p and "pilotC_settled_log" not in p for p in research)


def test_validated_crosswalk_resolves_target_teams():
    cross = eng.validated_crosswalk("Aston Villa", "Arsenal")
    assert cross["Aston Villa"]["thestats_id"] == "tm_1002"
    assert cross["Arsenal"]["thestats_id"] == "tm_9145"
    assert all(r["confidence"] == 1.0 for r in cross.values())



def test_partial_season_cache_triggers_completion(monkeypatch):
    calls = []
    partial = [_match(f"m{i}", 100+i) for i in range(100)]
    monkeypatch.setattr(eng, "_load_season_pages", lambda sid: partial)
    def hydrate(home, away, cutoff, missing):
        calls.extend(missing)
        return [], {"used": True, "live_requests": 0,
                    "missing_seasons": [s for s, _ in missing], "errors": [], "note": "complete pages"}
    monkeypatch.setattr(eng, "hydrate_history_from_thestats", hydrate)
    eng.load_two_season_history("Aston Villa", "Arsenal", 10_000)
    assert len(calls) == 2
    assert all(meta["cached_match_count"] == 100 for _, meta in calls)
    assert all(meta["expected_match_count"] == 380 for _, meta in calls)


def test_fallback_rows_enter_inference_history_without_refitting():
    canonical = [_match("canonical", 100)]
    fallback = _match("api-new", 200)
    fallback["_source"] = "thestatsapi_fallback"
    merged = eng.merge_inference_history(canonical, [fallback])
    assert [m["id"] for m in merged] == ["canonical", "api-new"]
    hist = eng.mix.build_histories(merged)
    assert any(m["id"] == "api-new" for _, m, _ in hist["Aston Villa"])


def test_history_and_odds_caps_are_independent(tmp_path, monkeypatch):
    ch = tmp_path / "ch"; ch.mkdir(); monkeypatch.setattr(eng, "CH", ch)
    payload = {"data": {"bookmakers": [{"markets": {"btts": {
        "yes": {"last_seen": 2.0}, "no": {"last_seen": 2.0}}}}]}}
    class FakeApi:
        MAX_LIVE_REQUESTS = 999
        made = 5
        root = ch
        @classmethod
        def live_requests_made(cls): return cls.made
        @classmethod
        def budget_snapshot(cls): return {"last_monthly_remaining": "95", "last_monthly_limit": "10000"}
        @classmethod
        def cache_path(cls, key): return str(cls.root / f"{key}.json")
        @classmethod
        def get_json(cls, path, params, cache_key, allow_status):
            assert cls.made < cls.MAX_LIVE_REQUESTS
            cls.made += 1
            Path(cls.cache_path(cache_key)).write_text(json.dumps(payload))
            return payload, {"from_cache": False}
    monkeypatch.setitem(sys.modules, "thestatsapi_client", FakeApi)
    raw, usage = eng.capture_odds("mt_uncached", tmp_path / "sources", refresh=True)
    assert usage["live_requests"] == 3
    assert FakeApi.MAX_LIVE_REQUESTS == 5 + eng.MAX_ODDS_REQUESTS
    assert set(raw) == set(eng.BOOKS)


def test_refresh_keys_are_collision_resistant(tmp_path, monkeypatch):
    ch = tmp_path / "ch"; ch.mkdir(); monkeypatch.setattr(eng, "CH", ch)
    keys = []
    payload = {"data": {"bookmakers": [{"markets": {"btts": {
        "yes": {"last_seen": 2.0}, "no": {"last_seen": 2.0}}}}]}}
    class FakeApi:
        MAX_LIVE_REQUESTS = 999; made = 0
        @classmethod
        def live_requests_made(cls): return cls.made
        @classmethod
        def budget_snapshot(cls): return {}
        @classmethod
        def cache_path(cls, key): return str(ch / f"{key}.json")
        @classmethod
        def get_json(cls, path, params, cache_key, allow_status):
            keys.append(cache_key); cls.made += 1
            Path(cls.cache_path(cache_key)).write_text(json.dumps(payload))
            return payload, {}
    monkeypatch.setitem(sys.modules, "thestatsapi_client", FakeApi)
    eng.capture_odds("mt_x", tmp_path / "s1", refresh=True)
    eng.capture_odds("mt_x", tmp_path / "s2", refresh=True)
    assert len(keys) == 6
    assert len(set(keys)) == 6


def test_post_kickoff_report_is_rejected_before_data_access(monkeypatch):
    monkeypatch.setattr(eng, "resolve_fixture", lambda fid: {
        "fixture_id": fid, "home": "Aston Villa", "away": "Arsenal",
        "kickoff_unix": time.time()-1, "kickoff_iso": "past"})
    with pytest.raises(ValueError, match="already kicked off"):
        eng.build_report("mt_past", "tester")


def test_duplicate_attestation_must_match_content(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "RESEARCH_COMMIT_LEDGER", tmp_path / "commits.jsonl")
    monkeypatch.setattr(eng, "RESEARCH_REVEAL_LEDGER", tmp_path / "reveals.jsonl")
    report = {"request_id": "req-fixed", "requested_by": "tester",
              "fixture": {"fixture_id": "mt_x", "kickoff_unix": 9_999_999_999.0},
              "source_hashes": {"betfair-exchange": "abc"}, "summary": {},
              "markets": [{"market": "goals", "line": 2.5,
                           "model_p_over_or_yes": 0.55, "decision": "NO OPPORTUNITY",
                           "books": {"betfair-exchange": [
                               {"side": "over/yes", "decimal_odds": 1.9, "fair_p": 0.52, "overround": 0.01},
                               {"side": "under/no", "decimal_odds": 2.1, "fair_p": 0.48, "overround": 0.01}]}}]}
    first = eng.commit_report(report)
    assert first["rows"][0]["attested"]
    # Exact replay is idempotent.
    second = eng.commit_report(report)
    assert second["rows"][0]["existing"]
    # Same prediction id with changed probability/report content must be rejected.
    report["markets"][0]["model_p_over_or_yes"] = 0.60
    with pytest.raises(eng.LedgerTamperError, match="conflicts"):
        eng.commit_report(report)


def test_real_pilotc_ledger_contains_no_fixture_research_ids():
    path = Path("/home/ubuntu/data/forward/pilotC_commitments.jsonl")
    if path.exists():
        assert "fixture-research:" not in path.read_text()



def test_cross_provider_overlap_deduplicates_by_fixture_identity():
    local = _match("7466677", 1_700_000_000, home="Aston Villa", away="AFC Bournemouth")
    api = dict(local); api["id"] = "mt_123"; api["away_name"] = "Bournemouth"
    api["_source"] = "thestatsapi_fallback"
    merged = eng.merge_inference_history([local], [api])
    assert len(merged) == 1
    assert eng.fixture_identity(local) == eng.fixture_identity(api)


def test_empty_cache_fallback_can_reach_minimum_supported_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(eng, "TS_CACHE", tmp_path / "ts")
    monkeypatch.setattr(eng, "CH", tmp_path / "ch")
    (tmp_path / "ts").mkdir(); (tmp_path / "ch").mkdir()
    monkeypatch.setattr(eng, "_find_cached_stats", lambda mid: None)
    monkeypatch.setattr(eng, "validated_crosswalk", lambda h, a: {
        h: {"thestats_id": "tm_home"}, a: {"thestats_id": "tm_away"}})

    fixtures = []
    for i in range(30):
        fixtures.append({"id": f"v{i}", "utc_date": f"2025-01-{(i%28)+1:02d}T12:00:00Z",
                         "home_team": {"id": "tm_home", "name": "Aston Villa"},
                         "away_team": {"id": f"oppv{i}", "name": f"Opp V {i}"},
                         "score": {"home": 1, "away": 0}})
        fixtures.append({"id": f"a{i}", "utc_date": f"2025-02-{(i%28)+1:02d}T12:00:00Z",
                         "home_team": {"id": "tm_away", "name": "Arsenal"},
                         "away_team": {"id": f"oppa{i}", "name": f"Opp A {i}"},
                         "score": {"home": 2, "away": 1}})
    stats = {"data": {"overview": {
        "expected_goals": {"all": {"home": 1.5, "away": 0.8}},
        "total_shots": {"all": {"home": 12, "away": 8}},
        "shots_on_target": {"all": {"home": 5, "away": 3}},
        "ball_possession": {"all": {"home": 55, "away": 45}},
        "corner_kicks": {"all": {"home": 6, "away": 4}},
        "yellow_cards": {"all": {"home": 2, "away": 2}},
        "red_cards": {"all": {"home": 0, "away": 0}},
        "fouls": {"all": {"home": 10, "away": 11}}},
        "shots": {"shots_off_target": {"all": {"home": 4, "away": 3}}}}}
    class FakeApi:
        MAX_LIVE_REQUESTS = 999; made = 0
        @classmethod
        def live_requests_made(cls): return cls.made
        @classmethod
        def get_json(cls, path, params=None, cache_key=None, allow_status=(200,)):
            assert cls.made < cls.MAX_LIVE_REQUESTS
            cls.made += 1
            if path == "/football/matches": return {"data": fixtures}, {}
            return stats, {}
    monkeypatch.setitem(sys.modules, "thestatsapi_client", FakeApi)
    rows, info = eng.hydrate_history_from_thestats(
        "Aston Villa", "Arsenal", 2_000_000_000,
        [("s", {"thestats_id": "sn_test"})])
    counts = eng.supported_context_counts(rows, ("Aston Villa", "Arsenal"))
    assert counts == {"Aston Villa": 30, "Arsenal": 30}
    assert info["live_requests"] <= eng.MAX_HISTORY_REQUESTS
    assert info["selected_stats_fixtures"] == 60


def test_odds_capture_rechecks_kickoff_during_run(tmp_path, monkeypatch):
    ch = tmp_path / "ch"; ch.mkdir(); monkeypatch.setattr(eng, "CH", ch)
    payload = {"data": {"bookmakers": [{"markets": {"btts": {
        "yes": {"last_seen": 2.0}, "no": {"last_seen": 2.0}}}}]}}
    for book in eng.BOOKS:
        (ch / f"pilotC_odds_mt_cross_{book}.json").write_text(json.dumps(payload))
    times = iter([999.0, 999.0, 1001.0])
    monkeypatch.setattr(eng.time, "time", lambda: next(times))
    class FakeApi:
        MAX_LIVE_REQUESTS = 99
        @staticmethod
        def live_requests_made(): return 0
        @staticmethod
        def budget_snapshot(): return {}
        @staticmethod
        def get_json(*a, **k): raise AssertionError("should cross kickoff before fetch")
    monkeypatch.setitem(sys.modules, "thestatsapi_client", FakeApi)
    with pytest.raises(ValueError, match="crossed kickoff"):
        eng.capture_odds("mt_cross", tmp_path / "sources", kickoff_unix=1000.0)
