"""In-Memory Research Repository.

Thread-safe in-memory implementation for testing and development.
Uses threading locks for atomic task claiming.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from src.research.persistence.repository import ResearchRepository


class InMemoryResearchRepository(ResearchRepository):
    """In-memory repository for testing.

    Thread-safe via threading.Lock for concurrent task claiming.
    All data lost when instance is garbage collected.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._candidates: dict[str, dict[str, Any]] = {}
        self._hypotheses: dict[str, dict[str, Any]] = {}
        self._experiments: dict[str, dict[str, Any]] = {}
        self._walkforwards: dict[str, dict[str, Any]] = {}
        self._governance: dict[str, list[dict[str, Any]]] = {}
        self._proposals: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}

    # ═══ RUNS ═══

    def save_run(self, run_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if run_id in self._runs:
                return False
            self._runs[run_id] = {**data, "_id": run_id, "_created_at": time.time()}
            return True

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        return self._runs.get(run_id)

    def list_runs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        runs = sorted(self._runs.values(), key=lambda r: r.get("_created_at", 0), reverse=True)
        return runs[offset:offset + limit]

    # ═══ CANDIDATES ═══

    def save_candidate(self, content_hash: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if content_hash in self._candidates:
                return False
            self._candidates[content_hash] = {**data, "_hash": content_hash, "_created_at": time.time()}
            return True

    def get_candidate(self, content_hash: str) -> Optional[dict[str, Any]]:
        return self._candidates.get(content_hash)

    def candidate_exists(self, content_hash: str) -> bool:
        return content_hash in self._candidates

    def list_candidates(self, market_type: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        items = list(self._candidates.values())
        if market_type:
            items = [c for c in items if c.get("market_type") == market_type]
        return items[offset:offset + limit]

    # ═══ HYPOTHESES ═══

    def save_hypothesis(self, content_hash: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if content_hash in self._hypotheses:
                return False
            self._hypotheses[content_hash] = {**data, "_hash": content_hash, "_created_at": time.time()}
            return True

    def get_hypothesis(self, content_hash: str) -> Optional[dict[str, Any]]:
        return self._hypotheses.get(content_hash)

    def hypothesis_exists(self, content_hash: str) -> bool:
        return content_hash in self._hypotheses

    # ═══ EXPERIMENTS ═══

    def save_experiment(self, experiment_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if experiment_id in self._experiments:
                return False
            self._experiments[experiment_id] = {**data, "_id": experiment_id, "_created_at": time.time()}
            return True

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        return self._experiments.get(experiment_id)

    def experiment_exists(self, experiment_id: str) -> bool:
        return experiment_id in self._experiments

    # ═══ WALK-FORWARD ═══

    def save_walkforward(self, content_hash: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if content_hash in self._walkforwards:
                return False
            self._walkforwards[content_hash] = {**data, "_hash": content_hash, "_created_at": time.time()}
            return True

    def get_walkforward(self, content_hash: str) -> Optional[dict[str, Any]]:
        return self._walkforwards.get(content_hash)

    # ═══ GOVERNANCE ═══

    def save_governance_decision(self, hypothesis_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if hypothesis_id not in self._governance:
                self._governance[hypothesis_id] = []
            self._governance[hypothesis_id].append({**data, "_created_at": time.time()})
            return True

    def get_governance_decisions(self, hypothesis_id: str) -> list[dict[str, Any]]:
        return self._governance.get(hypothesis_id, [])

    # ═══ PROPOSALS ═══

    def save_proposal(self, proposal_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if proposal_id in self._proposals:
                return False
            self._proposals[proposal_id] = {**data, "_id": proposal_id, "_created_at": time.time()}
            return True

    def get_proposal(self, proposal_id: str) -> Optional[dict[str, Any]]:
        return self._proposals.get(proposal_id)

    # ═══ TASKS ═══

    def save_task(self, task_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if task_id in self._tasks:
                return False
            self._tasks[task_id] = {**data, "_id": task_id, "_created_at": time.time()}
            return True

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, updates: dict[str, Any]) -> bool:
        with self._lock:
            if task_id not in self._tasks:
                return False
            self._tasks[task_id].update(updates)
            return True

    def claim_next_task(self, worker_id: str) -> Optional[dict[str, Any]]:
        """Atomically claim the next PENDING task.

        Thread-safe: lock prevents double-claiming.
        """
        with self._lock:
            for task_id, task in self._tasks.items():
                if task.get("status") == "PENDING":
                    task["status"] = "CLAIMED"
                    task["claimed_by"] = worker_id
                    task["claimed_at"] = time.time()
                    return dict(task)
            return None

    def list_tasks(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self._tasks.values())
        if status:
            items = [t for t in items if t.get("status") == status]
        return items[:limit]

    # ═══ STATISTICS ═══

    def count_candidates(self) -> int:
        return len(self._candidates)

    def count_experiments(self) -> int:
        return len(self._experiments)

    def count_tasks(self, status: Optional[str] = None) -> int:
        if status:
            return sum(1 for t in self._tasks.values() if t.get("status") == status)
        return len(self._tasks)
