"""Research memory — persistent knowledge store.

Tracks all tested hypotheses, their results, and relationships.
Prevents repeatedly testing the same hypothesis. Enables the AI
research agent to learn from past experiments.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.research.candidate_generator import ResearchHypothesis
from src.research.experiment import ExperimentResult, ExperimentStatus


class HypothesisStatus(Enum):
    """Status of a hypothesis in research memory."""
    UNTESTED = "UNTESTED"
    TESTED = "TESTED"
    PROMISING = "PROMISING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"


@dataclass
class MemoryEntry:
    """A single entry in research memory."""
    hypothesis: ResearchHypothesis
    content_hash: str
    status: HypothesisStatus
    result: Optional[ExperimentResult] = None
    parent_id: Optional[str] = None  # Links to parent experiment
    children_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tested_at: Optional[str] = None


class ResearchMemory:
    """Persistent research knowledge store.

    Responsibilities:
    - Store all tested hypotheses and results
    - Detect duplicate hypotheses via content hash
    - Track parent-child relationships between experiments
    - Provide retrieval for AI agent learning
    - Prevent redundant work
    """

    def __init__(self) -> None:
        self._entries: dict[str, MemoryEntry] = {}  # hypothesis_id → entry
        self._hash_index: dict[str, str] = {}  # content_hash → hypothesis_id

    def store_hypothesis(self, hypothesis: ResearchHypothesis) -> tuple[str, bool]:
        """Store a hypothesis. Returns (hypothesis_id, is_new).

        If the hypothesis has already been tested (same content hash),
        returns the existing entry and is_new=False.
        """
        h_hash = hypothesis.content_hash
        if h_hash in self._hash_index:
            return self._hash_index[h_hash], False

        entry = MemoryEntry(
            hypothesis=hypothesis,
            content_hash=h_hash,
            status=HypothesisStatus.UNTESTED,
        )
        self._entries[hypothesis.hypothesis_id] = entry
        self._hash_index[h_hash] = hypothesis.hypothesis_id
        return hypothesis.hypothesis_id, True

    def store_result(
        self,
        hypothesis_id: str,
        result: ExperimentResult,
    ) -> None:
        """Store an experiment result for a hypothesis."""
        entry = self._entries.get(hypothesis_id)
        if entry is None:
            return

        entry.result = result
        entry.tested_at = datetime.now(timezone.utc).isoformat()

        # Classify result
        if result.status == ExperimentStatus.FAILED:
            entry.status = HypothesisStatus.REJECTED
        elif result.is_significant and result.roi_pct > 3.0:
            entry.status = HypothesisStatus.VALIDATED
        elif result.roi_pct > 0:
            entry.status = HypothesisStatus.PROMISING
        else:
            entry.status = HypothesisStatus.REJECTED

        entry.status = (
            HypothesisStatus.TESTED if entry.status == HypothesisStatus.UNTESTED
            else entry.status
        )

    def is_duplicate(self, hypothesis: ResearchHypothesis) -> bool:
        """Check if a hypothesis has already been tested."""
        return hypothesis.content_hash in self._hash_index

    def link_experiments(self, parent_id: str, child_id: str) -> None:
        """Link a child experiment to its parent (follow-up)."""
        parent = self._entries.get(parent_id)
        child = self._entries.get(child_id)
        if parent:
            parent.children_ids.append(child_id)
        if child:
            child.parent_id = parent_id

    def get_entry(self, hypothesis_id: str) -> Optional[MemoryEntry]:
        """Get a memory entry by hypothesis ID."""
        return self._entries.get(hypothesis_id)

    def get_by_status(self, status: HypothesisStatus) -> list[MemoryEntry]:
        """Get all entries with a specific status."""
        return [e for e in self._entries.values() if e.status == status]

    def get_promising(self) -> list[MemoryEntry]:
        """Get all promising and validated hypotheses."""
        return [
            e for e in self._entries.values()
            if e.status in (HypothesisStatus.PROMISING, HypothesisStatus.VALIDATED)
        ]

    def get_all_results(self) -> list[ExperimentResult]:
        """Get all experiment results."""
        return [e.result for e in self._entries.values() if e.result is not None]

    def get_summary(self) -> dict[str, int]:
        """Get counts by status."""
        summary: dict[str, int] = {}
        for e in self._entries.values():
            key = e.status.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    @property
    def total_experiments(self) -> int:
        """Total number of hypotheses stored."""
        return len(self._entries)

    @property
    def total_tested(self) -> int:
        """Number of hypotheses that have been evaluated."""
        return sum(1 for e in self._entries.values() if e.result is not None)

    def to_context(self, max_entries: int = 20) -> str:
        """Generate a text summary for the AI research agent.

        Provides recent experiment results for learning.
        """
        tested = [e for e in self._entries.values() if e.result is not None]
        tested.sort(key=lambda e: e.tested_at or "", reverse=True)
        tested = tested[:max_entries]

        lines = [f"Research Memory Summary: {self.total_tested}/{self.total_experiments} tested"]
        summary = self.get_summary()
        lines.append(f"Status: {json.dumps(summary)}")
        lines.append("")

        for e in tested:
            r = e.result
            lines.append(
                f"- {e.hypothesis.hypothesis_id}: "
                f"status={e.status.value}, "
                f"roi={r.roi_pct:.1f}%, "
                f"bets={r.n_bets}, "
                f"p={r.p_value:.4f}" if r.p_value else f"- {e.hypothesis.hypothesis_id}: no p-value"
            )

        return "\n".join(lines)
