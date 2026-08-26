"""Quarantine Adapter — bridges research governance to frozen QuarantineTracker.

Does NOT recreate quarantine logic.
Adapts research governance decisions to the existing
QuarantineTracker interface in src/engine/fdr.py.

Flow:
    GovernanceDecision(QUARANTINE_ELIGIBLE)
    → QuarantineAdapter.submit_for_quarantine()
    → QuarantineTracker.enter_quarantine()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from src.engine.fdr import QuarantineEntry, QuarantineStatus, QuarantineTracker
from src.research.governance.classifier import GovernanceDecision, GovernanceState


@dataclass(frozen=True)
class QuarantineSubmission:
    """Record of a research hypothesis submitted to quarantine.

    Bridges the research identity to the quarantine system.
    """

    hypothesis_id: str
    candidate_hash: str
    strategy_name: str  # Name used in QuarantineTracker
    entry_date: datetime
    governance_decision: GovernanceDecision
    quarantine_entry: Optional[QuarantineEntry] = None
    submitted: bool = False
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "candidate_hash": self.candidate_hash,
            "strategy_name": self.strategy_name,
            "entry_date": self.entry_date.isoformat(),
            "submitted": self.submitted,
            "rejection_reason": self.rejection_reason,
        }


class QuarantineAdapter:
    """Adapts research governance to the frozen QuarantineTracker.

    Determines when a hypothesis has satisfied statistical
    prerequisites for quarantine, then delegates actual
    quarantine management to QuarantineTracker.

    Does NOT:
    - Recreate quarantine logic
    - Automatically promote candidates
    - Bypass governance requirements
    """

    def __init__(self, tracker: Optional[QuarantineTracker] = None) -> None:
        """Initialize adapter.

        Args:
            tracker: QuarantineTracker instance (creates new if None).
        """
        self._tracker = tracker or QuarantineTracker()
        self._submissions: list[QuarantineSubmission] = []

    @property
    def tracker(self) -> QuarantineTracker:
        """Access the underlying QuarantineTracker."""
        return self._tracker

    @property
    def submissions(self) -> list[QuarantineSubmission]:
        """All submission records."""
        return list(self._submissions)

    def submit_for_quarantine(
        self,
        decision: GovernanceDecision,
        entry_date: Optional[datetime] = None,
    ) -> QuarantineSubmission:
        """Submit a hypothesis for quarantine based on governance decision.

        Only accepts QUARANTINE_ELIGIBLE decisions.
        Generates a strategy_name compatible with QuarantineTracker.

        Args:
            decision: Governance decision (must be QUARANTINE_ELIGIBLE).
            entry_date: Quarantine entry date (defaults to now).

        Returns:
            QuarantineSubmission record.

        Raises:
            ValueError: If decision state is not QUARANTINE_ELIGIBLE.
        """
        if decision.new_state != GovernanceState.QUARANTINE_ELIGIBLE:
            raise ValueError(
                f"Cannot submit for quarantine: state is {decision.new_state.value}, "
                f"required QUARANTINE_ELIGIBLE"
            )

        entry_dt = entry_date or datetime.utcnow()

        # Generate strategy name from research identity
        strategy_name = self._generate_strategy_name(decision)

        # Submit to frozen QuarantineTracker
        try:
            entry = self._tracker.enter_quarantine(strategy_name, entry_dt)
            submission = QuarantineSubmission(
                hypothesis_id=decision.hypothesis_id,
                candidate_hash=decision.candidate_hash,
                strategy_name=strategy_name,
                entry_date=entry_dt,
                governance_decision=decision,
                quarantine_entry=entry,
                submitted=True,
            )
        except ValueError as e:
            # Already promoted — cannot re-enter
            submission = QuarantineSubmission(
                hypothesis_id=decision.hypothesis_id,
                candidate_hash=decision.candidate_hash,
                strategy_name=strategy_name,
                entry_date=entry_dt,
                governance_decision=decision,
                submitted=False,
                rejection_reason=str(e),
            )

        self._submissions.append(submission)
        return submission

    def check_quarantine_status(self, hypothesis_id: str) -> Optional[QuarantineStatus]:
        """Check quarantine status for a hypothesis.

        Args:
            hypothesis_id: The hypothesis identifier.

        Returns:
            QuarantineStatus or None if not in quarantine.
        """
        for sub in self._submissions:
            if sub.hypothesis_id == hypothesis_id and sub.submitted:
                try:
                    return self._tracker.check_status(
                        sub.strategy_name, datetime.utcnow()
                    )
                except KeyError:
                    return None
        return None

    def _generate_strategy_name(self, decision: GovernanceDecision) -> str:
        """Generate a QuarantineTracker-compatible strategy name.

        Format: research_{candidate_hash[:8]}_{hypothesis_id[:8]}
        """
        cand = decision.candidate_hash[:8] if decision.candidate_hash else "unknown"
        hyp = decision.hypothesis_id[:8] if decision.hypothesis_id else "unknown"
        return f"research_{cand}_{hyp}"
