"""Scheduler health assessment from the operational run log.

A functioning API with a DEAD cron/systemd timer is NOT healthy. The
``quality-report`` command reflects the RESEARCH state of the capture store;
this module answers a different, operational question:

    Is the collector actually running on schedule, and did the last runs
    succeed?

It reads ONLY the operational run log (:mod:`src.research.prospective.ops_log`)
plus the current wall clock. It never issues a network request, so it can be
used as an independent watchdog. Health is derived deterministically from the
freshness of the last run and the last run's own exit status.

States (independent, first match in priority order wins):

- ``STALE_SCHEDULER``  : no run at all, or the last run is older than the
  staleness threshold (the timer is dead / wedged). This dominates because a
  green API means nothing if nothing is invoking the collector.
- ``AUTH_FAILED``      : the last run failed to authenticate (missing/rejected
  key). Capture cannot proceed.
- ``QUOTA_LIMITED``    : the last run stopped early to protect the quota
  reserve.
- ``SCHEMA_DRIFT``     : the last run flagged an unexpected payload shape.
- ``PARTIAL_FAILURE``  : the last run completed but with per-fixture errors.
- ``HEALTHY``          : a recent run completed cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.research.prospective.ops_log import DEFAULT_OPS_LOG, OpsRunRecord, read_runs

#: A 15-minute cadence should produce a run every 900s. We allow ~3 missed
#: ticks before declaring the scheduler stale, so a single transient skip does
#: not trip the alarm. Fixed, not tuned on any outcome.
DEFAULT_STALE_AFTER_SECONDS = 3 * 15 * 60 + 120  # 3 ticks + slack = 2820s


@dataclass(frozen=True)
class SchedulerHealth:
    """Operational health snapshot derived from the ops run log."""

    health: str
    last_successful_run: Optional[float]
    last_attempted_run: Optional[float]
    minutes_since_success: Optional[float]
    minutes_since_attempt: Optional[float]
    latest_health_state: Optional[str]
    latest_quota_remaining: Optional[int]
    latest_error_count: Optional[int]
    total_runs_observed: int
    stale_after_seconds: float

    def to_dict(self) -> dict:
        return {
            "health": self.health,
            "last_successful_run": self.last_successful_run,
            "last_attempted_run": self.last_attempted_run,
            "minutes_since_success": self.minutes_since_success,
            "minutes_since_attempt": self.minutes_since_attempt,
            "latest_health_state": self.latest_health_state,
            "latest_quota_remaining": self.latest_quota_remaining,
            "latest_error_count": self.latest_error_count,
            "total_runs_observed": self.total_runs_observed,
            "stale_after_seconds": self.stale_after_seconds,
        }


def _is_success(rec: OpsRunRecord) -> bool:
    """A run is 'successful' if it completed without a blocking failure.

    QUOTA_LIMITED is a controlled, healthy stop (reserve protection) and still
    counts as a completed attempt for freshness, but not as a clean success for
    the ``last_successful_run`` marker. AUTH_FAILED / ERROR / SCHEMA_DRIFT /
    LOCKED are not successes. PARTIAL_FAILURE completed but had errors.
    """
    return rec.exit_status in ("OK",)


def assess_health(
    *,
    now: float,
    path: Path = DEFAULT_OPS_LOG,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> SchedulerHealth:
    """Assess scheduler health from the ops run log as of ``now``.

    Deterministic: the log contents + ``now`` fully determine the result. No
    network. When the log is empty, health is ``STALE_SCHEDULER`` (nothing has
    ever run), which is the correct fail-closed operational verdict.
    """
    runs = read_runs(path=path)
    total = len(runs)

    if not runs:
        return SchedulerHealth(
            health="STALE_SCHEDULER",
            last_successful_run=None,
            last_attempted_run=None,
            minutes_since_success=None,
            minutes_since_attempt=None,
            latest_health_state=None,
            latest_quota_remaining=None,
            latest_error_count=None,
            total_runs_observed=0,
            stale_after_seconds=stale_after_seconds,
        )

    last = runs[-1]
    last_attempt_ts = last.run_finished_at or last.run_started_at
    successes = [r for r in runs if _is_success(r)]
    last_success_ts = (successes[-1].run_finished_at or successes[-1].run_started_at) if successes else None

    minutes_since_attempt = (now - last_attempt_ts) / 60.0 if last_attempt_ts else None
    minutes_since_success = (now - last_success_ts) / 60.0 if last_success_ts else None

    # Priority order: staleness dominates (a dead timer is the worst
    # operational state regardless of the last recorded exit).
    if last_attempt_ts is None or (now - last_attempt_ts) > stale_after_seconds:
        health = "STALE_SCHEDULER"
    elif last.exit_status == "AUTH_FAILED":
        health = "AUTH_FAILED"
    elif last.exit_status == "SCHEMA_DRIFT":
        health = "SCHEMA_DRIFT"
    elif last.exit_status == "QUOTA_LIMITED" or last.quota_limited:
        health = "QUOTA_LIMITED"
    elif last.exit_status == "PARTIAL_FAILURE" or (last.errors or 0) > 0:
        health = "PARTIAL_FAILURE"
    elif last.exit_status == "OK":
        health = "HEALTHY"
    else:
        # LOCKED / ERROR / anything unexpected: not healthy, surface it.
        health = "PARTIAL_FAILURE"

    return SchedulerHealth(
        health=health,
        last_successful_run=last_success_ts,
        last_attempted_run=last_attempt_ts,
        minutes_since_success=minutes_since_success,
        minutes_since_attempt=minutes_since_attempt,
        latest_health_state=last.health_state,
        latest_quota_remaining=last.quota_remaining,
        latest_error_count=last.errors,
        total_runs_observed=total,
        stale_after_seconds=stale_after_seconds,
    )
