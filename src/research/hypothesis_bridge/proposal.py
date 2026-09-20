"""HypothesisProposal — research intent only, never a prediction.

This is what an LLM is permitted to hand the engine: a statement of WHAT to measure. It
carries no number that is or becomes a forecast; `firewall.check_inbound` enforces that with
an allow-list before anything else looks at the payload.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from src.research.hypothesis_bridge import firewall
from src.research.hypothesis_bridge.versions import PROPOSAL_SCHEMA_VERSION

#: What a proposal may ask about. Free prose is confined to `research_reason`, which never
#: reaches measurement code -- it is carried for audit only.
SUBJECTS = frozenset({"home_team", "away_team"})
PERSPECTIVES = frozenset({"for", "against"})
COMPARATORS = frozenset({"team_season_baseline", "league_season_baseline"})
WINDOW_MODES = frozenset({"all", "last_n"})
VENUES = frozenset({"home", "away", "any"})
PERIODS = frozenset({"all", "first_half", "second_half"})


class ProposalError(ValueError):
    """A proposal could not be accepted as research intent."""


@dataclass(frozen=True)
class HypothesisProposal:
    fixture_id: str
    subject: str                       # SUBJECTS
    target_metric: str                 # registry metric name
    perspective: str                   # PERSPECTIVES
    comparator: str                    # COMPARATORS
    conditions: dict[str, Any] = field(default_factory=dict)   # venue / period
    window: dict[str, Any] = field(default_factory=lambda: {"mode": "all"})
    similar_opponent_intent: Optional[dict[str, Any]] = None
    research_reason: str = ""
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_refs"] = list(self.evidence_refs)
        return d

    def proposal_hash(self) -> str:
        payload = {"schema": PROPOSAL_SCHEMA_VERSION, "proposal": self.to_dict()}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    @property
    def proposal_id(self) -> str:
        return f"prop_{self.proposal_hash()[:16]}"


def parse_proposal(raw: dict) -> HypothesisProposal:
    """Validate an untrusted mapping into a proposal, or raise.

    The firewall runs FIRST, before any field is read, so a payload carrying a probability is
    refused without its other fields ever being interpreted.
    """
    if not isinstance(raw, dict):
        raise ProposalError("proposal must be a mapping")
    problems = firewall.check_inbound(raw)
    if problems:
        raise ProposalError("; ".join(problems))
    missing = [k for k in ("fixture_id", "subject", "target_metric", "perspective", "comparator")
               if k not in raw]
    if missing:
        raise ProposalError(f"missing_required:{','.join(missing)}")
    return HypothesisProposal(
        fixture_id=str(raw["fixture_id"]),
        subject=str(raw["subject"]),
        target_metric=str(raw["target_metric"]),
        perspective=str(raw["perspective"]),
        comparator=str(raw["comparator"]),
        conditions=dict(raw.get("conditions") or {}),
        window=dict(raw.get("window") or {"mode": "all"}),
        similar_opponent_intent=(dict(raw["similar_opponent_intent"])
                                 if raw.get("similar_opponent_intent") else None),
        research_reason=str(raw.get("research_reason", "")),
        evidence_refs=tuple(raw.get("evidence_refs") or ()),
    )
