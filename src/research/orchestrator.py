"""Research Orchestrator — coordinates bounded research execution.

Manages the full research lifecycle:
    Plan → Queue → Execute → Persist → Resume

Features:
- Run lifecycle state machine (CREATED → RUNNING → COMPLETED/FAILED)
- Resumability after crash (skip completed, retry failed)
- Budget enforcement (max tasks, experiments, runtime)
- Event trail for auditability
- Idempotent execution (duplicate experiments impossible)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from src.research.ai.budget import ResearchBudget
from src.research.persistence.repository import ResearchRepository
from src.research.persistence.research_memory import ResearchMemory
from src.research.queue.manager import QueueManager
from src.research.queue.task import ResearchTask, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Research run lifecycle states."""
    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


# Valid run state transitions
_RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.PLANNED, RunStatus.CANCELLED},
    RunStatus.PLANNED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.PAUSED, RunStatus.BUDGET_EXHAUSTED, RunStatus.CANCELLED},
    RunStatus.PAUSED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
    RunStatus.BUDGET_EXHAUSTED: set(),
}


@dataclass
class RunState:
    """Persistent state of a research run."""
    run_id: str
    status: RunStatus = RunStatus.CREATED
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "skipped_tasks": self.skipped_tasks,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }


# Type alias for task executor function
TaskExecutor = Callable[[dict[str, Any]], Optional[str]]


