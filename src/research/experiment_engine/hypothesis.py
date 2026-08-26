"""Research hypothesis — the bridge between candidates and experiments.

A ResearchCandidate (Batch 3) is a generated metric/condition.
A Hypothesis wraps a candidate with a specific market direction
and makes it experiment-ready.

A hypothesis is NOT evidence. It is a testable claim.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.research.candidates import CandidateCondition, CandidateOperator, ResearchCandidate
from src.research.market import MarketType


class HypothesisStatus(Enum):
    """Lifecycle status of a hypothesis."""

    GENERATED = "GENERATED"
    EXPERIMENT_PENDING = "EXPERIMENT_PENDING"
    EXPERIMENT_RUNNING = "EXPERIMENT_RUNNING"
    EVALUATED = "EVALUATED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ExperimentHypothesis:
    """A testable research hypothesis derived from a candidate.

    Represents: 'When conditions C hold, market M outcome is predicted
    in direction D with model X.'

    The hypothesis is deterministically identified by its content hash
    which excludes runtime-dependent fields.

    Attributes:
        hypothesis_id: Human-readable identifier.
        candidate_hash: Content hash of the source ResearchCandidate.
        market_type: Target market.
        conditions: Conditions from the candidate (AND logic).
        direction: Expected outcome direction.
        feature_ids: Features referenced by conditions.
        rationale: Optional human/generation rationale.
        parameters: Additional hypothesis parameters.
        status: Current lifecycle status.
        created_at: ISO timestamp (excluded from content hash).
    """

    hypothesis_id: str
    candidate_hash: str
    market_type: str
    conditions: tuple[CandidateCondition, ...]
    direction: str  # "OVER", "UNDER", "YES", "NO", "HOME", "DRAW", "AWAY"
    feature_ids: tuple[str, ...]
    rationale: str = ""
    parameters: tuple[tuple[str, Any], ...] = ()
    status: HypothesisStatus = HypothesisStatus.GENERATED
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def content_hash(self) -> str:
        """Deterministic content hash for identity.

        Canonical serialization:
        - Sorted conditions by (feature_id, operator, threshold)
        - Sorted feature_ids
        - Sorted parameters
        - Excludes hypothesis_id, status, created_at
        """
        sorted_conditions = sorted(
            [c.to_dict() for c in self.conditions],
            key=lambda c: (c["feature_id"], c["operator"], c["threshold"]),
        )
        canonical = json.dumps(
            {
                "candidate_hash": self.candidate_hash,
                "market_type": self.market_type,
                "conditions": sorted_conditions,
                "direction": self.direction,
                "feature_ids": sorted(self.feature_ids),
                "parameters": sorted(self.parameters),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def evaluate_conditions(self, features: dict[str, float]) -> Optional[bool]:
        """Evaluate all conditions against feature values.

        Returns:
            True if ALL conditions pass.
            False if any condition fails.
            None if any required feature is missing (NULL != 0).
        """
        for condition in self.conditions:
            val = features.get(condition.feature_id)
            result = condition.evaluate(val)
            if result is None:
                return None  # Missing data — cannot evaluate
            if not result:
                return False
        return True

    @classmethod
    def from_candidate(
        cls,
        candidate: ResearchCandidate,
        hypothesis_id: Optional[str] = None,
    ) -> "ExperimentHypothesis":
        """Create hypothesis from a ResearchCandidate.

        Uses the candidate's direction, conditions, and market type.
        """
        h_id = hypothesis_id or f"hyp_{candidate.content_hash}"
        return cls(
            hypothesis_id=h_id,
            candidate_hash=candidate.content_hash,
            market_type=candidate.market_type,
            conditions=candidate.conditions,
            direction=candidate.direction,
            feature_ids=candidate.feature_ids,
            rationale=f"Generated from candidate {candidate.candidate_id}",
            parameters=tuple(sorted(candidate.parameters.items())),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/provenance."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "candidate_hash": self.candidate_hash,
            "content_hash": self.content_hash,
            "market_type": self.market_type,
            "conditions": [c.to_dict() for c in self.conditions],
            "direction": self.direction,
            "feature_ids": list(self.feature_ids),
            "rationale": self.rationale,
            "parameters": dict(self.parameters),
            "status": self.status.value,
            "created_at": self.created_at,
        }
