"""Regression tests for the forecast-broadcast heartbeat's ``check_stale_corpus``.

Context (false-positive repair + fail-closed hardening)
-------------------------------------------------------
``check_stale_corpus`` alerts ``CORPUS FRESHNESS REPORT STALE`` when
``health_report.json`` is older than ``STALE_HEALTH_REPORT_HOURS`` (36h). The
broadcaster only used to write that report on ticks that reached the model fit
(``due > 0``). During a legitimate quiet period between matchdays every tick
reports ``due == 0`` and returned early WITHOUT writing the report, so the report
aged past 36h and fired a false alert even though the gate simply had nothing to
evaluate and the corpus was current.

The repair has two coordinated halves:
  1. ``scripts/forecast_broadcast.py`` writes a health report on the ``due == 0``
     early return too (``run_summary.due == 0``, ``freshness_gate = None``, fresh
     ``generated_at_utc``), so a quiet period keeps the report current.
  2. ``check_stale_corpus`` suppresses the stale-report alert ONLY when it can
     POSITIVELY prove the period is quiet. Suppression requires BOTH:
       * the last recorded tick found ``run_summary.due == 0`` (strictly int 0);
         AND
       * an independent, fail-closed current-due determination of ``NONE_DUE``.
     The current-due determination is three-state (``DUE`` / ``NONE_DUE`` /
     ``UNKNOWN``): any missing, unreadable, malformed, ambiguous, or otherwise
     insufficient scope / fixture-universe evidence yields ``UNKNOWN``, which must
     ALERT — "cannot prove quiet" is never read as "quiet".

These tests drive the heartbeat module in isolation (no network, no broadcaster
run). The repository root is resolved RELATIVE TO THIS FILE so the suite is
portable across clones / CI (no hard-coded host path).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# Resolve the repo root portably: this file lives at
# <repo>/tests/research/prospective/test_corpus_freshness_report_stale.py
REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
for _p in (str(REPO), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

HEARTBEAT_PATH = SCRIPTS / "forecast_broadcast_heartbeat.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def heartbeat(monkeypatch, tmp_path):
    """The heartbeat module, isolated to temp record root / health report / scope.

    All artifact paths are redirected via env BEFORE import, so the module never
    reads any real host path and the test is fully hermetic.
    """
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
    mod = _load_module("fbhb_corpus_under_test", HEARTBEAT_PATH)
    return mod, health_report, fixture_list, scope_cfg


def _iso(unix: float) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(unix, dt.timezone.utc).isoformat()


def _write_report(path: Path, *, generated_unix: float, due, has_due: bool = True,
                  publication_blocked: bool = False, gate_state: str = "FRESH") -> None:
    run_summary = {"finished_at_utc": _iso(generated_unix)}
    if has_due:
        run_summary["due"] = due
    path.write_text(json.dumps({
        "report_contract": "forecast-broadcast-health/v1",
        "generated_at_utc": _iso(generated_unix),
        "publication_blocked": publication_blocked,
        "freshness_gate": {"state": gate_state, "metrics": {}},
        "run_summary": run_summary,
    }))


def _write_universe(path: Path, meta) -> None:
    path.write_text(json.dumps({
        "generated": _iso(0.0),
        "last_discovery": _iso(0.0),
        "match_ids": list(meta.keys()) if isinstance(meta, dict) else [],
        "meta": meta,
    }))


def _quiet_universe(now: float) -> dict:
    # One in-scope fixture, kickoff far in the future -> NONE_DUE.
    return {"mt_future": {"ts": now + 5 * 24 * 3600, "comp": "comp_8321", "status": "scheduled"}}


def _due_universe(now: float) -> dict:
    # One in-scope fixture past its T-8h horizon (kickoff 2h ago) -> DUE.
    return {"mt_due": {"ts": now - 2 * 3600, "comp": "comp_8321", "status": "scheduled"}}


def _assert_stale_alert(alert, mod):
    assert alert is not None
    assert alert["severity"] == mod.SEV_ALERT
    assert alert["title"] == "CORPUS FRESHNESS REPORT STALE"


# ---------------------------------------------------------------------------
# (14) Threshold is not weakened by the repair.
# ---------------------------------------------------------------------------


def test_stale_threshold_unchanged(heartbeat):
    mod, _, _, _ = heartbeat
    assert mod.STALE_HEALTH_REPORT_HOURS == 36.0


# ---------------------------------------------------------------------------
# A fresh report never alerts, regardless of due count.
# ---------------------------------------------------------------------------


def test_fresh_report_does_not_alert(heartbeat):
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 3600, due=0)
    _write_universe(fixture_list, {})  # nothing in scope
    assert mod.check_stale_corpus({}) is None


# ---------------------------------------------------------------------------
# (10) Positive quiet-period proof: valid scope + valid universe + nothing due
# + previous due==0 -> NO ALERT.
# ---------------------------------------------------------------------------


def test_stale_report_during_proven_quiet_period_is_not_alerted(heartbeat):
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.NONE_DUE
    assert mod.check_stale_corpus({}) is None


# ---------------------------------------------------------------------------
# (11) Fixture currently due + previous due==0 -> ALERT.
# ---------------------------------------------------------------------------


def test_stale_report_while_fixture_currently_due_alerts(heartbeat):
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _due_universe(now))
    assert mod._current_due_state(now) == mod.DUE
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


# ---------------------------------------------------------------------------
# (12) Previous due>0 + currently quiet -> ALERT.
# ---------------------------------------------------------------------------


def test_stale_report_previous_due_positive_alerts_even_if_quiet_now(heartbeat):
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=3)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.NONE_DUE
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


# ---------------------------------------------------------------------------
# (8) Previous run_summary.due MISSING -> ALERT even with a valid quiet calendar.
# (9) Previous run_summary.due MALFORMED -> ALERT even with a valid quiet calendar.
# ---------------------------------------------------------------------------


def test_previous_due_missing_alerts_even_if_quiet(heartbeat):
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=None, has_due=False)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.NONE_DUE
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


@pytest.mark.parametrize("bad_due", ["0", 0.0, True, False, [], {}, None])
def test_previous_due_malformed_alerts_even_if_quiet(heartbeat, bad_due):
    # Only the integer 0 proves a no-due tick. Strings, floats, booleans, empty
    # containers, and None must NOT be accepted as proof.
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=bad_due)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.NONE_DUE
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


# ---------------------------------------------------------------------------
# Fail-closed UNKNOWN current-due cases: previous due==0 but the calendar cannot
# be positively established -> ALERT (1-7).
# ---------------------------------------------------------------------------


def test_missing_scope_config_alerts(heartbeat):  # (1)
    mod, health_report, fixture_list, scope_cfg = heartbeat
    now = mod._now()
    scope_cfg.unlink()  # remove scope config entirely
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_invalid_scope_config_json_alerts(heartbeat):  # (2)
    mod, health_report, fixture_list, scope_cfg = heartbeat
    now = mod._now()
    scope_cfg.write_text("{not valid json")
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_scope_config_no_usable_comps_alerts(heartbeat):  # (2b)
    mod, health_report, fixture_list, scope_cfg = heartbeat
    now = mod._now()
    scope_cfg.write_text(json.dumps({"leagues": [], "horizon_hours_before_kickoff": 8}))
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_missing_horizon_alerts(heartbeat):  # (3)
    mod, health_report, fixture_list, scope_cfg = heartbeat
    now = mod._now()
    scope_cfg.write_text(json.dumps({"leagues": [{"comp_id": "comp_8321"}]}))  # no horizon
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


@pytest.mark.parametrize("bad_horizon", ["8", None, True, float("nan"), float("inf")])
def test_malformed_horizon_alerts(heartbeat, bad_horizon):  # (3b)
    mod, health_report, fixture_list, scope_cfg = heartbeat
    now = mod._now()
    scope_cfg.write_text(json.dumps({
        "leagues": [{"comp_id": "comp_8321"}],
        "horizon_hours_before_kickoff": bad_horizon,
    }))
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_missing_fixture_universe_alerts(heartbeat):  # (4)
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    # Do NOT create the fixture universe file at all.
    assert not fixture_list.exists()
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_invalid_fixture_universe_json_alerts(heartbeat):  # (5)
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    fixture_list.write_text("{ broken json ]")
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_malformed_fixture_universe_structure_alerts(heartbeat):  # (6)
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    # meta is not a dict -> cannot enumerate fixtures.
    _write_universe(fixture_list, ["not", "a", "dict"])
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_universe_top_level_not_dict_alerts(heartbeat):  # (6b)
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    fixture_list.write_text(json.dumps(["a", "b"]))  # top-level list, not dict
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_in_scope_fixture_unparseable_kickoff_alerts(heartbeat):  # (7)
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    # In-scope fixture whose kickoff cannot be interpreted -> ambiguous -> UNKNOWN.
    _write_universe(fixture_list, {
        "mt_bad": {"ts": "not-a-number", "comp": "comp_8321", "status": "scheduled"},
    })
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_malformed_fixture_record_alerts(heartbeat):  # (7b)
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    # A record we cannot even classify (not a dict) -> UNKNOWN.
    _write_universe(fixture_list, {"mt_bad": "not-a-dict"})
    assert mod._current_due_state(now) == mod.UNKNOWN
    _assert_stale_alert(mod.check_stale_corpus({}), mod)


def test_out_of_scope_bad_record_still_none_due(heartbeat):
    # Defensible existing contract: an out-of-scope competition is irrelevant and
    # must NOT force UNKNOWN, even if its kickoff is unparseable. With only that
    # out-of-scope junk plus no in-scope fixtures, the calendar is provably quiet.
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 40 * 3600, due=0)
    _write_universe(fixture_list, {
        "mt_other": {"ts": "garbage", "comp": "comp_OTHER", "status": "scheduled"},
    })
    assert mod._current_due_state(now) == mod.NONE_DUE
    assert mod.check_stale_corpus({}) is None


# ---------------------------------------------------------------------------
# (13) Publication-blocked still alerts regardless of age (unchanged branch).
# ---------------------------------------------------------------------------


def test_publication_blocked_alerts(heartbeat):
    mod, health_report, fixture_list, _ = heartbeat
    now = mod._now()
    _write_report(health_report, generated_unix=now - 3600, due=2,
                  publication_blocked=True, gate_state="STALE")
    _write_universe(fixture_list, {})
    alert = mod.check_stale_corpus({})
    assert alert is not None
    assert alert["severity"] == mod.SEV_ALERT
    assert "PUBLICATION BLOCKED" in alert["title"]


# ---------------------------------------------------------------------------
# Direct three-state helper sanity checks.
# ---------------------------------------------------------------------------


def test_current_due_state_positive_none_due(heartbeat):
    mod, _, fixture_list, _ = heartbeat
    now = mod._now()
    _write_universe(fixture_list, _quiet_universe(now))
    assert mod._current_due_state(now) == mod.NONE_DUE


def test_current_due_state_due(heartbeat):
    mod, _, fixture_list, _ = heartbeat
    now = mod._now()
    _write_universe(fixture_list, _due_universe(now))
    assert mod._current_due_state(now) == mod.DUE
