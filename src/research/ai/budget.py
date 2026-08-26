"""Research Budget — controls and limits for research runs.

Prevents:
- Unlimited experiments
- Unlimited AI calls
- Infinite loops
- Unbounded costs
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ResearchBudget:
    """Configurable budget for a research run.

    Exhaustion is explicit — never silently continues.
    """

    max_tasks: int = 100
    max_experiments: int = 50
    max_ai_proposals: int = 20
    max_candidates: int = 200
    max_runtime_seconds: float = 3600.0  # 1 hour
    max_tokens_per_call: int = 2000
    max_retries: int = 3

    # Counters
    tasks_used: int = 0
    experiments_used: int = 0
    ai_proposals_used: int = 0
    candidates_used: int = 0
    tokens_used: int = 0
    elapsed_seconds: float = 0.0

    @property
    def tasks_remaining(self) -> int:
        return max(0, self.max_tasks - self.tasks_used)

    @property
    def experiments_remaining(self) -> int:
        return max(0, self.max_experiments - self.experiments_used)

    @property
    def ai_proposals_remaining(self) -> int:
        return max(0, self.max_ai_proposals - self.ai_proposals_used)

    @property
    def is_exhausted(self) -> bool:
        """Whether any budget limit has been reached."""
        return (
            self.tasks_used >= self.max_tasks
            or self.experiments_used >= self.max_experiments
            or self.ai_proposals_used >= self.max_ai_proposals
            or self.candidates_used >= self.max_candidates
            or self.elapsed_seconds >= self.max_runtime_seconds
        )

    @property
    def exhaustion_reason(self) -> str:
        """Why the budget was exhausted."""
        if self.tasks_used >= self.max_tasks:
            return f"max_tasks ({self.max_tasks}) reached"
        if self.experiments_used >= self.max_experiments:
            return f"max_experiments ({self.max_experiments}) reached"
        if self.ai_proposals_used >= self.max_ai_proposals:
            return f"max_ai_proposals ({self.max_ai_proposals}) reached"
        if self.candidates_used >= self.max_candidates:
            return f"max_candidates ({self.max_candidates}) reached"
        if self.elapsed_seconds >= self.max_runtime_seconds:
            return f"max_runtime ({self.max_runtime_seconds}s) reached"
        return ""

    def use_task(self) -> bool:
        """Consume a task. Returns False if exhausted."""
        if self.tasks_used >= self.max_tasks:
            return False
        self.tasks_used += 1
        return True

    def use_experiment(self) -> bool:
        if self.experiments_used >= self.max_experiments:
            return False
        self.experiments_used += 1
        return True

    def use_ai_proposal(self) -> bool:
        if self.ai_proposals_used >= self.max_ai_proposals:
            return False
        self.ai_proposals_used += 1
        return True

    def use_candidate(self) -> bool:
        if self.candidates_used >= self.max_candidates:
            return False
        self.candidates_used += 1
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tasks": self.max_tasks,
            "max_experiments": self.max_experiments,
            "max_ai_proposals": self.max_ai_proposals,
            "tasks_used": self.tasks_used,
            "experiments_used": self.experiments_used,
            "ai_proposals_used": self.ai_proposals_used,
            "is_exhausted": self.is_exhausted,
            "exhaustion_reason": self.exhaustion_reason,
        }
