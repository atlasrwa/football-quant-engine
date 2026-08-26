"""Health Monitoring — lightweight system health checks.

Monitors:
- Provider availability
- Database connectivity (conceptual)
- Fixture freshness
- Odds freshness
- Scheduler heartbeat
- Stale/failed jobs
- Queue depth
- Open paper trades
- Missing closing odds

Creates structured results suitable for future dashboard/API.
Does NOT require a dashboard yet.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class HealthCheck:
    """Result of a single health check."""
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    checked_at: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "checked_at": self.checked_at,
            "latency_ms": round(self.latency_ms, 1),
            "metadata": self.metadata,
        }


@dataclass
class SystemHealth:
    """Aggregate system health state."""
    overall_status: HealthStatus = HealthStatus.UNKNOWN
    checks: list[HealthCheck] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)

    # Key metrics
    fixtures_fresh: bool = False
    odds_fresh: bool = False
    scheduler_alive: bool = False
    stale_jobs: int = 0
    failed_jobs: int = 0
    open_trades: int = 0
    missing_closing_odds: int = 0
    provider_errors: int = 0

    def compute_overall(self) -> None:
        """Compute overall status from individual checks."""
        if not self.checks:
            self.overall_status = HealthStatus.UNKNOWN
            return

        statuses = [c.status for c in self.checks]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            self.overall_status = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            self.overall_status = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            self.overall_status = HealthStatus.HEALTHY
        else:
            self.overall_status = HealthStatus.DEGRADED

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "checked_at": self.checked_at,
            "fixtures_fresh": self.fixtures_fresh,
            "odds_fresh": self.odds_fresh,
            "scheduler_alive": self.scheduler_alive,
            "stale_jobs": self.stale_jobs,
            "failed_jobs": self.failed_jobs,
            "open_trades": self.open_trades,
            "missing_closing_odds": self.missing_closing_odds,
            "provider_errors": self.provider_errors,
            "checks": [c.to_dict() for c in self.checks],
        }


class HealthMonitor:
    """Lightweight health monitoring system.

    Performs checks and produces structured results.
    No external dependencies — suitable for embedding in scheduler.
    """

    def __init__(
        self,
        fixture_freshness_seconds: float = 600.0,
        odds_freshness_seconds: float = 3600.0,
        heartbeat_timeout_seconds: float = 300.0,
    ) -> None:
        self._fixture_freshness = fixture_freshness_seconds
        self._odds_freshness = odds_freshness_seconds
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._last_fixture_refresh: float = 0.0
        self._last_odds_refresh: float = 0.0
        self._last_heartbeat: float = 0.0
        self._provider_errors: int = 0
        self._failed_jobs: int = 0

    def record_fixture_refresh(self) -> None:
        self._last_fixture_refresh = time.time()

    def record_odds_refresh(self) -> None:
        self._last_odds_refresh = time.time()

    def record_heartbeat(self) -> None:
        self._last_heartbeat = time.time()

    def record_provider_error(self) -> None:
        self._provider_errors += 1

    def record_job_failure(self) -> None:
        self._failed_jobs += 1

    def check_health(
        self,
        open_trades: int = 0,
        missing_closing_odds: int = 0,
        stale_jobs: int = 0,
    ) -> SystemHealth:
        """Perform all health checks and return aggregate result."""
        now = time.time()
        checks: list[HealthCheck] = []

        # Fixture freshness
        fixture_age = now - self._last_fixture_refresh if self._last_fixture_refresh else float("inf")
        fixture_fresh = fixture_age < self._fixture_freshness
        checks.append(HealthCheck(
            name="fixture_freshness",
            status=HealthStatus.HEALTHY if fixture_fresh else HealthStatus.DEGRADED,
            message=f"Last refresh: {fixture_age:.0f}s ago" if self._last_fixture_refresh else "Never refreshed",
        ))

        # Odds freshness
        odds_age = now - self._last_odds_refresh if self._last_odds_refresh else float("inf")
        odds_fresh = odds_age < self._odds_freshness
        checks.append(HealthCheck(
            name="odds_freshness",
            status=HealthStatus.HEALTHY if odds_fresh else HealthStatus.DEGRADED,
            message=f"Last refresh: {odds_age:.0f}s ago" if self._last_odds_refresh else "Never refreshed",
        ))

        # Scheduler heartbeat
        heartbeat_age = now - self._last_heartbeat if self._last_heartbeat else float("inf")
        scheduler_alive = heartbeat_age < self._heartbeat_timeout
        checks.append(HealthCheck(
            name="scheduler_heartbeat",
            status=HealthStatus.HEALTHY if scheduler_alive else HealthStatus.UNHEALTHY,
            message=f"Last heartbeat: {heartbeat_age:.0f}s ago" if self._last_heartbeat else "No heartbeat",
        ))

        # Provider errors
        checks.append(HealthCheck(
            name="provider_errors",
            status=HealthStatus.HEALTHY if self._provider_errors == 0 else HealthStatus.DEGRADED,
            message=f"{self._provider_errors} errors recorded",
            metadata={"count": self._provider_errors},
        ))

        health = SystemHealth(
            checks=checks,
            fixtures_fresh=fixture_fresh,
            odds_fresh=odds_fresh,
            scheduler_alive=scheduler_alive,
            stale_jobs=stale_jobs,
            failed_jobs=self._failed_jobs,
            open_trades=open_trades,
            missing_closing_odds=missing_closing_odds,
            provider_errors=self._provider_errors,
        )
        health.compute_overall()
        return health
