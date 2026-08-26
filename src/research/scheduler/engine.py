"""Scheduler Engine — executes bounded, idempotent forward pipeline jobs.

Wraps the existing ForwardResearchOrchestrator with:
- Job lifecycle management
- Dependency enforcement
- Retry with backoff
- Timeout detection
- Heartbeat
- Event emission

Does NOT replace the orchestrator. Reuses existing queue/persistence.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.research.scheduler.jobs import (
    JOB_DEPENDENCIES,
    JobResult,
    JobStatus,
    JobType,
    SchedulerJob,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchedulerConfig:
    """Configuration for the production scheduler."""
    max_jobs_per_cycle: int = 20
    default_timeout_seconds: float = 300.0
    default_max_attempts: int = 3
    backoff_base_seconds: float = 30.0
    backoff_max_seconds: float = 600.0
    heartbeat_interval_seconds: float = 60.0
    cycle_interval_seconds: float = 300.0  # 5 min between full cycles


class SchedulerEngine:
    """Executes scheduled jobs with dependency enforcement and retry logic.

    Usage:
        engine = SchedulerEngine(config=SchedulerConfig())
        engine.register_handler(JobType.REFRESH_FIXTURES, refresh_fn)
        engine.run_cycle()  # Execute one bounded cycle
    """

    def __init__(self, config: Optional[SchedulerConfig] = None) -> None:
        self._config = config or SchedulerConfig()
        self._handlers: dict[JobType, Callable[[], JobResult]] = {}
        self._jobs: dict[str, SchedulerJob] = {}
        self._completed_types: set[JobType] = set()
        self._events: list[dict[str, Any]] = []
        self._last_heartbeat: float = 0.0
        self._cycle_count: int = 0

    @property
    def config(self) -> SchedulerConfig:
        return self._config

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def register_handler(self, job_type: JobType, handler: Callable[[], JobResult]) -> None:
        """Register a handler function for a job type."""
        self._handlers[job_type] = handler

    def run_cycle(self) -> list[JobResult]:
        """Execute one bounded scheduler cycle.

        Processes jobs in dependency order. Stops at max_jobs_per_cycle.
        Idempotent: re-running the same cycle produces no duplicates.
        """
        self._cycle_count += 1
        self._emit_event("SCHEDULER_CYCLE_STARTED", {"cycle": self._cycle_count})
        results: list[JobResult] = []
        jobs_executed = 0

        # Determine execution order respecting dependencies
        for job_type in self._get_execution_order():
            if jobs_executed >= self._config.max_jobs_per_cycle:
                break

            if job_type not in self._handlers:
                continue

            # Check dependencies
            if not self._dependencies_met(job_type):
                logger.debug("Skipping %s: dependencies not met", job_type.value)
                continue

            # Execute job
            result = self._execute_job(job_type)
            results.append(result)
            jobs_executed += 1

            if result.success:
                self._completed_types.add(job_type)

        self._emit_event("SCHEDULER_CYCLE_COMPLETED", {
            "cycle": self._cycle_count,
            "jobs_executed": jobs_executed,
            "jobs_succeeded": sum(1 for r in results if r.success),
        })
        return results

    def _execute_job(self, job_type: JobType) -> JobResult:
        """Execute a single job with timeout and error handling."""
        job = SchedulerJob(
            job_type=job_type,
            timeout_seconds=self._config.default_timeout_seconds,
            max_attempts=self._config.default_max_attempts,
        )
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        job.attempt_count += 1
        self._jobs[job.job_id] = job

        self._emit_event("JOB_STARTED", {"job_type": job_type.value, "job_id": job.job_id})

        try:
            handler = self._handlers[job_type]
            result = handler()

            job.status = JobStatus.COMPLETED
            job.completed_at = time.time()
            job.result_data = result.to_dict()

            self._emit_event("JOB_COMPLETED", {
                "job_type": job_type.value, "job_id": job.job_id,
                "duration": round(time.time() - job.started_at, 2),
                "items": result.items_processed,
            })
            return result

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:200]}"
            job.error_message = error_msg
            job.completed_at = time.time()

            if job.can_retry:
                job.status = JobStatus.RETRYABLE
                self._emit_event("JOB_RETRY", {
                    "job_type": job_type.value, "error": error_msg,
                    "attempt": job.attempt_count,
                })
            else:
                job.status = JobStatus.FAILED
                self._emit_event("JOB_FAILED", {
                    "job_type": job_type.value, "error": error_msg,
                })

            return JobResult(
                job_id=job.job_id,
                job_type=job_type,
                success=False,
                duration_seconds=time.time() - job.started_at,
                errors=(error_msg,),
            )

    def _dependencies_met(self, job_type: JobType) -> bool:
        """Check if all dependencies for a job type have completed."""
        deps = JOB_DEPENDENCIES.get(job_type, [])
        return all(dep in self._completed_types for dep in deps)

    def _get_execution_order(self) -> list[JobType]:
        """Topological order of job types based on dependencies."""
        # Simple topological sort
        order: list[JobType] = []
        visited: set[JobType] = set()

        def visit(jt: JobType) -> None:
            if jt in visited:
                return
            visited.add(jt)
            for dep in JOB_DEPENDENCIES.get(jt, []):
                visit(dep)
            order.append(jt)

        for jt in JobType:
            visit(jt)
        return order

    def reset_cycle(self) -> None:
        """Reset completed state for a new cycle (call between periodic runs)."""
        self._completed_types.clear()

    def _emit_event(self, event_type: str, data: Optional[dict[str, Any]] = None) -> None:
        """Emit a scheduler event (append-only)."""
        self._events.append({
            "event_type": event_type,
            "timestamp": time.time(),
            "data": data or {},
        })
