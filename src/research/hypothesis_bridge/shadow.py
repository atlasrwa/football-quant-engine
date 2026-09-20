"""ShadowResearchRecord — the immutable, versioned output of the bridge.

Every record, VALID or REJECTED, is emitted: a rejection is a research result, and dropping
it would make the rejection-reason distribution unmeasurable. No record may carry a
predictive quantity; `firewall.assert_outbound_clean` is the last gate before one is returned.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.hypothesis_bridge import firewall, registry
from src.research.hypothesis_bridge.canonical import CanonicalHypothesis
from src.research.hypothesis_bridge.proposal import HypothesisProposal
from src.research.hypothesis_bridge.validation import ValidationResult
from src.research.hypothesis_bridge.versions import (
    SHADOW_RECORD_VERSION, CANONICAL_IR_VERSION, VALIDATOR_VERSION, COMPILER_VERSION,
    MEASUREMENT_VERSION, bridge_version_stamp)


def producer_code_commit() -> str:
    """The commit that produced this record, or an explicit unknown marker."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:                                    # pragma: no cover - environment
        pass
    return "UNKNOWN_PRODUCER_COMMIT"


def corpus_vintage(recs: list[MatchRecord]) -> str:
    """Data-vintage identity: which corpus rows this record could have seen."""
    payload = {"n": len(recs),
               "max_kickoff": max((r.kickoff_unix for r in recs), default=None),
               "fixture_digest": hashlib.sha256(
                   "|".join(sorted(r.fixture_id for r in recs)).encode()).hexdigest()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_record(*, proposal: HypothesisProposal, target: MatchRecord,
                 packet_version: str, packet_hash: str,
                 validation: ValidationResult,
                 ir: Optional[CanonicalHypothesis] = None,
                 measurement: Optional[dict[str, Any]] = None,
                 corpus_identity: str = "UNKNOWN_CORPUS",
                 producer_commit: Optional[str] = None) -> dict:
    """Assemble and firewall-check a shadow record. Raises if anything predictive is present."""
    record = {
        "record_version": SHADOW_RECORD_VERSION,
        "fixture_id": target.fixture_id,
        "target_kickoff": target.kickoff_unix,

        "proposal_id": proposal.proposal_id,
        "proposal_hash": proposal.proposal_hash(),

        "packet_version": packet_version,
        "packet_hash": packet_hash,

        "canonical_hypothesis_id": (ir.canonical_hypothesis_id if ir else None),
        "canonical_ir": (ir.to_dict() if ir else None),
        "canonical_ir_version": CANONICAL_IR_VERSION,

        "capability_hash": registry.capability_hash(),
        "corpus_identity": corpus_identity,

        "validator_version": VALIDATOR_VERSION,
        "compiler_version": COMPILER_VERSION,
        "measurement_version": MEASUREMENT_VERSION,
        "bridge_version_stamp": bridge_version_stamp(),

        "validation_status": validation.status,
        "rejection_reason": validation.rejection_reason,

        "raw_n": validation.raw_n,
        "effective_n": validation.effective_n,
        "coverage": validation.coverage,

        "measurement": measurement,

        "research_reason": proposal.research_reason,
        "evidence_refs": list(proposal.evidence_refs),

        "producer_code_commit": producer_commit or producer_code_commit(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # Last gate. A record that reached storage carrying an edge would afterwards be
    # indistinguishable from a legitimate one, so this raises rather than filtering.
    firewall.assert_outbound_clean(record)
    return record
