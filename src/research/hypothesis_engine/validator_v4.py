"""Hypothesis validator for V5A.2 (`validator_v4`) -- one language, translated once.

Pipeline, in the order the gates bind:

    0  canonicalize   v5a2_contract     mechanical spelling folds, ONTOLOGY language
    1  schema         schema_v3         enums projected from the ontology
    2  identity       fixture + packet hash binding                    (unchanged)
    3  firewall       firewall_v3       numerical-authority + grading   (unchanged)
    4  contract       abstention + grounding, in MODEL language
    5  admissibility  v5a2_admissibility, in MODEL language
    6  TRANSLATE      v5a2_translate    -> frozen internal namespaces
    7  engine gates   capability / metric / axis availability, in ENGINE language

Gates 4 and 5 run BEFORE translation on purpose: every reason they produce quotes the
terms the model actually wrote, so a rejection is legible to the thing that was rejected.
Gate 7 runs after, because `capability` and `availability` are frozen and only speak the
internal language.

TWO SUBSTANTIVE CHANGES FROM `validator_v3`
-------------------------------------------
D1 -- the namespace fix. `validator_v3` inherited `schema_v2`, whose `dimension` enum came
from `vocabulary` and whose `required_capabilities` enum came from `capability`. A model
that conditioned on `opponent_profile` and declared it needed `opponent_profile` failed
schema validation, because the capability field's token for that concept was `competition`
and nothing in the packet or prompt said so. Two of V5A.1's first six calls died there and
24 hypotheses were discarded unread. Both enums now come from one ontology.

D2 -- the abstention contract. `validator._validate_one` rejects an INSUFFICIENT_EVIDENCE
hypothesis that cites any evidence at all, and no prompt, schema or packet ever said so; 6
of V5A.1's rejections were exactly that. Task S5's preferred contract is adopted here: an
abstention MAY cite the evidence that shows why the question cannot be supported. That is
strictly more permissive than the frozen rule, so `validator.py` and `validator_v2.py` are
NOT edited and stay byte-identical for V2/V3/V5A reproducibility. Fabricated references are
still rejected in an abstention -- citing something the packet does not contain is
fabrication whatever the sufficiency says.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import (availability, capability, firewall_v4, lifecycle, schema_v3, validator,
               validator_v2, vocabulary)

VALIDATOR_VERSION = "validator_v4"

#: Task S15: a response that fails the contract is not the same event as an apparatus that
#: cannot express the response. The first is a scientific observation about the model; the
#: second is our bug and must be zero after this closure.
E_EXPOSED = "EXPOSED"
E_EXPOSED_LOW_COVERAGE = "EXPOSED_LOW_COVERAGE"

MODEL_SCHEMA_INVALID = "MODEL_SCHEMA_INVALID"
INFRASTRUCTURE_CONTRACT_FAILURE = "INFRASTRUCTURE_CONTRACT_FAILURE"


@dataclass
class ValidationResultV4:
    accepted: bool
    failure: Optional[str] = None
    reasons: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    accepted_hypotheses: list = field(default_factory=list)
    canonical_payload: Optional[dict] = None
    canonicalization: Optional[dict] = None
    firewall_findings: list = field(default_factory=list)
    translation: Optional[dict] = None
    #: Per-hypothesis APPARATUS defects (an ontology term the schema admitted but the
    #: translation layer cannot map). Distinct from model errors and counted separately,
    #: because `classify_stop` halts the run on the first one.
    apparatus_defects: list = field(default_factory=list)
    #: MODEL_SCHEMA_INVALID vs INFRASTRUCTURE_CONTRACT_FAILURE, set only when the whole
    #: response failed. None when the response was processed.
    failure_class: Optional[str] = None

    def to_dict(self) -> dict:
        return {"validator_version": VALIDATOR_VERSION,
                "accepted": self.accepted,
                "failure": self.failure,
                "failure_class": self.failure_class,
                "reasons": list(self.reasons),
                "verdicts": [v.to_dict() for v in self.verdicts],
                "canonicalization": self.canonicalization,
                "translation": self.translation,
                "apparatus_defects": list(self.apparatus_defects),
                "n_apparatus_defects": len(self.apparatus_defects),
                "firewall": [v.to_dict() for v in self.firewall_findings]}


def resolve_valid_ids(packet: Optional[dict]) -> set:
    from src.research.hypothesis_oos import v5a1_evidence as E
    return E.resolve_evidence_ids(packet)


def build_ontology_for(packet, manifest=None):
    """Gated ontology for a V5A.2 packet.

    `v5a2_view` reads the availability map in ONTOLOGY TERMS. Pointing this at
    `v5a1_ontology` instead would silently offer nothing, because that module looks up
    `venue_splits` / `opponent_profile_response`, which V5A.2 packets no longer contain --
    a fail-open-looking failure that actually rejects every profile question. The
    generated surface battery covers exactly this.
    """
    if not packet:
        return None
    from src.research.hypothesis_oos import v5a2_view as VIEW
    return VIEW.build_ontology_view(packet, manifest)


def _classify_schema_failure(errs: list, packet=None) -> str:
    """Model contract failure, or our apparatus failing to express a legal response?

    The D1 class is precisely: the packet ADVERTISED a term and the schema then rejected
    it. That is the apparatus contradicting itself, and it must never happen again.

    The test is deliberately narrower than "the error mentions an ontology term". Some
    declared terms are not legal everywhere -- `market_prices` is declared in the
    availability map so the packet can state the absence is deliberate, but it is not a
    legal `required_capabilities` value. A model writing it has broken a contract it was
    shown, which is a MODEL error; counting it as an apparatus defect would halt a paid run
    on the model's mistake. So a term only implicates the apparatus when the packet
    actually declares it EXPOSED.
    """
    from src.research.hypothesis_oos import v5a2_admissibility as ADM
    from src.research.hypothesis_oos import v5a2_ontology as O
    if packet is None:
        return MODEL_SCHEMA_INVALID
    states = ADM.exposure_states(packet)
    advertised = {t for t in O.all_terms()
                  if states.get(t) in (E_EXPOSED, E_EXPOSED_LOW_COVERAGE)}
    for e in errs:
        text = str(e)
        for t in advertised:
            if f"'{t}'" in text or f'"{t}"' in text:
                return INFRASTRUCTURE_CONTRACT_FAILURE
    return MODEL_SCHEMA_INVALID


def validate(
    payload,
    *,
    packet: Optional[dict] = None,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
    expected_packet_hash: Optional[str] = None,
    expected_fixture_id: Optional[str] = None,
    ontology=None,
) -> ValidationResultV4:
    from src.research.hypothesis_oos import v5a2_admissibility as ADM
    from src.research.hypothesis_oos import v5a2_contract as C
    from src.research.hypothesis_oos import v5a2_translate as TR

    if not isinstance(payload, dict):
        return ValidationResultV4(False, lifecycle.SCHEMA_INVALID,
                                  [f"response is {type(payload).__name__}, not an object"],
                                  failure_class=MODEL_SCHEMA_INVALID)

    # ---- gate 0: boundary canonicalization, ontology language ------------------------
    canon, creport = C.canonicalize_payload(payload)

    # ---- gate 1: schema v3 -----------------------------------------------------------
    errs = validator.validate_schema_against(schema_v3.build_schema(), canon)
    if errs:
        return ValidationResultV4(False, lifecycle.SCHEMA_INVALID, errs,
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  failure_class=_classify_schema_failure(errs, packet))

    # ---- gate 2: identity binding ----------------------------------------------------
    reasons: list = []
    if expected_fixture_id and canon.get("fixture_id") != expected_fixture_id:
        reasons.append(f"fixture_id {canon.get('fixture_id')!r} != expected "
                       f"{expected_fixture_id!r}")
    if expected_packet_hash and canon.get("packet_hash") != expected_packet_hash:
        reasons.append(f"packet_hash {canon.get('packet_hash')!r} != the hash of the "
                       f"packet actually sent ({expected_packet_hash!r})")
    if reasons:
        return ValidationResultV4(False, lifecycle.SCHEMA_INVALID, reasons,
                                  canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  failure_class=MODEL_SCHEMA_INVALID)

    # ---- gate 3: firewall ------------------------------------------------------------
    findings = firewall_v4.scan(canon, packet=packet)
    blk = firewall_v4.blocking(findings)
    grading = [v for v in blk if v.layer == "GRADE"]
    numeric = [v for v in blk if v.layer != "GRADE"]
    if numeric:
        return ValidationResultV4(False, lifecycle.NUMERICAL_AUTHORITY_VIOLATION,
                                  [str(v) for v in numeric], canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  firewall_findings=findings,
                                  failure_class=MODEL_SCHEMA_INVALID)
    if grading:
        return ValidationResultV4(False, lifecycle.LATENT_GRADING_VIOLATION,
                                  [str(v) for v in grading], canonical_payload=canon,
                                  canonicalization=creport.to_dict(),
                                  firewall_findings=findings,
                                  failure_class=MODEL_SCHEMA_INVALID)

    # ---- gates 4-7 -------------------------------------------------------------------
    valid_ids = resolve_valid_ids(packet)
    ont = ontology if ontology is not None else (build_ontology_for(packet, manifest)
                                                 if packet else None)
    treport = TR.TranslationReport()
    verdicts, accepted, apparatus_defects = [], [], []

    for h in canon.get("hypotheses", []) or []:
        hid = h.get("hypothesis_id", "<anon>")

        v = _contract_and_grounding(h, hid, valid_ids, bool(packet))

        if v.accepted and packet:
            adm = ADM.packet_admissibility_reasons(h, packet)
            if adm:
                v.accepted = False
                v.failure = lifecycle.UNSUPPORTED_CONTEXT_SOURCE
                v.reasons = list(v.reasons) + adm

        if v.accepted:
            try:
                internal = TR.translate_hypothesis(h, treport)
            except TR.UntranslatableTerm as exc:
                # A term the schema admitted but the ontology cannot map is OUR defect,
                # not the model's. Before this it escaped as an uncaught traceback from
                # inside the per-hypothesis loop, which mid-paid-run would have aborted
                # the driver rather than firing the stop rule that exists to count it.
                apparatus_defects.append({"hypothesis_id": hid, "error": str(exc)})
                v.accepted = False
                v.failure = lifecycle.UNSUPPORTED_CONTEXT_SOURCE
                v.reasons = list(v.reasons) + [
                    f"APPARATUS DEFECT, not a model error: {exc}"]
                verdicts.append(v)
                continue
            engine_reasons = _engine_gates(internal, manifest)
            if engine_reasons:
                v.accepted = False
                v.failure = engine_reasons[0]
                v.reasons = list(v.reasons) + engine_reasons[1:]
            elif ont is not None:
                axis_problems = availability.unavailable_axis_reasons(internal, ont)
                if axis_problems:
                    v.accepted = False
                    v.failure = lifecycle.UNSUPPORTED_CONTEXT_SOURCE
                    v.reasons = list(v.reasons) + axis_problems
            if v.accepted:
                accepted.append(internal)

        verdicts.append(v)

    return ValidationResultV4(True, None, [], verdicts, accepted,
                              canonical_payload=canon,
                              canonicalization=creport.to_dict(),
                              firewall_findings=findings,
                              translation=treport.to_dict(),
                              apparatus_defects=apparatus_defects,
                              failure_class=(INFRASTRUCTURE_CONTRACT_FAILURE
                                             if apparatus_defects else None))


def _contract_and_grounding(h: dict, hid: str, valid_ids: set, have_packet: bool):
    """Abstention contract + evidence grounding, in MODEL language.

    The abstention rule is task S5's PREFERRED contract, and the prompt states it in the
    same sentence that invites abstention:

        INSUFFICIENT_EVIDENCE + no refs           -> accepted
        INSUFFICIENT_EVIDENCE + refs in packet    -> accepted  (the D2 fix)
        INSUFFICIENT_EVIDENCE + refs not in packet-> rejected  (fabrication)
        SUFFICIENT            + no refs           -> rejected
    """
    refs = h.get("evidence_refs") or []
    sufficiency = h.get("sufficiency")
    abstaining = sufficiency == vocabulary.SUFFICIENCY[1]   # INSUFFICIENT_EVIDENCE

    if have_packet:
        unknown = [r for r in refs if r not in valid_ids]
        if unknown:
            return validator.HypothesisVerdict(
                hid, False, lifecycle.INSUFFICIENT_EVIDENCE,
                [f"evidence_refs not present in the packet actually sent: {unknown[:5]}; "
                 f"a reference the packet does not contain is ungrounded football "
                 f"knowledge, not evidence"])

    if abstaining:
        # Citing the evidence that demonstrates the gap is ALLOWED and is better research
        # practice than a bare abstention: it says WHY the question cannot be supported.
        return validator.HypothesisVerdict(hid, True)

    if not refs:
        return validator.HypothesisVerdict(
            hid, False, lifecycle.INSUFFICIENT_EVIDENCE,
            ["a SUFFICIENT hypothesis must cite at least one evidence id; if the packet "
             "did not support the question, mark it INSUFFICIENT_EVIDENCE instead"])

    return validator.HypothesisVerdict(hid, True)


def _engine_gates(internal: dict, manifest) -> list:
    """Capability + metric gates, in ENGINE language. `[failure, *reasons]` or `[]`."""
    for cap_name in internal.get("required_capabilities") or []:
        spec = capability.context_source(cap_name)
        if spec is None:
            return [lifecycle.UNSUPPORTED_CONTEXT_SOURCE,
                    f"translated capability {cap_name!r} is not a known context source; "
                    f"this is an ontology defect, not a model error"]
        if spec.status != capability.SUPPORTED:
            return [lifecycle.UNSUPPORTED_CONTEXT_SOURCE,
                    f"required capability {cap_name!r} is {spec.status}: {spec.note}"]

    for m in internal.get("target_metrics") or []:
        if not capability.is_supported_metric(m):
            return [lifecycle.UNSUPPORTED_METRIC,
                    f"metric {m!r} is not in the capability inventory"]
        if manifest is not None and not manifest.allows_metric(m):
            return [lifecycle.UNSUPPORTED_METRIC,
                    f"metric {m!r} is not available for this fixture"]
    return []


def version_stamp() -> dict:
    from src.research.hypothesis_oos import v5a2_admissibility as ADM
    from src.research.hypothesis_oos import v5a2_translate as TR
    return {"validator_version": VALIDATOR_VERSION,
            "delegates_gates_to": validator_v2.VALIDATOR_VERSION,
            "admissibility_version": ADM.ADMISSIBILITY_VERSION,
            "translation_version": TR.TRANSLATION_VERSION,
            **schema_v3.version_stamp(),
            **firewall_v4.version_stamp()}
