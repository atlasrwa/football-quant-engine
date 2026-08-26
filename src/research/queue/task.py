"""Research Task — unit of work in the research queue.

Explicit state machine with guarded transitions.
Invalid transitions are rejected.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """Research task lifecycle states."""

    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYABLE = "RETRYABLE"
    REJECTED = "REJECTED"


class TaskType(Enum):
    """Types of research tasks."""

    EXPERIMENT = "EXPERIMENT"
    WALK_FORWARD = "WALK_FORWARD"
    FDR_CORRECTION = "FDR_CORRECTION"
    GOVERNANCE = "GOVERNANCE"
    DISCOVERY = "DISCOVERY"
    AI_PROPOSAL = "AI_PROPOSAL"


# Valid state transitions
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.CLAIMED, TaskStatus.CANCELLED, TaskStatus.REJECTED},
    TaskStatus.CLAIMED: {TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),  # Terminal
    TaskStatus.FAILED: {TaskStatus.RETRYABLE, TaskStatus.REJECTED},
    TaskStatus.CANCELLED: set(),  # Terminal
    TaskStatus.RETRYABLE: {TaskStatus.PENDING},
    TaskStatus.REJECTED: set(),  # Terminal
}


@dataclass
class ResearchTask:
    """A unit of research work.

    Attributes:
        task_id: Deterministic identity (content hash of payload).
        task_type: What kind of research this is.
        status: Current lifecycle state.
        priority: Higher = more urgent (default 0).
        candidate_hash: Associated candidate content hash.
        hypothesis_hash: Associated hypothesis content hash.
        research_run_id: Parent research run.
        requested_by: Source of the request (DETERMINISTIC/AI/HUMAN).
        payload: Task-specific configuration.
        result_reference: Pointer to result after completion.
        error_message: Error details if failed.
        attempt_count: Number of execution attempts.
        max_attempts: Maximum retry attempts.
        created_at: Creation timestamp.
        claimed_by: Worker that claimed the task.
        claimed_at: When the task was claimed.
        started_at: When execution began.
        completed_at: When task completed/failed.
    """

    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    candidate_hash: str = ""
    hypothesis_hash: str = ""
    research_run_id: str = ""
    requested_by: str = "DETERMINISTIC"
    payload: dict[str, Any] = field(default_factory=dict)
    result_reference: str = ""
    error_message: str = ""
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    claimed_by: str = ""
    claimed_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def content_hash(self) -> str:
        """Deterministic identity based on task content (not status/timing)."""
        canonical = json.dumps({
            "task_type": self.task_type.value,
            "candidate_hash": self.candidate_hash,
            "hypothesis_hash": self.hypothesis_hash,
            "research_run_id": self.research_run_id,
            "payload": self.payload,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def is_terminal(self) -> bool:
        """Whether this task is in a terminal state."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.REJECTED)

    @property
    def can_retry(self) -> bool:
        """Whether this task can be retried."""
        return (
            self.status == TaskStatus.FAILED
            and self.attempt_count < self.max_attempts
        )

    def transition(self, new_status: TaskStatus) -> None:
        """Transition to a new state. Raises ValueError on invalid transition."""
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Valid: {[s.value for s in valid]}"
            )
        self.status = new_status

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "priority": self.priority,
            "candidate_hash": self.candidate_hash,
            "hypothesis_hash": self.hypothesis_hash,
            "research_run_id": self.research_run_id,
            "requested_by": self.requested_by,
            "payload": self.payload,
            "result_reference": self.result_reference,
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "claimed_by": self.claimed_by,
            "content_hash": self.content_hash,
        }

    @staticmethod
    def create(
        task_type: TaskType,
        candidate_hash: str = "",
        hypothesis_hash: str = "",
        research_run_id: str = "",
        requested_by: str = "DETERMINISTIC",
        payload: Optional[dict[str, Any]] = None,
        priority: int = 0,
        max_attempts: int = 3,
    ) -> "ResearchTask":
        """Create a task with deterministic ID."""
        task = ResearchTask(
            task_id="",  # Will be set from content_hash
            task_type=task_type,
            candidate_hash=candidate_hash,
            hypothesis_hash=hypothesis_hash,
            research_run_id=research_run_id,
            requested_by=requested_by,
            payload=payload or {},
            priority=priority,
            max_attempts=max_attempts,
        )
        task.task_id = task.content_hash
        return task
