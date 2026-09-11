"""Regression tests for the forecast-broadcast heartbeat's ``check_stale_corpus``.

Context (false-positive repair)
-------------------------------
``check_stale_corpus`` alerts ``CORPUS FRESHNESS REPORT STALE`` when
``health_report.json`` is older than ``STALE_HEALTH_REPORT_HOURS`` (36h). The
broadcaster only used to write that report on ticks that reached the model fit
(``due > 0``). During a legitimate quiet period between matchdays every tick
reports ``due == 0`` and returned early WITHOUT writing the report, so the report
aged past 36h and fired a false alert even though the gate simply had nothing to
evaluate and the corpus was current.

The repair has two coordinated halves:
  1. ``scripts/forecast_broadcast.py`` now writes a health report on the
     ``due == 0`` early return too (``run_summary.due == 0``, fresh
     ``generated_at_utc``), so a quiet period keeps the report current.
  2. ``check_stale_corpus`` only treats a stale report as an ALERT when the gate
     SHOULD have run: if the last recorded tick found nothing due AND nothing is
     currently past its horizon, a stale report is the expected quiet-period state
     and is not alerted. A stale report while fixtures were due still alerts.

These tests drive the heartbeat module in isolation (no network, no broadcaster
run) using the same conventions as ``test_fixture_universe_refresh.py``.
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


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def heartbeat(monkeypatch, tmp_path):
    """The heartbeat module, isolated to temp record root / health report / scope."""
    record_root = tmp_path / "forecast_broadcast"
    record_root.mkdir(parents=True, exist_ok=True)
    health_report = record_root / "health_report.json"
    fixture_list = tmp_path / "_fixture_list.json"
    scope_cfg = tmp_path / "scope.json"
    scope_cfg.write_text(json.dumps({
        "leagues": [{"comp_id": "comp_8321"}],
        "markets": [{"market": "total_goals", "line": 2.5}],
        "horizon_hours_before_kickoff": 8,
        "quiet_hours_utc": {"start_hour": 22, "end_hour": 6},
    }))
    # Paths are resolved at import time, so set env BEFORE loading the module.
    monkeypatch.setenv("FORECAST_HB_RECORD_ROOT", str(record_root))
    monkeypatch.setenv("FORECAST_HB_HEALTH_REPORT", str(health_report))
    monkeypatch.setenv("FORECAST_HB_FIXTURE_LIST", str(fixture_list))
    monkeypatch.setenv("FORECAST_HB_SCOPE_CONFIG", str(scope_cfg))
    monkeypatch.setenv("FORECAST_HB_STALE_HEALTH_REPORT_HOURS", "36")
    mod = _load_module("fbhb_corpus_under_test", SCRIPTS / "forecast_broadcast_heartbeat.py")
    return mod, health_report, fixture_list


def _iso(unix: float) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(unix, dt.timezone.utc).isoformat()


def _write_report(path: Path, *, generated_unix: float, due: int,
                  publication_blocked: bool = False, gate_state: str = "FRESH") -> None:
    path.write_text(json.dumps({
        "report_contract": "forecast-broadcast-health/v1",
        "generated_at_utc": _iso(generated_unix),
        "publication_blocked": publication_blocked,
        "freshness_gate": {"state": gate_state, "metrics": {}},
        "run_summary": {"due": due, "finished_at_utc": _iso(generated_unix)},
    }))


def _write_universe(path: Path, meta: dict) -> None:
    path.write_text(json.dumps({
        "generated": _iso(0.0),
        "last_discovery": _iso(0.0),
        "match_ids": list(meta.keys()),
        "meta": meta,
    }))


# ---------------------------------------------------------------------------
# Threshold is not weakened by the repair.
# ---------------------------------------------------------------------------


def test_stale_threshold_unchanged(heartbeat):
    mod, _, _ = heartbeat
    assert mod.STALE_HEALTH_REPORT_HOURS == 36.0


# ---------------------------------------------------------------------------
# A fresh report never alerts, regardless of due count.
# ---------------------------------------------------------------------------


def test_fresh_report_does_not_alert(heartbeat):
    mod, health_report, fixture_list = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 3600, due=0)
    _write_universe(fixture_list, {})  # nothing in scope
    assert mod.check_stale_corpus({}) is None


# ---------------------------------------------------------------------------
# The false-positive case: stale report during a genuine quiet period.
# Last tick found nothing due AND nothing is currently past its horizon
# => NOT an alert.
# ---------------------------------------------------------------------------


def test_stale_report_during_quiet_period_is_not_alerted(heartbeat):
    mod, health_report, fixture_list = heartbeat
    now = mod._now()
    # Report is 40h old (> 36h) but the last tick recorded due == 0 ...
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    # ... and no in-scope fixture has passed its horizon (kickoff far in future).
    _write_universe(fixture_list, {
        "mt_future": {"ts": now + 5 * 24 * 3600, "comp": "comp_8321", "status": "scheduled"},
    })
    assert mod.check_stale_corpus({}) is None


# ---------------------------------------------------------------------------
# The real failure mode is preserved: a stale report while fixtures were due
# still alerts.
# ---------------------------------------------------------------------------


def test_stale_report_while_fixtures_due_still_alerts(heartbeat):
    mod, health_report, fixture_list = heartbeat
    now = mod._now()
    # Report is stale AND a fixture has passed its T-8h horizon (kickoff 2h ago),
    # so the gate SHOULD have produced a fresh verdict but did not.
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, {
        "mt_due": {"ts": now - 2 * 3600, "comp": "comp_8321", "status": "scheduled"},
    })
    alert = mod.check_stale_corpus({})
    assert alert is not None
    assert alert["severity"] == mod.SEV_ALERT
    assert alert["title"] == "CORPUS FRESHNESS REPORT STALE"


def test_stale_report_with_due_marker_still_alerts_even_if_calendar_quiet(heartbeat):
    # If the last recorded tick itself had due > 0 but the report then went stale,
    # that is a stalled pipeline mid-matchday: alert even though the universe query
    # now shows nothing (defensive — the recorded verdict says work was happening).
    mod, health_report, fixture_list = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=3)
    _write_universe(fixture_list, {})  # calendar currently quiet
    alert = mod.check_stale_corpus({})
    assert alert is not None
    assert alert["severity"] == mod.SEV_ALERT
    assert alert["title"] == "CORPUS FRESHNESS REPORT STALE"


# ---------------------------------------------------------------------------
# Publication-blocked still alerts regardless of age (unchanged branch).
# ---------------------------------------------------------------------------


def test_publication_blocked_alerts(heartbeat):
    mod, health_report, fixture_list = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 3600, due=2,
                  publication_blocked=True, gate_state="STALE")
    _write_universe(fixture_list, {})
    alert = mod.check_stale_corpus({})
    assert alert is not None
    assert alert["severity"] == mod.SEV_ALERT
    assert "PUBLICATION BLOCKED" in alert["title"]
