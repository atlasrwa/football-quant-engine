"""Regression tests for the fixture-universe refresh operational repair.

Context (DATA ACCUMULATION MODE, ops repair only)
-------------------------------------------------
The shared discovered fixture universe
(``data/thestatsapi/championship/_pilotC_fixture_list.json``) is watched by the
forecast-broadcast heartbeat's ``check_stale_fixture_universe`` (36h stale-inflow
threshold). Its only frequent refresher was lost when Pilot C was deprecated; the
surviving twice-weekly cron entry (72h gap) cannot keep it under 36h. The repair adds
an independent 6-hourly systemd timer that reuses the EXISTING discovery command
(``scripts/pilotC_fixture_discovery.py``) unchanged.

These tests prove the mission's required properties WITHOUT any network call:
 1. a fresh universe does not trigger stale status
 2. a stale universe does trigger stale status
 3. a successful refresh advances the universe freshness timestamp
 4. refresh introduces newly discovered eligible fixtures
 5. duplicate fixtures are not created (idempotent merge by match id)
 6. ambiguous / unsupported competitions remain excluded (scope + settleability gate)
 7. collector capture semantics are unchanged (odds/lineup/genuine-close untouched)
 8. refresh does not invoke odds / lineup / model / settle paths
 9. repeated refresh is idempotent (byte-stable universe, no growth)
10. publication policy remains unaffected (reserved message types still blocked)
11. champion remains unaffected (no champion module touched by the refresh path)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path("/home/ubuntu")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


# ---------------------------------------------------------------------------
# Helpers to import the two standalone scripts by path.
# ---------------------------------------------------------------------------


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def heartbeat(monkeypatch, tmp_path):
    """The forecast-broadcast heartbeat module, isolated to a temp fixture file."""
    fixture_list = tmp_path / "_fixture_list.json"
    scope_cfg = tmp_path / "scope.json"
    scope_cfg.write_text(json.dumps({
        "leagues": [{"comp_id": "comp_8321"}, {"comp_id": "comp_3039"}],
        "markets": [{"market": "total_goals", "line": 2.5}],
        "horizon_hours_before_kickoff": 8,
        "quiet_hours_utc": {"start_hour": 22, "end_hour": 6},
    }))
    # Env is read at module import time for paths, so set before loading.
    monkeypatch.setenv("FORECAST_HB_FIXTURE_LIST", str(fixture_list))
    monkeypatch.setenv("FORECAST_HB_SCOPE_CONFIG", str(scope_cfg))
    monkeypatch.setenv("FORECAST_HB_STALE_UNIVERSE_HOURS", "36")
    mod = _load_module(
        "fbhb_under_test", SCRIPTS / "forecast_broadcast_heartbeat.py"
    )
    return mod, fixture_list


def _write_universe(path: Path, *, last_discovery_iso: str, meta: dict) -> None:
    path.write_text(json.dumps({
        "generated": last_discovery_iso,
        "last_discovery": last_discovery_iso,
        "match_ids": list(meta.keys()),
        "meta": meta,
    }))


def _iso(unix: float) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(unix, dt.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1 + 2. Freshness / staleness detection semantics (unchanged threshold).
# ---------------------------------------------------------------------------


def test_fresh_universe_does_not_trigger_stale(heartbeat):
    mod, fixture_list = heartbeat
    now = mod._now()
    # Refreshed 1h ago, one in-scope future fixture.
    _write_universe(fixture_list, last_discovery_iso=_iso(now - 3600), meta={
        "mt_1": {"ts": now + 3 * 3600, "comp": "comp_8321", "status": "scheduled"},
    })
    assert mod.check_stale_fixture_universe({}) is None


def test_stale_universe_triggers_alert(heartbeat):
    mod, fixture_list = heartbeat
    now = mod._now()
    # Refreshed 65h ago (> 36h): exactly the production condition.
    _write_universe(fixture_list, last_discovery_iso=_iso(now - 65 * 3600), meta={
        "mt_1": {"ts": now + 3 * 3600, "comp": "comp_8321", "status": "scheduled"},
    })
    alert = mod.check_stale_fixture_universe({})
    assert alert is not None
    assert alert["severity"] == mod.SEV_ALERT
    assert "STALE FIXTURE UNIVERSE" in alert["title"]
    assert alert["metrics"]["in_scope_upcoming"] == 1


def test_stale_threshold_is_not_weakened_by_the_repair(heartbeat):
    """The repair must NOT silence/raise the 36h threshold to clear the alert."""
    mod, _ = heartbeat
    assert mod.STALE_UNIVERSE_HOURS == 36.0


# ---------------------------------------------------------------------------
# Discovery module fixture: fake TheStatsAPI + fake corpus (NO network, NO sklearn).
# ---------------------------------------------------------------------------


@pytest.fixture()
def discovery(monkeypatch, tmp_path):
    """Load pilotC_fixture_discovery with the network + corpus stubbed out.

    Redirects every artifact path into tmp so the test never touches real data,
    and replaces the provider client with an in-memory fake so no request is made.
    """
    mod = _load_module("pilotc_discovery_under_test", SCRIPTS / "pilotC_fixture_discovery.py")

    # Redirect artifacts to tmp.
    fixture_list = tmp_path / "_fixture_list.json"
    status_file = tmp_path / "discovery_status.json"
    discovery_log = tmp_path / "discovery_log.jsonl"
    monkeypatch.setattr(mod, "FIXTURE_LIST", fixture_list)
    monkeypatch.setattr(mod, "STATUS_FILE", status_file)
    monkeypatch.setattr(mod, "DISCOVERY_LOG", discovery_log)

    # Deterministic covered-league scope for the test (two leagues).
    monkeypatch.setattr(mod, "COVERED_LEAGUES", {
        "comp_8321": "England Championship",
        "comp_3039": "England Premier League",
    })

    # Settleability gate: only these teams are "covered" (in corpus).
    covered_teams = {"Alpha FC", "Beta FC", "Gamma FC", "Delta FC"}
    monkeypatch.setattr(mod, "_load_corpus_teams", lambda: set(covered_teams))

    # Fake provider client. Records calls so we can assert ONLY /football/matches
    # is queried (no odds/lineup/stats endpoints).
    calls = {"paths": [], "requests": 0}
    now = mod.time.time()

    def _fx(mid, comp, home, away, hours_ahead, status="scheduled"):
        import datetime as dt
        ts = now + hours_ahead * 3600
        return {
            "id": mid, "status": status,
            "utc_date": dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(),
            "home_team": {"name": home}, "away_team": {"name": away},
        }

    league_fixtures = {
        "comp_8321": [
            _fx("mt_100", "comp_8321", "Alpha FC", "Beta FC", 48),      # covered -> add
            _fx("mt_101", "comp_8321", "Alpha FC", "Unknown United", 48),  # not covered
            _fx("mt_102", "comp_8321", "Gamma FC", "Delta FC", 24 * 20),   # out of window
        ],
        "comp_3039": [
            _fx("mt_200", "comp_3039", "Gamma FC", "Delta FC", 72),     # covered -> add
        ],
    }

    def fake_get_json(path, params=None, cache_key=None, allow_status=(200,)):
        calls["paths"].append(path)
        calls["requests"] += 1
        comp = (params or {}).get("competition_id")
        data = {"data": league_fixtures.get(comp, []), "meta": {"total_pages": 1}}
        return data, {"http_status": 200}

    req_counter = {"n": 0}
    monkeypatch.setattr(mod.api, "get_json", fake_get_json)
    monkeypatch.setattr(mod.api, "live_requests_made", lambda: calls["requests"])
    monkeypatch.setattr(mod.api, "budget_snapshot", lambda: {"last_monthly_remaining": 98000})
    # api.MAX_LIVE_REQUESTS is min()'d with REQUEST_CAP inside discover(); give it room.
    monkeypatch.setattr(mod.api, "MAX_LIVE_REQUESTS", 1000, raising=False)

    return mod, calls, fixture_list


# ---------------------------------------------------------------------------
# 4 + 6. Refresh adds newly eligible fixtures; excludes uncovered / out-of-window.
# ---------------------------------------------------------------------------


def test_refresh_adds_newly_eligible_fixtures(discovery):
    mod, calls, fixture_list = discovery
    stats = mod.discover(dry_run=False)
    assert stats["state"] == "found"
    # mt_100 (Alpha vs Beta) and mt_200 (Gamma vs Delta) are covered + in-window.
    assert stats["fixtures_added"] == 2
    universe = json.loads(fixture_list.read_text())
    assert set(universe["meta"].keys()) == {"mt_100", "mt_200"}


def test_uncovered_and_out_of_window_fixtures_excluded(discovery):
    mod, calls, fixture_list = discovery
    stats = mod.discover(dry_run=False)
    universe = json.loads(fixture_list.read_text())
    # mt_101 has an uncovered away team -> settleability gate drops it.
    assert "mt_101" not in universe["meta"]
    # mt_102 is 20 days out (> 10-day window) -> excluded.
    assert "mt_102" not in universe["meta"]


# ---------------------------------------------------------------------------
# 3. A successful refresh advances the freshness timestamp.
# ---------------------------------------------------------------------------


def test_refresh_advances_freshness_timestamp(discovery):
    mod, calls, fixture_list = discovery
    # Seed a stale universe.
    old_iso = "2026-09-07T06:00:00+00:00"
    fixture_list.write_text(json.dumps({
        "generated": old_iso, "last_discovery": old_iso,
        "match_ids": [], "meta": {},
    }))
    mod.discover(dry_run=False)
    universe = json.loads(fixture_list.read_text())
    assert universe["last_discovery"] != old_iso
    # New timestamp parses and is strictly newer.
    import datetime as dt
    new = dt.datetime.fromisoformat(universe["last_discovery"])
    old = dt.datetime.fromisoformat(old_iso)
    assert new > old


# ---------------------------------------------------------------------------
# 5 + 9. Duplicate-free, idempotent merge.
# ---------------------------------------------------------------------------


def test_no_duplicate_fixtures_and_idempotent(discovery):
    mod, calls, fixture_list = discovery
    first = mod.discover(dry_run=False)
    universe_1 = json.loads(fixture_list.read_text())
    n_after_first = len(universe_1["meta"])
    ids_after_first = sorted(universe_1["meta"].keys())

    second = mod.discover(dry_run=False)
    universe_2 = json.loads(fixture_list.read_text())

    # No new fixtures added on the second run; same id set; match_ids has no dupes.
    assert second["fixtures_added"] == 0
    assert sorted(universe_2["meta"].keys()) == ids_after_first
    assert len(universe_2["meta"]) == n_after_first
    assert len(universe_2["match_ids"]) == len(set(universe_2["match_ids"]))


# ---------------------------------------------------------------------------
# 8. Fixture discovery ONLY — no odds / lineup / model / settle endpoints.
# ---------------------------------------------------------------------------


def test_refresh_only_queries_matches_endpoint(discovery):
    mod, calls, fixture_list = discovery
    mod.discover(dry_run=False)
    assert calls["paths"], "discovery made no request at all"
    # Every request is the scheduled-matches listing; nothing else.
    assert all(p == "/football/matches" for p in calls["paths"])
    for forbidden in ("/odds", "lineup", "/statistics", "/players", "referee"):
        assert not any(forbidden in p for p in calls["paths"])


def test_refresh_is_quota_capped(discovery):
    mod, calls, fixture_list = discovery
    stats = mod.discover(dry_run=False)
    rq = stats["requests"]
    # Two leagues, one page each => a small, bounded request count under the cap.
    assert rq["live_requests_used_this_run"] <= rq["per_run_request_cap"]
    assert rq["per_run_request_cap"] == mod.REQUEST_CAP


# ---------------------------------------------------------------------------
# 7. Collector capture semantics unchanged (genuine-close / vintage untouched).
# ---------------------------------------------------------------------------


def test_collector_capture_semantics_unchanged():
    """The repair adds scheduling only; capture/close/vintage code is untouched."""
    from src.research.prospective.odds_capture import (
        OddsSemantics, resolve_genuine_close, CloseStatus, CapturedPrice,
    )
    from src.research.prospective.vintages import ProspectiveVintage

    # Genuine close still requires our own pre-kickoff snapshot; never last_seen.
    K = 1_000_000.0
    snaps = [
        CapturedPrice("pinnacle", "total_goals", "over", 2.5, 1.90,
                      OddsSemantics.PROSPECTIVE_SNAPSHOT, K - 3600, "h"),
        CapturedPrice("pinnacle", "total_goals", "over", 2.5, 1.95,
                      OddsSemantics.PROSPECTIVE_SNAPSHOT, K - 600, "h"),
    ]
    r = resolve_genuine_close(snaps, kickoff_ts=K, bookmaker="pinnacle",
                              market="total_goals", selection="over", line=2.5)
    assert r.status == CloseStatus.GENUINE_CLOSE
    assert r.close.observed_at == K - 600
    # Vintage ladder is unchanged (FINAL still ~T-15m).
    assert ProspectiveVintage.FINAL.offset_seconds == 15 * 60


# ---------------------------------------------------------------------------
# 10. Publication policy unaffected (reserved signal types still blocked).
# ---------------------------------------------------------------------------


def test_publication_policy_unaffected():
    from src.research.prospective.research_notify import (
        MessageType, RESERVED_TYPES, assert_no_signal_content, SignalContentError,
    )
    assert MessageType.VALIDATED_SIGNAL in RESERVED_TYPES
    assert MessageType.STRATEGY_ACTION in RESERVED_TYPES
    with pytest.raises(SignalContentError):
        assert_no_signal_content("this is a strong signal, place a bet")


# ---------------------------------------------------------------------------
# 11. Champion unaffected — the refresh path imports no champion/model module.
# ---------------------------------------------------------------------------


def test_refresh_runner_touches_no_champion_or_model_path():
    runner = (SCRIPTS / "prospective_universe_refresh_run.sh").read_text()
    # Ignore comment lines and the data-dir path token "championship" — the runner's
    # only executable action is invoking the discovery script. Check the command
    # surface, not prose.
    code_lines = [ln for ln in runner.splitlines()
                  if ln.strip() and not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    # No model/champion/settle/odds/lineup ENTRYPOINTS appear in the executable body.
    for forbidden in ("src.cli", "forward_predict", "pilotC_settle",
                      "capture-due", "capture-odds", "capture-lineups",
                      "daily-signals", "signals_telegram", "refresh_corpus"):
        assert forbidden not in code
    # The only python invocation is the existing discovery script.
    assert "scripts/pilotC_fixture_discovery.py" in code
    assert code.count(".venv/bin/python") == 1
