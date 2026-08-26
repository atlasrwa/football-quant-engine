"""Research Proposal — structured AI/deterministic output.

A proposal must be validated before entering the queue.
AI output is never directly executable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProposalSource(Enum):
    """Who generated the proposal."""
    DETERMINISTIC = "DETERMINISTIC"
    AI = "AI"
    HUMAN = "HUMAN"


class ProposalStatus(Enum):
    """Lifecycle of a proposal."""
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    EXECUTED = "EXECUTED"


class ResearchPhase(Enum):
    """Research phase classification."""
    EXPLORATION = "EXPLORATION"
    VALIDATION = "VALIDATION"
    CONFIRMATION = "CONFIRMATION"


@dataclass(frozen=True)
class ResearchProposal:
    """Structured research proposal.

    This is what the AI emits. It must pass deterministic
    validation before entering the research queue.

    AI proposals default to EXPLORATION phase.
    Only the deterministic pipeline can advance to VALIDATION/CONFIRMATION.
    """

    proposal_id: str = ""
    source: ProposalSource = ProposalSource.DETERMINISTIC
    status: ProposalStatus = ProposalStatus.DRAFT
    phase: ResearchPhase = ResearchPhase.EXPLORATION

    # What to test
    market_type: str = ""
    feature_ids: tuple[str, ...] = ()
    conditions: tuple[dict[str, Any], ...] = ()
    direction: str = ""  # OVER, UNDER, HOME, DRAW, AWAY, YES, NO
    operator_type: str = ""

    # How to test
    model_type: str = ""
    model_parameters: dict[str, Any] = field(default_factory=dict)
    odds_mode: str = "SYNTHETIC_ODDS"

    # Context
    rationale: str = ""
    confidence: float = 0.0  # 0-1 AI confidence
    constraints: dict[str, Any] = field(default_factory=dict)

    # Provenance
    prompt_version: str = ""
    context_hash: str = ""
    schema_version: str = "1.0"

    @property
    def content_hash(self) -> str:
        """Deterministic identity based on research content."""
        canonical = json.dumps({
            "market_type": self.market_type,
            "feature_ids": sorted(self.feature_ids),
            "conditions": list(self.conditions),
            "direction": self.direction,
            "operator_type": self.operator_type,
            "model_type": self.model_type,
            "model_parameters": self.model_parameters,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id or self.content_hash,
            "source": self.source.value,
            "status": self.status.value,
            "phase": self.phase.value,
            "market_type": self.market_type,
            "feature_ids": list(self.feature_ids),
            "conditions": list(self.conditions),
            "direction": self.direction,
            "operator_type": self.operator_type,
            "model_type": self.model_type,
            "model_parameters": self.model_parameters,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "prompt_version": self.prompt_version,
            "context_hash": self.context_hash,
            "schema_version": self.schema_version,
            "content_hash": self.content_hash,
        }
