"""Tests for operational run logging and scheduler-health assessment.

These cover the mission's operational-reliability requirements: a functioning
API with a dead timer must NOT read as HEALTHY, run metadata is persisted
separately from research observations, the log is bounded (rotates), and the
health states are derived deterministically from the log + wall clock.
"""

from __future__ import annotations

from pathlib import Path

from src.research.prospective.ops_log import (
    MAX_BYTES,
    OpsRunRecord,
    append_run,
    latest_run,
    read_runs,
)
from src.research.prospective.scheduler_health import (
    DEFAULT_STALE_AFTER_SECONDS,
    assess_health,
)


def _rec(started, finished, status="OK", health="HEALTHY", errors=0, quota=90000, quota_limited=False):
    return OpsRunRecord(
        run_started_at=started,
        run_finished_at=finished,
        duration_seconds=finished - started,
        exit_status=status,
        health_state=health,
        errors=errors,
        quota_remaining=quota,
        quota_limited=quota_limited,
    )


# --- ops log -------------------------------------------------------------


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(100.0, 150.0), path=p)
    append_run(_rec(200.0, 260.0, status="PARTIAL_FAILURE", errors=2), path=p)
    runs = read_runs(path=p)
    assert len(runs) == 2
    assert runs[0].exit_status == "OK"
    assert runs[1].exit_status == "PARTIAL_FAILURE"
    assert runs[1].errors == 2
    assert latest_run(path=p).run_started_at == 200.0


def test_read_limit_keeps_most_recent(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    for i in range(5):
        append_run(_rec(float(i), float(i) + 1), path=p)
    runs = read_runs(path=p, limit=2)
    assert [r.run_started_at for r in runs] == [3.0, 4.0]


def test_malformed_line_skipped(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1.0, 2.0), path=p)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
    append_run(_rec(3.0, 4.0), path=p)
    runs = read_runs(path=p)
    assert len(runs) == 2  # bad line skipped, never guessed


def test_ops_log_rotates_when_oversized(tmp_path, monkeypatch):
    p = tmp_path / "ops_runs.jsonl"
    # Force a tiny rotation threshold to exercise the rotation path.
    monkeypatch.setattr("src.research.prospective.ops_log.MAX_BYTES", 200)
    for i in range(50):
        append_run(_rec(float(i), float(i) + 1), path=p)
    # The active file exists and at least one rotated backup was created.
    assert p.exists()
    assert (tmp_path / "ops_runs.jsonl.1").exists()


def test_missing_log_reads_empty(tmp_path):
    assert read_runs(path=tmp_path / "does_not_exist.jsonl") == []


# --- scheduler health ----------------------------------------------------


def test_empty_log_is_stale_scheduler(tmp_path):
    h = assess_health(now=1000.0, path=tmp_path / "ops_runs.jsonl")
    assert h.health == "STALE_SCHEDULER"
    assert h.total_runs_observed == 0


def test_recent_ok_run_is_healthy(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0), path=p)
    h = assess_health(now=1100.0, path=p)  # 50s after finish
    assert h.health == "HEALTHY"
    assert h.last_successful_run == 1050.0
    assert h.latest_quota_remaining == 90000


def test_functioning_api_but_dead_timer_is_stale(tmp_path):
    """The core requirement: a clean last run that is now OLD => STALE_SCHEDULER."""
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0, status="OK", health="HEALTHY"), path=p)
    # now is far beyond the staleness threshold even though the last run was OK.
    now = 1050.0 + DEFAULT_STALE_AFTER_SECONDS + 10
    h = assess_health(now=now, path=p)
    assert h.health == "STALE_SCHEDULER"


def test_auth_failure_surfaces(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1000.0, status="AUTH_FAILED", health="AUTH_FAILED"), path=p)
    h = assess_health(now=1030.0, path=p)
    assert h.health == "AUTH_FAILED"


def test_quota_limited_surfaces(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0, status="QUOTA_LIMITED", quota_limited=True), path=p)
    h = assess_health(now=1100.0, path=p)
    assert h.health == "QUOTA_LIMITED"


def test_partial_failure_surfaces(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0, status="PARTIAL_FAILURE", errors=3), path=p)
    h = assess_health(now=1100.0, path=p)
    assert h.health == "PARTIAL_FAILURE"
    assert h.latest_error_count == 3


def test_schema_drift_surfaces(tmp_path):
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0, status="SCHEMA_DRIFT"), path=p)
    h = assess_health(now=1100.0, path=p)
    assert h.health == "SCHEMA_DRIFT"


def test_staleness_dominates_partial_failure(tmp_path):
    """Even if the last run had errors, an OLD last run is STALE first."""
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0, status="PARTIAL_FAILURE", errors=1), path=p)
    now = 1050.0 + DEFAULT_STALE_AFTER_SECONDS + 1
    h = assess_health(now=now, path=p)
    assert h.health == "STALE_SCHEDULER"


def test_quota_limited_not_counted_as_success_marker(tmp_path):
    """QUOTA_LIMITED is a controlled stop; it should not set last_successful_run."""
    p = tmp_path / "ops_runs.jsonl"
    append_run(_rec(1000.0, 1050.0, status="QUOTA_LIMITED", quota_limited=True), path=p)
    h = assess_health(now=1100.0, path=p)
    assert h.last_successful_run is None
    assert h.last_attempted_run == 1050.0
