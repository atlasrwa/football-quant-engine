"""Research Memory — prevents duplicate research and provides history.

Answers: "What have we already tested?"
Prevents: accidental duplicate experiments.
Supports: deterministic lookup by content hash.
"""

from __future__ import annotations

from typing import Any, Optional

from src.research.persistence.repository import ResearchRepository


class ResearchMemory:
    """Query layer over the research repository for memory operations.

    Provides high-level queries:
    - Has this candidate been tested?
    - Has this hypothesis been evaluated?
    - What experiments exist for this candidate?
    - What was the governance decision?
    """

    def __init__(self, repository: ResearchRepository) -> None:
        self._repo = repository

    def has_candidate(self, content_hash: str) -> bool:
        """Check if a candidate has been seen before."""
        return self._repo.candidate_exists(content_hash)

    def has_hypothesis(self, content_hash: str) -> bool:
        """Check if a hypothesis has been tested."""
        return self._repo.hypothesis_exists(content_hash)

    def has_experiment(self, experiment_id: str) -> bool:
        """Check if an experiment has been executed."""
        return self._repo.experiment_exists(experiment_id)

    def get_candidate_history(self, content_hash: str) -> Optional[dict[str, Any]]:
        """Get full history for a candidate."""
        return self._repo.get_candidate(content_hash)

    def get_experiment_result(self, experiment_id: str) -> Optional[dict[str, Any]]:
        """Get a stored experiment result."""
        return self._repo.get_experiment(experiment_id)

    def get_governance_history(self, hypothesis_id: str) -> list[dict[str, Any]]:
        """Get all governance decisions for a hypothesis."""
        return self._repo.get_governance_decisions(hypothesis_id)

    def record_candidate(self, content_hash: str, data: dict[str, Any]) -> bool:
        """Record a candidate in memory. Returns False if duplicate."""
        return self._repo.save_candidate(content_hash, data)

    def record_hypothesis(self, content_hash: str, data: dict[str, Any]) -> bool:
        """Record a hypothesis. Returns False if duplicate."""
        return self._repo.save_hypothesis(content_hash, data)

    def record_experiment(self, experiment_id: str, data: dict[str, Any]) -> bool:
        """Record an experiment result. Returns False if duplicate."""
        return self._repo.save_experiment(experiment_id, data)

    def record_walkforward(self, content_hash: str, data: dict[str, Any]) -> bool:
        """Record a walk-forward result."""
        return self._repo.save_walkforward(content_hash, data)

    def record_governance(self, hypothesis_id: str, data: dict[str, Any]) -> bool:
        """Record a governance decision."""
        return self._repo.save_governance_decision(hypothesis_id, data)

    def should_skip_experiment(self, experiment_id: str) -> bool:
        """Check if this experiment should be skipped (already done)."""
        return self._repo.experiment_exists(experiment_id)

    def summary(self) -> dict[str, int]:
        """Get research memory statistics."""
        return {
            "candidates": self._repo.count_candidates(),
            "experiments": self._repo.count_experiments(),
            "pending_tasks": self._repo.count_tasks(status="PENDING"),
            "completed_tasks": self._repo.count_tasks(status="COMPLETED"),
        }
