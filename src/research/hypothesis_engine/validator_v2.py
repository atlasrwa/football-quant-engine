"""Deterministic hypothesis validator v2 (`hypothesis_validator_v2`).

Same gates, same no-salvage discipline, same order as `validator.validate`. Three wiring
changes, and nothing else:

  0. CANONICALIZE FIRST. `condition_contract.canonicalize_payload` runs at the external
     boundary, BEFORE schema validation and BEFORE compilation, so every layer downstream
     sees exactly one representation of an intent. A condition the contract cannot resolve
     is left verbatim and reported -- never repaired, never dropped.
  1. SCHEMA v2. The closed per-dimension condition enum, so a wrong-cased or illegal value
     is a SCHEMA rejection with an exact path instead of a silent death at compile.
  2. FIREWALL v2. Classified. Class A and class B both block exactly as v1 blocked; class
     C (approved-metric lexical collision, carrying no number) is instrumentation error and
     does not.

`validator.py` is NOT edited beyond the additive schema-combinator support, and
`validator.validate` still points at schema v1 -- the frozen V2 pipeline must stay exactly
reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import (availability, capability, condition_contract, firewall_v2, lifecycle,
               schema_v2, validator)

VALIDATOR_VERSION = "hypothesis_validator_v2"


@dataclass
class ValidationResultV2:
    accepted: bool
    failure: Optional[str] = None
    reasons: list[str] = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    accepted_hypotheses: list[dict] = field(default_factory=list)
    #: the payload after boundary canonicalization -- what every later layer must use
    canonical_payload: Optional[dict] = None
    canonicalization: Optional[dict] = None
    #: every firewall finding, INCLUDING suppressed class-C ones, for auditability
    firewall_findings: list = field(default_factory=list)

    @property
    def n_accepted(self) -> int:
        return len(self.accepted_hypotheses)

    def to_dict(self) -> dict:
        return {
            "validator_version": VALIDATOR_VERSION,
            "accepted": self.accepted,
            "failure": self.failure,
            "reasons": list(self.reasons),
            "n_accepted": self.n_accepted,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "canonicalization": self.canonicalization,
            "firewall": [v.to_dict() for v in self.firewall_findings],
        }


def validate(
    payload,
    *,
    packet: Optional[dict] = None,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
    expected_packet_hash: Optional[str] = None,
    expected_fixture_id: Optional[str] = None,
    ontology: Optional["availability.ResearchOntology"] = None,
) -> ValidationResultV2:
    if not isinstance(payload, dict):
        return ValidationResultV2(False, lifecycle.SCHEMA_INVALID,
                                  [f"response is {type(payload).__name__}, not an object"])

    # ---- gate 0: boundary canonicalization -------------------------------------------
    canon, creport = condition_contract.canonicalize_payload(payload)

    # ---- gate 1: schema v2 (also the firewall's structural layer) ---------------------
    errs = validator.validate_schema_against(schema_v2.build_schema(), canon)
    if errs:
        return ValidationResultV2(False, lifecycle.SCHEMA_INVALID, errs,
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict())

    # ---- gate 2: identity binding -----------------------------------------------------
    reasons: list[str] = []
    if expected_fixture_id and canon.get("fixture_id") != expected_fixture_id:
        reasons.append(f"fixture_id {canon.get('fixture_id')!r} != expected "
                       f"{expected_fixture_id!r}")
    if expected_packet_hash and canon.get("packet_hash") != expected_packet_hash:
        reasons.append(f"packet_hash {canon.get('packet_hash')!r} != the hash of the "
                       f"packet actually sent ({expected_packet_hash!r})")
    if reasons:
        return ValidationResultV2(False, lifecycle.SCHEMA_INVALID, reasons,
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict())

    # ---- gate 3: classified numerical-authority firewall (whole response) -------------
    findings = firewall_v2.scan(canon, packet=packet)
    blocking = firewall_v2.blocking(findings)
    grading = [v for v in blocking if v.layer == "GRADE"]
    numeric = [v for v in blocking if v.layer != "GRADE"]
    if numeric:
        return ValidationResultV2(False, lifecycle.NUMERICAL_AUTHORITY_VIOLATION,
                                  [str(v) for v in numeric],
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  firewall_findings=findings)
    if grading:
        return ValidationResultV2(False, lifecycle.LATENT_GRADING_VIOLATION,
                                  [str(v) for v in grading],
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  firewall_findings=findings)

    # ---- gate 4: per-hypothesis grounding / capability (UNCHANGED from v1) ------------
    valid_ids = set()
    if packet:
        valid_ids = {it.get("id") for it in (packet.get("evidence") or []) if it.get("id")}

    # The ontology is what makes axis availability checkable per fixture.
    ont = ontology
    if ont is None and packet:
        ont = availability.build_ontology(packet, manifest)

    verdicts = []
    accepted: list[dict] = []
    for h in canon.get("hypotheses", []) or []:
        hid = h.get("hypothesis_id", "<anon>")
        v = validator._validate_one(h, hid, valid_ids, manifest, bool(packet))
        # SECOND AXIS GATE. `fixture_condition_space` keeps an unresolvable axis out of the
        # model's sight; this keeps it out of the research record if the model writes one
        # anyway. `query_plan` cannot do this itself -- it only checks membership in
        # `vocabulary.PROFILE_AXES`, which is precisely the set that contains the two
        # entries with no backing inventory metric.
        if v.accepted and ont is not None:
            axis_problems = availability.unavailable_axis_reasons(h, ont)
            if axis_problems:
                v.accepted = False
                v.failure = lifecycle.UNSUPPORTED_CONTEXT_SOURCE
                v.reasons = list(v.reasons) + axis_problems
        verdicts.append(v)
        if v.accepted:
            accepted.append(h)

    return ValidationResultV2(True, None, [], verdicts, accepted,
                              canonical_payload=canon,
                              canonicalization=creport.to_dict(),
                              firewall_findings=findings)


def version_stamp() -> dict:
    return {
        "validator_version": VALIDATOR_VERSION,
        **schema_v2.version_stamp(),
        **firewall_v2.version_stamp(),
    }
