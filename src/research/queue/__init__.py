"""Batch 7 — Research Queue.

Manages research task lifecycle with explicit state machine,
atomic claiming, retry logic, and idempotency.

Task states: PENDING → CLAIMED → RUNNING → COMPLETED/FAILED/CANCELLED
             FAILED → RETRYABLE → PENDING (retry)
"""

from src.research.queue.task import ResearchTask, TaskStatus, TaskType
from src.research.queue.manager import QueueManager

__all__ = ["ResearchTask", "TaskStatus", "TaskType", "QueueManager"]
