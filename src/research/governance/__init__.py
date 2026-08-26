"""Batch 5 — Research Governance.

Manages the lifecycle of research candidates from discovery
through quarantine eligibility.

State machine:
    DISCOVERED → PROMISING → WALK_FORWARD_VALIDATED → FDR_VALIDATED
    → QUARANTINE_ELIGIBLE → QUARANTINED → REJECTED

Governance criteria are configurable — not hard-coded universal truths.

IMPORTANT: Quarantine eligibility != production readiness.
"""

from src.research.governance.classifier import (
    GovernanceClassifier,
    GovernanceCriteria,
    GovernanceDecision,
    GovernanceState,
)
from src.research.governance.quarantine_adapter import QuarantineAdapter
from src.research.governance.identity import ResearchRunIdentity

__all__ = [
    "GovernanceClassifier",
    "GovernanceCriteria",
    "GovernanceDecision",
    "GovernanceState",
    "QuarantineAdapter",
    "ResearchRunIdentity",
]
