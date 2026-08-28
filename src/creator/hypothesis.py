"""Creator hypothesis definition and management.

A hypothesis is: "Under conditions X over features Y, market Z tends toward
direction D." Creators define hypotheses over confirmed features; the system
runs them through the identical governance pipeline used for internal models.

Key properties:
- Content-hash identity (same hypothesis = same hash, regardless of who submitted it)
- Immutable after creation (editing creates a new version)
- Tied to a creator identity
- Tracked for FDR correction (submission count per creator)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class PredictionTarget(str, Enum):
    """What the hypothesis predicts."""
    CORNERS_OVER_UNDER = "corners_over_under"
    CARDS_OVER_UNDER = "cards_over_under"
    GOALS_OVER_UNDER = "goals_over_under"
    BTTS = "btts"
    CLEAN_SHEET = "clean_sheet"


class ConditionOperator(str, Enum):
    """Comparison operators for conditions."""
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="


class HypothesisStatus(str, Enum):
    """Lifecycle state of a hypothesis."""
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"           # Queued for validation
    VALIDATING = "VALIDATING"         # Currently running through pipeline
    VALIDATED_PASS = "VALIDATED_PASS"  # Passed all gates
    VALIDATED_FAIL = "VALIDATED_FAIL"  # Failed one or more gates
    QUARANTINED = "QUARANTINED"       # In 90-day live test
    PROMOTED = "PROMOTED"             # Cleared quarantine
    REJECTED = "REJECTED"             # Failed quarantine


@dataclass(frozen=True)
class HypothesisCondition:
    """A single condition in a hypothesis.

    e.g., "home_corners_avg_5 > 6.0" means
    'home team averaged more than 6 corners over last 5 matches'.
    """
    feature_id: str
    operator: ConditionOperator
    threshold: float

    def to_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "operator": self.operator.value,
            "threshold": self.threshold,
        }


@dataclass
class CreatorHypothesis:
    """A creator-defined testable hypothesis.

    Immutable content: changing conditions/target/direction creates a new version.
    """
    hypothesis_id: str
    creator_id: str
    name: str
    description: str
    target: PredictionTarget
    direction: str  # "OVER" or "UNDER" (or "YES"/"NO" for BTTS)
    conditions: list[HypothesisCondition]
    logic: str  # "AND" or "OR"
    line: Optional[float]  # e.g., 9.5 for corners over/under
    content_hash: str
    version: int
    status: HypothesisStatus
    created_at: str
    parent_version: Optional[int] = None
    forked_from: Optional[str] = None  # hypothesis_id of source

    @staticmethod
    def compute_content_hash(
        target: str,
        direction: str,
        conditions: list[dict],
        logic: str,
        line: Optional[float],
    ) -> str:
        """Deterministic content hash from hypothesis definition.

        Same hypothesis = same hash regardless of name, creator, or timestamp.
        """
        canonical = json.dumps({
            "target": target,
            "direction": direction,
            "conditions": sorted(conditions, key=lambda c: c["feature_id"]),
            "logic": logic,
            "line": line,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "creator_id": self.creator_id,
            "name": self.name,
            "description": self.description,
            "target": self.target.value,
            "direction": self.direction,
            "conditions": [c.to_dict() for c in self.conditions],
            "logic": self.logic,
            "line": self.line,
            "content_hash": self.content_hash,
            "version": self.version,
            "status": self.status.value,
            "created_at": self.created_at,
            "parent_version": self.parent_version,
            "forked_from": self.forked_from,
        }


class HypothesisBuilder:
    """Validates and constructs CreatorHypothesis from form inputs.

    Wraps the existing StrategyBuilder pattern with creator-specific
    validation (feature existence, pre-kickoff usability, etc.).
    """

    VALID_DIRECTIONS = {"OVER", "UNDER", "YES", "NO"}
    VALID_LOGIC = {"AND", "OR"}
    DEFAULT_LINES = {
        PredictionTarget.CORNERS_OVER_UNDER: 9.5,
        PredictionTarget.CARDS_OVER_UNDER: 3.5,
        PredictionTarget.GOALS_OVER_UNDER: 2.5,
        PredictionTarget.BTTS: None,
        PredictionTarget.CLEAN_SHEET: None,
    }

    def __init__(self, feature_catalog: dict[str, Any]) -> None:
        """Initialize with the feature catalog (keyed by feature_id)."""
        self._catalog = feature_catalog

    def build(
        self,
        creator_id: str,
        name: str,
        description: str,
        target: str,
        direction: str,
        conditions: list[dict],
        logic: str = "AND",
        line: Optional[float] = None,
        forked_from: Optional[str] = None,
    ) -> CreatorHypothesis:
        """Validate inputs and construct a hypothesis.

        Raises ValueError with clear messages on validation failure.
        """
        # Name
        if not name or not name.strip():
            raise ValueError("Hypothesis name cannot be empty")
        if len(name) > 200:
            raise ValueError("Hypothesis name must be ≤200 characters")

        # Target
        try:
            target_enum = PredictionTarget(target)
        except ValueError:
            valid = [t.value for t in PredictionTarget]
            raise ValueError(f"Invalid target '{target}'. Must be one of: {valid}")

        # Direction
        direction = direction.upper()
        if direction not in self.VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction '{direction}'. Must be one of: {sorted(self.VALID_DIRECTIONS)}")

        # Logic
        logic = logic.upper()
        if logic not in self.VALID_LOGIC:
            raise ValueError(f"Invalid logic '{logic}'. Must be AND or OR")

        # Line (default if not specified)
        if line is None:
            line = self.DEFAULT_LINES.get(target_enum)

        # Conditions
        if not conditions:
            raise ValueError("At least one condition is required")
        if len(conditions) > 5:
            raise ValueError("Maximum 5 conditions per hypothesis (prevents overfitting)")

        validated_conditions = []
        for i, cond in enumerate(conditions):
            feature_id = cond.get("feature_id", "")
            if feature_id not in self._catalog:
                raise ValueError(
                    f"Condition {i+1}: feature '{feature_id}' not found in the feature catalog. "
                    f"Use GET /api/v1/creator/features for available features."
                )
            try:
                op = ConditionOperator(cond.get("operator", ""))
            except ValueError:
                valid_ops = [o.value for o in ConditionOperator]
                raise ValueError(
                    f"Condition {i+1}: invalid operator '{cond.get('operator')}'. "
                    f"Must be one of: {valid_ops}"
                )
            threshold = cond.get("threshold")
            if threshold is None or not isinstance(threshold, (int, float)):
                raise ValueError(f"Condition {i+1}: threshold must be a number")

            validated_conditions.append(HypothesisCondition(
                feature_id=feature_id,
                operator=op,
                threshold=float(threshold),
            ))

        # Content hash
        content_hash = CreatorHypothesis.compute_content_hash(
            target=target_enum.value,
            direction=direction,
            conditions=[c.to_dict() for c in validated_conditions],
            logic=logic,
            line=line,
        )

        # Build
        now = datetime.now(timezone.utc).isoformat()
        hypothesis_id = hashlib.sha256(
            f"{creator_id}:{content_hash}:{now}".encode()
        ).hexdigest()[:16]

        return CreatorHypothesis(
            hypothesis_id=hypothesis_id,
            creator_id=creator_id,
            name=name.strip(),
            description=description.strip() if description else "",
            target=target_enum,
            direction=direction,
            conditions=validated_conditions,
            logic=logic,
            line=line,
            content_hash=content_hash,
            version=1,
            status=HypothesisStatus.DRAFT,
            created_at=now,
            forked_from=forked_from,
        )