class ResearchOrchestrator:
    """Coordinates bounded research execution with resumability.

    Usage:
        orchestrator = ResearchOrchestrator(repo, queue_manager, memory, budget)
        orchestrator.plan(run_id, tasks)
        orchestrator.execute(run_id, worker_id, executor_fn)
    """

    def __init__(
        self,
        repository: ResearchRepository,
        queue_manager: QueueManager,
        memory: ResearchMemory,
        budget: Optional[ResearchBudget] = None,
        worker_id: str = "orchestrator_default",
    ) -> None:
        self._repo = repository
        self._queue = queue_manager
        self._memory = memory
        self._budget = budget or ResearchBudget()
        self._worker_id = worker_id

    @property
    def budget(self) -> ResearchBudget:
        return self._budget

    def plan(self, run_id: str, tasks: list[ResearchTask]) -> RunState:
        """Plan a research run by submitting tasks to the queue.

        Idempotent: re-planning with same tasks has no effect.

        Args:
            run_id: Deterministic research run identity.
            tasks: Tasks to execute in this run.

        Returns:
            RunState after planning.
        """
        state = RunState(run_id=run_id, total_tasks=len(tasks))

        # Save or reuse existing run
        existing = self._repo.get_run(run_id)
        if existing and existing.get("status") in (
            RunStatus.COMPLETED.value, RunStatus.CANCELLED.value, RunStatus.BUDGET_EXHAUSTED.value
        ):
            # Run already terminal — return its state
            state.status = RunStatus(existing["status"])
            state.completed_tasks = existing.get("completed_tasks", 0)
            return state

        self._repo.save_run(run_id, {**state.to_dict(), "status": RunStatus.PLANNED.value})
        self._emit_event("RUN_PLANNED", "run", run_id, {"total_tasks": len(tasks)})

        # Submit tasks (idempotent)
        submitted = 0
        skipped = 0
        for task in tasks:
            # Check if experiment already done
            exp_id = task.payload.get("experiment_id", "")
            if exp_id and self._memory.should_skip_experiment(exp_id):
                skipped += 1
                continue
            task_id, is_new = self._queue.submit(task)
            if is_new:
                submitted += 1

        state.status = RunStatus.PLANNED
        state.skipped_tasks = skipped
        logger.info("Run %s planned: %d submitted, %d skipped", run_id, submitted, skipped)
        return state

    def execute(
        self,
        run_id: str,
        executor: TaskExecutor,
        max_tasks: Optional[int] = None,
    ) -> RunState:
        """Execute pending tasks for a run.

        Resumable: skips already-completed experiments.
        Budget-enforced: stops when budget is exhausted.

        Args:
            run_id: Research run to execute.
            executor: Function that executes a task and returns result_reference.
            max_tasks: Override max tasks for this execution (default: budget.max_tasks).

        Returns:
            Final RunState.
        """
        state = self._load_state(run_id)
        if state.status in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.BUDGET_EXHAUSTED):
            return state

        # Transition to RUNNING
        state.status = RunStatus.RUNNING
        state.started_at = state.started_at or time.time()
        self._save_state(state)
        self._emit_event("RUN_STARTED", "run", run_id)

        task_limit = max_tasks or self._budget.max_tasks + 1  # +1 so budget check inside loop triggers
        executed = 0

        while True:
            # Check budget BEFORE claiming next task
            if self._budget.is_exhausted:
                state.status = RunStatus.BUDGET_EXHAUSTED
                state.error_message = self._budget.exhaustion_reason
                self._save_state(state)
                self._emit_event("RUN_BUDGET_EXHAUSTED", "run", run_id, {"reason": state.error_message})
                return state

            # Check runtime
            elapsed = time.time() - state.started_at
            self._budget.elapsed_seconds = elapsed
            if self._budget.is_exhausted:
                state.status = RunStatus.BUDGET_EXHAUSTED
                state.error_message = self._budget.exhaustion_reason
                self._save_state(state)
                return state

            # Hard limit (if max_tasks param provided)
            if max_tasks and executed >= max_tasks:
                break

            # Claim next task
            task_data = self._queue.claim(self._worker_id)
            if task_data is None:
                # No more pending tasks
                break

            task_id = task_data.get("_id") or task_data.get("task_id", "")
            self._emit_event("TASK_CLAIMED", "task", task_id, {"worker": self._worker_id})

            # Start task
            self._queue.start(task_id)
            self._emit_event("TASK_STARTED", "task", task_id)

            # Execute
            try:
                result_ref = executor(task_data)
                self._queue.complete(task_id, result_reference=result_ref or "")
                state.completed_tasks += 1
                self._budget.use_experiment()
                self._emit_event("TASK_COMPLETED", "task", task_id, {"result": result_ref})
            except Exception as e:
                error_msg = str(e)[:500]
                self._queue.fail(task_id, error_message=error_msg)
                state.failed_tasks += 1
                self._emit_event("TASK_FAILED", "task", task_id, {"error": error_msg})
                logger.warning("Task %s failed: %s", task_id, error_msg[:100])

            executed += 1
            self._budget.use_task()

        # Check final state
        pending = self._queue.queue_depth()
        if pending == 0 and state.failed_tasks == 0:
            state.status = RunStatus.COMPLETED
        elif pending == 0:
            state.status = RunStatus.COMPLETED  # Some failed but all attempted
        else:
            state.status = RunStatus.PAUSED  # Still work remaining

        state.completed_at = time.time()
        self._save_state(state)
        self._emit_event("RUN_FINISHED", "run", run_id, state.to_dict())
        return state

    def resume(self, run_id: str, executor: TaskExecutor) -> RunState:
        """Resume an interrupted or paused run.

        Recovers stale tasks and continues execution.
        """
        # Recover any stale tasks first
        if hasattr(self._repo, "recover_stale_tasks"):
            self._repo.recover_stale_tasks()
        elif hasattr(self._queue, "recover_stale"):
            self._queue.recover_stale()

        # Retry retryable tasks
        retryable = self._repo.list_tasks(status=TaskStatus.RETRYABLE.value)
        for task_data in retryable:
            task_id = task_data.get("_id") or task_data.get("task_id", "")
            self._queue.retry(task_id)

        return self.execute(run_id, executor)

    def get_state(self, run_id: str) -> RunState:
        """Get current run state."""
        return self._load_state(run_id)

    def cancel(self, run_id: str) -> RunState:
        """Cancel a run."""
        state = self._load_state(run_id)
        if state.status in (RunStatus.COMPLETED, RunStatus.CANCELLED, RunStatus.BUDGET_EXHAUSTED):
            return state
        state.status = RunStatus.CANCELLED
        state.completed_at = time.time()
        self._save_state(state)
        self._emit_event("RUN_CANCELLED", "run", run_id)
        return state

    def _load_state(self, run_id: str) -> RunState:
        """Load run state from repository."""
        data = self._repo.get_run(run_id)
        if data is None:
            return RunState(run_id=run_id)
        return RunState(
            run_id=run_id,
            status=RunStatus(data.get("status", "CREATED")),
            total_tasks=data.get("total_tasks", 0),
            completed_tasks=data.get("completed_tasks", 0),
            failed_tasks=data.get("failed_tasks", 0),
            skipped_tasks=data.get("skipped_tasks", 0),
            started_at=data.get("started_at", 0),
            completed_at=data.get("completed_at", 0),
            error_message=data.get("error_message", ""),
        )

    def _save_state(self, state: RunState) -> None:
        """Persist run state."""
        data = state.to_dict()
        existing = self._repo.get_run(state.run_id)
        if existing:
            if hasattr(self._repo, "update_run"):
                self._repo.update_run(state.run_id, {"status": state.status.value, "data": data})
            else:
                # In-memory repo: overwrite
                self._repo._runs[state.run_id] = {**data, "_id": state.run_id, "_created_at": time.time()}
        else:
            self._repo.save_run(state.run_id, data)

    def _emit_event(self, event_type: str, entity_type: str = "", entity_id: str = "",
                    data: Optional[dict] = None) -> None:
        """Emit a research event if repository supports it."""
        if hasattr(self._repo, "append_event"):
            self._repo.append_event(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                run_id=entity_id if entity_type == "run" else "",
                worker_id=self._worker_id,
                data=data,
            )
