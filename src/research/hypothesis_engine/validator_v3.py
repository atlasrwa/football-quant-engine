"""Hypothesis validator with arm-neutral evidence resolution (`validator_v3`).

Every gate is `validator_v2`'s, reused unchanged. ONE thing differs, and it is the whole
reason this module exists:

    v2:  valid_ids = {it["id"] for it in packet["evidence"]}      # V3-shaped key
    v3:  valid_ids = v5a1_evidence.resolve_evidence_ids(packet)   # the common interface

In the aborted V5A that single line made the treatment arm's grounded-acceptance rate
exactly zero before a token was generated, because its packets had no `evidence` key. Here
both arms resolve through the same function, so a citation that is real is accepted in
either arm and a citation that is not is rejected in either arm.

`validator_v2.py` and `firewall_v2.py` are NOT modified: they are hashed into the frozen V3
and V5A preregistrations and remain byte-identical.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.research.hypothesis_engine import (availability, capability, condition_contract,
                                            firewall_v3, lifecycle, schema_v2, validator,
                                            validator_v2, vocabulary)

VALIDATOR_VERSION = "validator_v3"


@dataclass
class ValidationResultV3:
    accepted: bool
    failure: Optional[str] = None
    reasons: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    accepted_hypotheses: list = field(default_factory=list)
    canonical_payload: Optional[dict] = None
    canonicalization: Optional[dict] = None
    firewall_findings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "validator_version": VALIDATOR_VERSION,
            "accepted": self.accepted,
            "failure": self.failure,
            "reasons": list(self.reasons),
            "verdicts": [v.to_dict() for v in self.verdicts],
            "canonicalization": self.canonicalization,
            "firewall": [v.to_dict() for v in self.firewall_findings],
        }


def resolve_valid_ids(packet: Optional[dict]) -> set:
    from src.research.hypothesis_oos import v5a1_evidence as E
    return E.resolve_evidence_ids(packet)


def build_ontology_for(packet: Optional[dict],
                       manifest: Optional[capability.FixtureCapabilityManifest] = None):
    """Gated ontology for a V5A.1 packet, via the frozen `availability` module.

    `availability.build_ontology` reads a V3-shaped packet. Rather than fork it, this
    projects the V5A.1 packet into the three facts it actually consults -- offered
    dimensions, evidence scopes and observed formation families -- and hands it that view.
    The availability logic itself is untouched.
    """
    if not packet:
        return None
    from src.research.hypothesis_oos import v5a1_ontology as O
    return O.build_ontology_view(packet, manifest)


def validate(
    payload,
    *,
    packet: Optional[dict] = None,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
    expected_packet_hash: Optional[str] = None,
    expected_fixture_id: Optional[str] = None,
    ontology=None,
) -> ValidationResultV3:
    if not isinstance(payload, dict):
        return ValidationResultV3(False, lifecycle.SCHEMA_INVALID,
                                  [f"response is {type(payload).__name__}, not an object"])

    # ---- gate 0: boundary canonicalization (v2, unchanged) ----------------------------
    canon, creport = condition_contract.canonicalize_payload(payload)

    # ---- gate 1: schema v2 (v2, unchanged) -------------------------------------------
    errs = validator.validate_schema_against(schema_v2.build_schema(), canon)
    if errs:
        return ValidationResultV3(False, lifecycle.SCHEMA_INVALID, errs,
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict())

    # ---- gate 2: identity binding (v2, unchanged) ------------------------------------
    reasons: list = []
    if expected_fixture_id and canon.get("fixture_id") != expected_fixture_id:
        reasons.append(f"fixture_id {canon.get('fixture_id')!r} != expected "
                       f"{expected_fixture_id!r}")
    if expected_packet_hash and canon.get("packet_hash") != expected_packet_hash:
        reasons.append(f"packet_hash {canon.get('packet_hash')!r} != the hash of the "
                       f"packet actually sent ({expected_packet_hash!r})")
    if reasons:
        return ValidationResultV3(False, lifecycle.SCHEMA_INVALID, reasons,
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict())

    # ---- gate 3: firewall, arm-neutral provenance ------------------------------------
    findings = firewall_v3.scan(canon, packet=packet)
    blk = firewall_v3.blocking(findings)
    grading = [v for v in blk if v.layer == "GRADE"]
    numeric = [v for v in blk if v.layer != "GRADE"]
    if numeric:
        return ValidationResultV3(False, lifecycle.NUMERICAL_AUTHORITY_VIOLATION,
                                  [str(v) for v in numeric], canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  firewall_findings=findings)
    if grading:
        return ValidationResultV3(False, lifecycle.LATENT_GRADING_VIOLATION,
                                  [str(v) for v in grading], canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  firewall_findings=findings)

    # ---- gate 4: grounding / capability. THE FIX: one resolver, both arms ------------
    valid_ids = resolve_valid_ids(packet)

    ont = ontology
    if ont is None and packet:
        ont = build_ontology_for(packet, manifest)

    verdicts, accepted = [], []
    for h in canon.get("hypotheses", []) or []:
        hid = h.get("hypothesis_id", "<anon>")
        v = validator._validate_one(h, hid, valid_ids, manifest, bool(packet))
        if v.accepted and ont is not None:
            axis_problems = availability.unavailable_axis_reasons(h, ont)
            if axis_problems:
                v.accepted = False
                v.failure = lifecycle.UNSUPPORTED_CONTEXT_SOURCE
                v.reasons = list(v.reasons) + axis_problems
        # THIRD GATE, new in v3: schema_v2's enums are frozen and wider than any one
        # packet. This narrows them to what THIS packet actually exposes, so a question
        # about an excluded metric or an unexposed window cannot be accepted.
        if v.accepted and packet:
            from src.research.hypothesis_oos import v5a1_admissibility as ADM
            adm = ADM.packet_admissibility_reasons(h, packet)
            if adm:
                v.accepted = False
                v.failure = lifecycle.UNSUPPORTED_CONTEXT_SOURCE
                v.reasons = list(v.reasons) + adm
        verdicts.append(v)
        if v.accepted:
            accepted.append(h)

    return ValidationResultV3(True, None, [], verdicts, accepted,
                              canonical_payload=canon,
                              canonicalization=creport.to_dict(),
                              firewall_findings=findings)


def version_stamp() -> dict:
    return {"validator_version": VALIDATOR_VERSION,
            "delegates_gates_to": validator_v2.VALIDATOR_VERSION,
            **schema_v2.version_stamp(),
            **firewall_v3.version_stamp()}
