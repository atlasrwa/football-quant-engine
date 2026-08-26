"""Scheduler Jobs — bounded, idempotent work units for forward research.

Job types map to orchestrator operations with dependency enforcement.
Each job has deterministic identity, bounded execution, and explicit lifecycle.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JobType(Enum):
    """Types of scheduled jobs in the forward pipeline."""
    REFRESH_FIXTURES = "REFRESH_FIXTURES"
    DETECT_FIXTURE_CHANGES = "DETECT_FIXTURE_CHANGES"
    BUILD_SNAPSHOTS = "BUILD_SNAPSHOTS"
    CAPTURE_PREMATCH_ODDS = "CAPTURE_PREMATCH_ODDS"
    EVALUATE_ELIGIBILITY = "EVALUATE_ELIGIBILITY"
    GENERATE_PAPER_TRADES = "GENERATE_PAPER_TRADES"
    MONITOR_OPEN_TRADES = "MONITOR_OPEN_TRADES"
    DETECT_COMPLETED = "DETECT_COMPLETED"
    SETTLE_TRADES = "SETTLE_TRADES"
    RETRIEVE_CLOSING_ODDS = "RETRIEVE_CLOSING_ODDS"
    CALCULATE_CLV = "CALCULATE_CLV"
    GENERATE_REPORTS = "GENERATE_REPORTS"
    AI_RESEARCH_CYCLE = "AI_RESEARCH_CYCLE"


class JobStatus(Enum):
    """Job lifecycle states."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYABLE = "RETRYABLE"
    SKIPPED = "SKIPPED"
    TIMEOUT = "TIMEOUT"


# Job dependency graph: job → required predecessors
JOB_DEPENDENCIES: dict[JobType, list[JobType]] = {
    JobType.REFRESH_FIXTURES: [],
    JobType.DETECT_FIXTURE_CHANGES: [JobType.REFRESH_FIXTURES],
    JobType.BUILD_SNAPSHOTS: [JobType.REFRESH_FIXTURES],
    JobType.CAPTURE_PREMATCH_ODDS: [JobType.REFRESH_FIXTURES],
    JobType.EVALUATE_ELIGIBILITY: [JobType.BUILD_SNAPSHOTS, JobType.CAPTURE_PREMATCH_ODDS],
    JobType.GENERATE_PAPER_TRADES: [JobType.EVALUATE_ELIGIBILITY],
    JobType.MONITOR_OPEN_TRADES: [],
    JobType.DETECT_COMPLETED: [JobType.REFRESH_FIXTURES],
    JobType.SETTLE_TRADES: [JobType.DETECT_COMPLETED],
    JobType.RETRIEVE_CLOSING_ODDS: [JobType.SETTLE_TRADES],
    JobType.CALCULATE_CLV: [JobType.RETRIEVE_CLOSING_ODDS],
    JobType.GENERATE_REPORTS: [JobType.CALCULATE_CLV],
    JobType.AI_RESEARCH_CYCLE: [],  # Independent, budget-bounded
}


@dataclass
class SchedulerJob:
    """A single scheduled job execution."""
    job_id: str = ""
    job_type: JobType = JobType.REFRESH_FIXTURES
    status: JobStatus = JobStatus.PENDING
    scheduled_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    attempt_count: int = 0
    max_attempts: int = 3
    timeout_seconds: float = 300.0
    error_message: str = ""
    result_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.job_id:
            # Deterministic ID from type + scheduled time (rounded to minute)
            rounded = int(self.scheduled_at // 60) * 60
            canonical = json.dumps({
                "job_type": self.job_type.value,
                "scheduled_at_minute": rounded,
            }, sort_keys=True, separators=(",", ":"))
            self.job_id = hashlib.sha256(canonical.encode()).hexdigest()[:12]

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.SKIPPED)

    @property
    def is_timed_out(self) -> bool:
        if self.status != JobStatus.RUNNING:
            return False
        return (time.time() - self.started_at) > self.timeout_seconds

    @property
    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "timeout_seconds": self.timeout_seconds,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class JobResult:
    """Immutable result of a job execution."""
    job_id: str
    job_type: JobType
    success: bool
    duration_seconds: float = 0.0
    items_processed: int = 0
    errors: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "success": self.success,
            "duration_seconds": round(self.duration_seconds, 2),
            "items_processed": self.items_processed,
            "errors": list(self.errors),
        }
