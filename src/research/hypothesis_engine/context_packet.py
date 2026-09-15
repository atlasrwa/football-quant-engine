"""Fixture-context packet + capability manifest (`fixture_context_packet_v1`).

The bounded factual universe handed to the LLM. Every numeric value in it originates from
Python; the LLM computes nothing and may cite nothing that is not here.

RELATIONSHIP TO THE LEGACY PACKET
---------------------------------
The legacy `fixture_evidence_packet_v1/v2` structure is reused essentially unchanged --
per-item provenance, stable evidence ids, PIT cutoffs, reliability, shrinkage level, packet
hash -- because that part of the previous generation was correct. Two things are added:

  * `capability_manifest` -- what can actually be asked about THIS fixture, so the model is
    told its query surface rather than having to guess it. This is what makes "capability
    awareness" (mandate §25 D) a fair thing to score: a model that asks for injury data was
    told, in the packet, that injury data does not exist.

  * `formation_coverage` -- candidate N, usable N, coverage rate and missingness for every
    formation-conditioned dimension, per mandate §7. Formation is a QUALITY/SAMPLE-SIZE
    issue, not a blanket exclusion, so the packet reports how much of it there is instead
    of dropping it.

FORMATION HANDLING (mandate §7, §8)
-----------------------------------
Historical recorded formation is supplied as fixture context and needs no announcement
timestamp. Future/expected formation is UNKNOWN in this repository, so the packet supplies
the subject's observed recent formation DISTRIBUTION instead of asserting one, and marks
`expected_formation` as UNSUPPORTED_CONTEXT_SOURCE. The model can still ask robust
questions across plausible formations, or formation-independent ones.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from . import capability, vocabulary

PACKET_SCHEMA_VERSION = "fixture_context_packet_v1"


@dataclass(frozen=True)
class EvidenceItem:
    """One citable fact. `id` is what a hypothesis references in `evidence_refs`."""

    id: str
    metric: str
    value: Optional[float]
    sample_n: int
    scope: dict
    reliability: str                  # LOW | MEDIUM | HIGH
    shrinkage_level: str              # DIRECT | SHRUNK
    source_provider: str
    source_field: str
    cutoff_unix: int
    temporal_status: str = "PIT_SAFE"
    max_source_time_unix: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "metric": self.metric, "value": self.value,
            "sample_n": self.sample_n, "scope": dict(self.scope),
            "reliability": self.reliability, "shrinkage_level": self.shrinkage_level,
            "source_provider": self.source_provider, "source_field": self.source_field,
            "cutoff_unix": self.cutoff_unix, "temporal_status": self.temporal_status,
            "max_source_time_unix": self.max_source_time_unix,
        }


def reliability_for(n: int) -> str:
    if n >= 20:
        return "HIGH"
    if n >= 8:
        return "MEDIUM"
    return "LOW"


def evidence_id(subject: str, family: str, metric: str, scope: dict) -> str:
    """Stable, deterministic, identity-neutral evidence id.

    Contains no club or competition name, so the same packet transformed for the alias
    control keeps byte-identical ids -- which is what lets the identity control compare
    intent rather than incidentally-renamed references.
    """
    h = hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:6]
    return f"{subject}_{family}_{metric}_{h}"


def formation_coverage(
    recorded: Sequence[Optional[str]],
) -> dict:
    """Coverage report for a formation-conditioned dimension (mandate §7).

    `recorded` is the per-candidate-fixture recorded formation, with None for fixtures
    where no lineup payload exists.
    """
    candidate_n = len(recorded)
    usable_n = sum(1 for f in recorded if f)
    return {
        "candidate_n": candidate_n,
        "usable_n": usable_n,
        "missing_n": candidate_n - usable_n,
        "coverage_rate": round(usable_n / candidate_n, 4) if candidate_n else 0.0,
    }


def formation_family(formation: Optional[str]) -> str:
    """Structural family from a recorded formation string, e.g. '3-4-2-1' -> BACK_THREE.

    Reads only the back-line count, which is the structurally reliable part of the string.
    Deliberately does NOT infer style, intent or quality from the label -- the legacy
    generation's formation-stereotype failure came from treating a label as a behavior.
    """
    if not formation:
        return "OTHER"
    head = formation.split("-")[0].strip()
    if not head.isdigit():
        return "OTHER"
    return {3: "BACK_THREE", 4: "BACK_FOUR", 5: "BACK_FIVE"}.get(int(head), "OTHER")


def build_capability_manifest(
    *,
    fixture_id: str,
    available_metrics: Iterable[str],
    formation_coverage_report: Optional[dict] = None,
    half_level_available: bool = True,
    referee_available: bool = False,
    min_formation_coverage: float = 0.15,
) -> capability.FixtureCapabilityManifest:
    """What can actually be asked about this fixture.

    A dimension is offered only when its context source is supported AND this fixture has
    enough of it. Formation dimensions are gated on a coverage floor rather than excluded:
    a fixture with 2% formation coverage cannot support a formation-conditioned cohort, but
    one with 40% can, and the manifest says which this is.
    """
    metrics = tuple(sorted(m for m in available_metrics
                           if capability.is_supported_metric(m)))

    dims: list[str] = ["venue", "competition", "opponent_profile"]

    if half_level_available:
        dims.extend(["period", "half_score_state"])

    cov = formation_coverage_report or {}
    if cov.get("coverage_rate", 0.0) >= min_formation_coverage:
        dims.extend(["own_formation_family", "opponent_formation_family"])

    if referee_available:
        dims.append("referee")

    coverage: dict[str, dict] = {}
    if formation_coverage_report:
        coverage["own_formation_family"] = dict(formation_coverage_report)
        coverage["opponent_formation_family"] = dict(formation_coverage_report)

    notes: list[str] = []
    if cov and cov.get("coverage_rate", 0.0) < min_formation_coverage:
        notes.append(
            f"formation-conditioned dimensions withheld: coverage "
            f"{cov.get('coverage_rate')} < floor {min_formation_coverage}. This is a "
            f"sample-size limitation for this fixture, not a rule against formation "
            f"analysis.")
    if not half_level_available:
        notes.append("half-level metrics unavailable for this fixture's history; period "
                     "and half_score_state dimensions withheld.")

    return capability.FixtureCapabilityManifest(
        fixture_id=fixture_id,
        available_metrics=metrics,
        available_dimensions=tuple(sorted(set(dims))),
        unsupported_context=capability.default_unsupported_context(),
        coverage=coverage,
        notes=tuple(notes),
    )


@dataclass
class FixtureContextPacket:
    fixture_id: str
    information_cutoff_unix: int
    home_label: str
    away_label: str
    competition_label: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    manifest: Optional[capability.FixtureCapabilityManifest] = None
    #: observed recent formation distribution per subject; expected formation is UNKNOWN
    formation_distribution: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self, include_hash: bool = True) -> dict:
        body = {
            "packet_schema_version": PACKET_SCHEMA_VERSION,
            "fixture_id": self.fixture_id,
            "information_cutoff_unix": self.information_cutoff_unix,
            "fixture": {
                "home": self.home_label,
                "away": self.away_label,
                "competition": self.competition_label,
            },
            "vocabulary": vocabulary.snapshot(),
            "capability_manifest": self.manifest.to_dict() if self.manifest else None,
            "formation_distribution": dict(self.formation_distribution),
            "evidence": [e.to_dict() for e in self.evidence],
            "data_quality": {
                "n_evidence": len(self.evidence),
                "n_pit_safe": sum(1 for e in self.evidence
                                  if e.temporal_status == "PIT_SAFE"),
                "n_unavailable": sum(1 for e in self.evidence if e.value is None),
            },
            "notes": list(self.notes),
        }
        if include_hash:
            body["packet_hash"] = packet_hash(body)
        return body

    def evidence_ids(self) -> set[str]:
        return {e.id for e in self.evidence}


def packet_hash(body: dict) -> str:
    """sha256 over the packet MINUS the hash field itself."""
    clean = {k: v for k, v in body.items() if k != "packet_hash"}
    return hashlib.sha256(
        json.dumps(clean, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
