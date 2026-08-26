"""Queue Manager — orchestrates task lifecycle.

Provides safe task claiming, retry logic, stale recovery,
and idempotent submission.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.research.persistence.repository import ResearchRepository
from src.research.queue.task import ResearchTask, TaskStatus, TaskType

logger = logging.getLogger(__name__)

_STALE_TIMEOUT = 3600.0  # 1 hour — claimed but not started


class QueueManager:
    """Manages the research task queue.

    Features:
    - Idempotent submission (same content → same task)
    - Atomic claiming via repository
    - Retry with bounded attempts
    - Stale task recovery
    """

    def __init__(self, repository: ResearchRepository, stale_timeout: float = _STALE_TIMEOUT) -> None:
        self._repo = repository
        self._stale_timeout = stale_timeout

    def submit(self, task: ResearchTask) -> tuple[str, bool]:
        """Submit a task. Idempotent: returns existing if duplicate.

        Returns:
            (task_id, is_new) — is_new=False means existing task reused.
        """
        # Check if identical task already exists
        existing = self._repo.get_task(task.task_id)
        if existing is not None:
            logger.info("Task %s already exists (status: %s)", task.task_id, existing.get("status"))
            return task.task_id, False

        # Save new task
        saved = self._repo.save_task(task.task_id, task.to_dict())
        if not saved:
            # Race condition: another thread saved it first
            return task.task_id, False

        logger.info("Task %s submitted (type: %s)", task.task_id, task.task_type.value)
        return task.task_id, True

    def claim(self, worker_id: str) -> Optional[dict[str, Any]]:
        """Claim the next available task atomically.

        Args:
            worker_id: Identifier of the claiming worker.

        Returns:
            Task dict or None if queue empty.
        """
        task_data = self._repo.claim_next_task(worker_id)
        if task_data:
            logger.info("Worker %s claimed task %s", worker_id, task_data.get("_id", "?"))
        return task_data

    def start(self, task_id: str) -> bool:
        """Mark a claimed task as running."""
        task_data = self._repo.get_task(task_id)
        if not task_data or task_data.get("status") != TaskStatus.CLAIMED.value:
            return False
        return self._repo.update_task(task_id, {
            "status": TaskStatus.RUNNING.value,
            "started_at": time.time(),
            "attempt_count": task_data.get("attempt_count", 0) + 1,
        })

    def complete(self, task_id: str, result_reference: str = "") -> bool:
        """Mark a running task as completed."""
        task_data = self._repo.get_task(task_id)
        if not task_data or task_data.get("status") != TaskStatus.RUNNING.value:
            return False
        return self._repo.update_task(task_id, {
            "status": TaskStatus.COMPLETED.value,
            "completed_at": time.time(),
            "result_reference": result_reference,
        })

    def fail(self, task_id: str, error_message: str = "") -> bool:
        """Mark a running task as failed. May be retryable."""
        task_data = self._repo.get_task(task_id)
        if not task_data or task_data.get("status") != TaskStatus.RUNNING.value:
            return False

        attempt_count = task_data.get("attempt_count", 1)
        max_attempts = task_data.get("max_attempts", 3)

        if attempt_count < max_attempts:
            new_status = TaskStatus.RETRYABLE.value
        else:
            new_status = TaskStatus.FAILED.value

        return self._repo.update_task(task_id, {
            "status": new_status,
            "error_message": error_message,
            "completed_at": time.time(),
        })

    def retry(self, task_id: str) -> bool:
        """Move a retryable task back to PENDING."""
        task_data = self._repo.get_task(task_id)
        if not task_data or task_data.get("status") != TaskStatus.RETRYABLE.value:
            return False
        return self._repo.update_task(task_id, {
            "status": TaskStatus.PENDING.value,
            "claimed_by": "",
            "claimed_at": 0.0,
            "started_at": 0.0,
        })

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or claimed task."""
        task_data = self._repo.get_task(task_id)
        if not task_data:
            return False
        status = task_data.get("status")
        if status not in (TaskStatus.PENDING.value, TaskStatus.CLAIMED.value):
            return False
        return self._repo.update_task(task_id, {
            "status": TaskStatus.CANCELLED.value,
            "completed_at": time.time(),
        })

    def recover_stale(self) -> int:
        """Recover tasks claimed but not started within timeout.

        Returns number of recovered tasks.
        """
        now = time.time()
        recovered = 0
        claimed_tasks = self._repo.list_tasks(status=TaskStatus.CLAIMED.value)
        for task_data in claimed_tasks:
            claimed_at = task_data.get("claimed_at", 0)
            if now - claimed_at > self._stale_timeout:
                task_id = task_data.get("_id") or task_data.get("task_id")
                if task_id:
                    self._repo.update_task(task_id, {
                        "status": TaskStatus.PENDING.value,
                        "claimed_by": "",
                        "claimed_at": 0.0,
                    })
                    recovered += 1
                    logger.warning("Recovered stale task %s", task_id)
        return recovered

    def queue_depth(self) -> int:
        """Number of pending tasks."""
        return self._repo.count_tasks(status=TaskStatus.PENDING.value)
