"""Research Repository Interface.

Defines the persistence contract for research objects.
Concrete implementations provide in-memory or PostgreSQL storage.

Domain objects are never contaminated with persistence logic.
Repository accepts/returns domain objects or simple dicts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class ResearchRepository(ABC):
    """Abstract research persistence interface.

    All methods are synchronous — research batch operations
    do not require async I/O.

    Identity is always based on content hashes, not timestamps.
    Duplicate prevention is built-in.
    """

    # ═══════════════════════════════════════════════════════════
    # RESEARCH RUNS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_run(self, run_id: str, data: dict[str, Any]) -> bool:
        """Save a research run. Returns False if already exists."""
        ...

    @abstractmethod
    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a research run by its deterministic ID."""
        ...

    @abstractmethod
    def list_runs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List research runs ordered by creation time."""
        ...

    # ═══════════════════════════════════════════════════════════
    # CANDIDATES
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_candidate(self, content_hash: str, data: dict[str, Any]) -> bool:
        """Save a candidate. Returns False if already exists."""
        ...

    @abstractmethod
    def get_candidate(self, content_hash: str) -> Optional[dict[str, Any]]:
        """Retrieve a candidate by content hash."""
        ...

    @abstractmethod
    def candidate_exists(self, content_hash: str) -> bool:
        """Check if a candidate has been seen before."""
        ...

    @abstractmethod
    def list_candidates(
        self, market_type: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List candidates with optional market filter."""
        ...

    # ═══════════════════════════════════════════════════════════
    # HYPOTHESES
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_hypothesis(self, content_hash: str, data: dict[str, Any]) -> bool:
        """Save a hypothesis. Returns False if already exists."""
        ...

    @abstractmethod
    def get_hypothesis(self, content_hash: str) -> Optional[dict[str, Any]]:
        """Retrieve a hypothesis by content hash."""
        ...

    @abstractmethod
    def hypothesis_exists(self, content_hash: str) -> bool:
        """Check if hypothesis has been tested before."""
        ...

    # ═══════════════════════════════════════════════════════════
    # EXPERIMENTS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_experiment(self, experiment_id: str, data: dict[str, Any]) -> bool:
        """Save an experiment result. Returns False if already exists."""
        ...

    @abstractmethod
    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        """Retrieve an experiment by its deterministic ID."""
        ...

    @abstractmethod
    def experiment_exists(self, experiment_id: str) -> bool:
        """Check if experiment already executed."""
        ...

    # ═══════════════════════════════════════════════════════════
    # WALK-FORWARD RESULTS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_walkforward(self, content_hash: str, data: dict[str, Any]) -> bool:
        """Save a walk-forward result."""
        ...

    @abstractmethod
    def get_walkforward(self, content_hash: str) -> Optional[dict[str, Any]]:
        """Retrieve walk-forward result."""
        ...

    # ═══════════════════════════════════════════════════════════
    # GOVERNANCE DECISIONS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_governance_decision(self, hypothesis_id: str, data: dict[str, Any]) -> bool:
        """Save a governance decision."""
        ...

    @abstractmethod
    def get_governance_decisions(self, hypothesis_id: str) -> list[dict[str, Any]]:
        """Get all governance decisions for a hypothesis."""
        ...

    # ═══════════════════════════════════════════════════════════
    # PROPOSALS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_proposal(self, proposal_id: str, data: dict[str, Any]) -> bool:
        """Save a research proposal."""
        ...

    @abstractmethod
    def get_proposal(self, proposal_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a proposal."""
        ...

    # ═══════════════════════════════════════════════════════════
    # TASKS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def save_task(self, task_id: str, data: dict[str, Any]) -> bool:
        """Save a research task."""
        ...

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a task."""
        ...

    @abstractmethod
    def update_task(self, task_id: str, updates: dict[str, Any]) -> bool:
        """Update task fields. Returns False if task not found."""
        ...

    @abstractmethod
    def claim_next_task(self, worker_id: str) -> Optional[dict[str, Any]]:
        """Atomically claim the next pending task. Returns None if empty."""
        ...

    @abstractmethod
    def list_tasks(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List tasks with optional status filter."""
        ...

    # ═══════════════════════════════════════════════════════════
    # STATISTICS
    # ═══════════════════════════════════════════════════════════

    @abstractmethod
    def count_candidates(self) -> int:
        ...

    @abstractmethod
    def count_experiments(self) -> int:
        ...

    @abstractmethod
    def count_tasks(self, status: Optional[str] = None) -> int:
        ...
