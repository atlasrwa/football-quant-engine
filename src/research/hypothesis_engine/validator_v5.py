"""Per-HYPOTHESIS adjudication (`validator_v5`). §3, §8, §19.

    A failure in hypothesis H4 must NOT invalidate H1-H3 or H5-H12 unless the entire
    response is structurally unparsable.

WHAT V5A.2 DID
--------------
`validator_v4.validate` has four early returns before the per-hypothesis loop is reached:
schema, identity, numerical-authority firewall, latent grading. Each returns a
`ValidationResultV4(False, ...)` for the WHOLE response. In the live run the third one
fired twice, on one `'50%'` in one question, and 24 hypotheses with 183 well-formed
evidence references between them were discarded unread.

That is not a loop bug. `validator.validate_schema_against(schema_v3.build_schema(), canon)`
validates the whole DOCUMENT, so one bad enum fails the `hypotheses` array and fails the
document no matter what the caller does afterwards. The fix has to reach the schema, which
is why `schema_v4` splits it, and the firewall, which is why `firewall_v5` scans one
hypothesis at a time.

THE ONLY RESPONSE-FATAL CONDITIONS (§3)
----------------------------------------
    payload is not an object
    `hypotheses` missing, or not an array
    an element of `hypotheses` is not an object
    identity binding fails: `fixture_id` or `packet_hash` is not the packet actually sent

The first three are §3's "individual hypotheses impossible to recover reliably", verbatim.
The fourth is the one non-recoverability that is not about shape: a response bound to a
different packet is not evidence about THIS packet, and no per-hypothesis salvage can make
it so. Every other failure -- every one -- is adjudicated per hypothesis.

EVERY GATE RUNS FOR EVERY HYPOTHESIS (§19)
-------------------------------------------
There is no short-circuit. A hypothesis that fails grounding is still put through
availability, firewall, comparator, degeneracy and the compiler, and every result is
recorded. `v6_classes.GATE_ORDER` then names the class by the FIRST gate that failed, so
the class is deterministic while the diagnostics stay complete. §19: "Do not collapse
failures too early."

The one thing that cannot be evaluated after a schema failure is a field the schema failure
makes unreadable. Those gates record `None` -- NOT MEASURED -- and `None` is never treated
as a pass anywhere downstream.

ZERO SPEND.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import (availability, capability, firewall_v5, lifecycle, query_plan as QP,
               schema_v4, validator, vocabulary)

VALIDATOR_VERSION = "validator_v5"


@dataclass
class HypothesisAdjudication:
    """One hypothesis, judged on its own. Never depends on a sibling except for redundancy,
    which is inherently a relation and is evaluated in response order (first wins)."""
    index: int
    hypothesis_id: str
    outcome_class: str
    scorecard: dict = field(default_factory=dict)
    reasons: dict = field(default_factory=dict)
    firewall_findings: list = field(default_factory=list)
    numeric_findings: list = field(default_factory=list)
    comparator: dict = field(default_factory=dict)
    conditioning: dict = field(default_factory=dict)
    internal: Optional[dict] = None
    #: The CANONICALIZED hypothesis as the model wrote it. Kept on every adjudication,
    #: including rejected ones, so the scorecard can report what a rejected hypothesis was
    #: ABOUT -- which metrics, which references -- instead of reporting a hole. V5A.2 could
    #: not do this: its research-arm diversity counts were `_blank_score` defaults.
    hypothesis: Optional[dict] = None
    abstaining: bool = False
    n_refs: int = 0
    n_valid_refs: int = 0
    n_fabricated_refs: int = 0

    def to_dict(self) -> dict:
        return {"index": self.index, "hypothesis_id": self.hypothesis_id,
                "outcome_class": self.outcome_class,
                "scorecard": dict(self.scorecard),
                "reasons": {k: list(v) for k, v in sorted(self.reasons.items())},
                "firewall": [f.to_dict() for f in self.firewall_findings],
                "numeric_contract": list(self.numeric_findings),
                "comparator": dict(self.comparator),
                "conditioning": dict(self.conditioning),
                "abstaining": self.abstaining,
                "n_refs": self.n_refs, "n_valid_refs": self.n_valid_refs,
                "n_fabricated_refs": self.n_fabricated_refs}


@dataclass
class ResponseAdjudication:
    response_class: str
    fatal: bool
    reasons: list = field(default_factory=list)
    hypotheses: list = field(default_factory=list)
    canonicalization: Optional[dict] = None
    translation: Optional[dict] = None
    apparatus_defects: list = field(default_factory=list)
    n_proposed: int = 0

    @property
    def recoverable(self) -> list:
        return list(self.hypotheses)

    def to_dict(self) -> dict:
        return {"validator_version": VALIDATOR_VERSION,
                "response_class": self.response_class, "fatal": self.fatal,
                "reasons": list(self.reasons),
                "n_proposed": self.n_proposed,
                "n_recoverable": len(self.hypotheses),
                "canonicalization": self.canonicalization,
                "translation": self.translation,
                "apparatus_defects": list(self.apparatus_defects),
                "hypotheses": [h.to_dict() for h in self.hypotheses]}


def _blank_scorecard() -> dict:
    """Every §19 key, present and `None` (= not measured) until a gate sets it.

    `None` and `False` are kept distinguishable on purpose. V5A.2's `_blank_score()`
    returned ZEROS on a whole-response failure, and its own execution report had to warn
    that "any table that prints research-arm zeros here is printing a placeholder". A
    scorecard that cannot express "not measured" forces that warning into prose.
    """
    return {
        "numeric_contract_valid": None,
        "schema_valid": None,
        "evidence_grounded": None,
        "evidence_refs_valid": None,
        "availability_valid": None,
        "firewall_valid": None,
        "comparator_valid": None,
        "nondegenerate": None,
        "nonredundant": None,
        "compiler_valid": None,
        "contextually_supported": None,
        "redundant": None,
        "abstaining": None,
        "qualified": None,
    }


def _identity_reasons(payload, expected_packet_hash, expected_fixture_id) -> list:
    out = []
    if expected_fixture_id and payload.get("fixture_id") != expected_fixture_id:
        out.append(f"fixture_id {payload.get('fixture_id')!r} != expected "
                   f"{expected_fixture_id!r}; this response is not about the packet sent")
    if expected_packet_hash and payload.get("packet_hash") != expected_packet_hash:
        out.append(f"packet_hash {payload.get('packet_hash')!r} != the hash of the packet "
                   f"actually sent ({expected_packet_hash!r})")
    return out


def _intent_key(h: dict) -> tuple:
    """The measurable intent of a hypothesis, for the redundancy relation.

    Everything that changes WHAT is measured, and nothing that changes only how it is
    worded. `question`, `evidence_refs`, `candidate_confounders`, `priority` and
    `evidence_summary` are excluded: two identically-specified measurements are the same
    measurement however differently they are narrated. `priority` is excluded for the
    additional reason in §23 -- a model-supplied confidence-like token is not data.
    """
    return (
        str(vocabulary.canonical_subject(str(h.get("subject") or "")) or h.get("subject")),
        tuple(sorted(str(m) for m in (h.get("target_metrics") or []))),
        str(h.get("side")), str(h.get("window")), str(h.get("comparison")),
        tuple(sorted((str(c.get("dimension")), str(c.get("value")), str(c.get("axis")))
                     for c in (h.get("conditions") or []) if isinstance(c, dict))),
    )


def _contextually_supported(h, valid_ids, conditioning) -> bool:
    """§10 conjunct 8 / §19: is this question justified by evidence available in THIS arm?

    Three requirements, all structural:
      1. at least one cited reference resolves in this packet (an abstention is exempt --
         §17 makes an evidence-free abstention valid);
      2. every dimension the hypothesis conditions on is backed by a citation of evidence
         FOR that dimension (`v6_conditioning.condition_support`);
      3. a recent-window or venue use is backed the same way.

    This is about JUSTIFICATION, not legality. A hypothesis can be perfectly admissible
    (the packet exposes the term) and still be unsupported (the model cited nothing that
    shows the term matters here). §16 asks for exactly that distinction and asks not to
    reward citation volume for its own sake, so the test is existence, never count.
    """
    if h.get("sufficiency") == "INSUFFICIENT_EVIDENCE":
        return True
    good = [r for r in (h.get("evidence_refs") or []) if r in valid_ids]
    if not good:
        return False
    if conditioning.get("all_conditions_supported") is False:
        return False
    for name, rec in (conditioning.get("dimension_uses") or {}).items():
        if rec.get("used") and rec.get("supported_by_refs") is False:
            return False
    return True


def adjudicate(payload, *, packet=None, manifest=None, expected_packet_hash=None,
               expected_fixture_id=None, ontology=None) -> ResponseAdjudication:
    """Adjudicate ONE response. The whole point of V6 lives in this function."""
    from src.research.hypothesis_oos import v5a2_admissibility as ADM
    from src.research.hypothesis_oos import v5a2_contract as C
    from src.research.hypothesis_oos import v5a2_translate as TR
    from src.research.hypothesis_oos import v5a1_evidence as E
    from src.research.hypothesis_oos import v6_baseline as BL
    from src.research.hypothesis_oos import v6_classes as K
    from src.research.hypothesis_oos import v6_conditioning as CD
    from src.research.hypothesis_oos import v6_numeric_contract as NC

    # ---- RESPONSE-FATAL gate 1: is it an object at all? -------------------------------
    if not isinstance(payload, dict):
        return ResponseAdjudication(
            K.RESPONSE_PARSE_FATAL, True,
            [f"response is {type(payload).__name__}, not an object; no hypotheses can be "
             f"recovered from it"])

    # ---- RESPONSE-FATAL gate 2: envelope only. Item contents are NOT consulted. -------
    errs = validator.validate_schema_against(schema_v4.envelope_schema(), payload)
    if errs:
        return ResponseAdjudication(
            K.RESPONSE_PARSE_FATAL, True,
            [f"envelope schema: {e}" for e in errs],
            n_proposed=len(payload.get("hypotheses") or [])
            if isinstance(payload.get("hypotheses"), list) else 0)

    # ---- RESPONSE-FATAL gate 3: identity binding --------------------------------------
    ident = _identity_reasons(payload, expected_packet_hash, expected_fixture_id)
    if ident:
        return ResponseAdjudication(
            K.RESPONSE_PARSE_FATAL, True, ident,
            n_proposed=len(payload.get("hypotheses") or []))

    # From here on NOTHING is response-fatal. Every remaining failure is per hypothesis.
    canon, creport = C.canonicalize_payload(payload)
    raw_hyps = payload.get("hypotheses") or []
    canon_hyps = canon.get("hypotheses") or []
    valid_ids = E.resolve_evidence_ids(packet)
    ev_values = E.resolve_evidence_values(packet) if packet else ()
    sample_ns = firewall_v5.sample_n_values(packet)
    item_schema = schema_v4.hypothesis_item_schema()
    ont = ontology
    if ont is None and packet is not None:
        from src.research.hypothesis_oos import v5a2_view as VIEW
        ont = VIEW.build_ontology_view(packet, manifest)

    treport = TR.TranslationReport()
    adjudications, apparatus_defects, seen_intents = [], [], {}

    for i, (raw_h, h) in enumerate(zip(raw_hyps, canon_hyps)):
        hid = h.get("hypothesis_id") if isinstance(h, dict) else None
        hid = hid if isinstance(hid, str) else f"<anon{i}>"
        sc, reasons = _blank_scorecard(), {}

        # -- gate: numeric-authority FIELD contract (§5). Before schema, so a numerical
        #    authority claim is never recorded as a generic malformed object.
        numeric_findings = NC.scan_hypothesis(raw_h)
        sc["numeric_contract_valid"] = not numeric_findings
        if numeric_findings:
            reasons["numeric_contract_valid"] = [f["detail"] for f in numeric_findings]

        # -- gate: item schema, ONE item -------------------------------------------------
        item_errs = validator.validate_schema_against(item_schema, h)
        sc["schema_valid"] = not item_errs
        if item_errs:
            reasons["schema_valid"] = list(item_errs)

        abstaining = (isinstance(h, dict)
                      and h.get("sufficiency") == vocabulary.SUFFICIENCY[1])
        sc["abstaining"] = abstaining

        refs = [r for r in (h.get("evidence_refs") or []) if isinstance(r, str)]
        good = [r for r in refs if r in valid_ids]
        bad = [r for r in refs if r not in valid_ids]

        if sc["schema_valid"]:
            # -- gate: grounding ---------------------------------------------------------
            g_reasons = []
            if packet is not None and bad:
                g_reasons.append(
                    f"evidence_refs not present in the packet actually sent: {bad[:5]}; a "
                    f"reference the packet does not contain is ungrounded football "
                    f"knowledge, not evidence")
            if not abstaining and not refs:
                g_reasons.append(
                    "a SUFFICIENT hypothesis must cite at least one evidence id; if the "
                    "packet did not support the question, mark it INSUFFICIENT_EVIDENCE")
            sc["evidence_refs_valid"] = not bad
            sc["evidence_grounded"] = not g_reasons
            if g_reasons:
                reasons["evidence_grounded"] = g_reasons

            # -- gate: availability ------------------------------------------------------
            adm = ADM.packet_admissibility_reasons(h, packet) if packet else []
            sc["availability_valid"] = not adm
            if adm:
                reasons["availability_valid"] = list(adm)

            # -- gate: firewall, SCOPED TO THIS HYPOTHESIS -------------------------------
            fw = firewall_v5.scan_hypothesis(h, i, packet=packet, values=ev_values,
                                             sample_ns=sample_ns)
            fw_block = firewall_v5.blocking(fw)
            sc["firewall_valid"] = not fw_block
            if fw_block:
                reasons["firewall_valid"] = [str(v) for v in fw_block]

            # -- gate: comparator + baseline absorption (§15) ----------------------------
            cmpres = BL.classify(h, packet)
            sc["comparator_valid"] = cmpres["comparator_valid"]
            if cmpres["reasons"]:
                reasons["comparator_valid"] = list(cmpres["reasons"])

            # -- gate: non-degenerate ----------------------------------------------------
            cond = CD.classify(h, packet, valid_ids)
            degen = []
            if cond["conditioning_class"] == CD.LOW_CONTRAST:
                degen.append("a condition with value 'ANY' restricts nothing; the cohort "
                             "is the unconditioned cohort under another name")
            if cond["conditioning_class"] == CD.CONTRADICTORY:
                degen.append("two conditions on the same dimension with different values "
                             "define an empty cohort")
            sc["nondegenerate"] = not degen
            if degen:
                reasons["nondegenerate"] = degen

            # -- gate: non-redundant (relation; first occurrence wins) -------------------
            key = _intent_key(h)
            prior = seen_intents.get(key)
            sc["nonredundant"] = prior is None
            sc["redundant"] = prior is not None
            if prior is not None:
                reasons["nonredundant"] = [
                    f"identical measurable intent to {prior!r} earlier in this response "
                    f"(same subject, metrics, side, window, comparison and conditions); "
                    f"only the repeat is rejected"]
            else:
                seen_intents[key] = hid

            sc["contextually_supported"] = _contextually_supported(h, valid_ids, cond)

            # -- gate: compiler ----------------------------------------------------------
            internal, comp_reasons = None, []
            try:
                internal = TR.translate_hypothesis(h, treport)
            except TR.UntranslatableTerm as exc:
                apparatus_defects.append({"hypothesis_id": hid, "error": str(exc)})
                adjudications.append(HypothesisAdjudication(
                    i, hid, K.INFRASTRUCTURE_FAILURE, sc,
                    {**reasons, "compiler_valid": [f"APPARATUS DEFECT, not a model "
                                                   f"error: {exc}"]},
                    fw, numeric_findings, cmpres, cond, None, h, abstaining,
                    len(refs), len(good), len(bad)))
                continue

            comp_reasons.extend(_engine_gates(internal, manifest))
            if not comp_reasons and ont is not None:
                comp_reasons.extend(availability.unavailable_axis_reasons(internal, ont))
            if not comp_reasons and not abstaining and packet is not None:
                try:
                    plans = QP.compile_hypothesis(
                        internal, fixture_id=packet["fixture_id"],
                        cutoff_unix=packet["information_cutoff_unix"])
                except Exception as exc:                       # compiler refusal
                    comp_reasons.append(f"compiler raised {type(exc).__name__}: {exc}")
                    plans = []
                if not plans or not all(getattr(p, "plan", None) is not None
                                        for p in plans):
                    comp_reasons.append(
                        "the hypothesis did not compile to an executable query plan for "
                        "every target metric")
            sc["compiler_valid"] = not comp_reasons
            if comp_reasons:
                reasons["compiler_valid"] = list(comp_reasons)
        else:
            cmpres, cond, internal = {}, {}, None
            fw = []

        failed = K.first_failed_gate(sc)
        if failed is None:
            outcome = K.VALID_ABSTENTION if abstaining else K.VALID_HYPOTHESIS
        else:
            outcome = failed[1]

        adjudications.append(HypothesisAdjudication(
            i, hid, outcome, sc, reasons, fw, numeric_findings, cmpres, cond,
            internal if outcome in K.HYPOTHESIS_OK_CLASSES else None,
            h if isinstance(h, dict) else None,
            abstaining, len(refs), len(good), len(bad)))

    return ResponseAdjudication(
        K.VALID_MODEL_RESPONSE, False, [], adjudications,
        canonicalization=creport.to_dict(), translation=treport.to_dict(),
        apparatus_defects=apparatus_defects, n_proposed=len(raw_hyps))


def _engine_gates(internal: dict, manifest) -> list:
    """Capability + metric gates, in ENGINE language. Unchanged in substance from v4."""
    out = []
    for cap_name in internal.get("required_capabilities") or []:
        spec = capability.context_source(cap_name)
        if spec is None:
            out.append(f"translated capability {cap_name!r} is not a known context source")
        elif spec.status != capability.SUPPORTED:
            out.append(f"required capability {cap_name!r} is {spec.status}: {spec.note}")
    for m in internal.get("target_metrics") or []:
        if not capability.is_supported_metric(m):
            out.append(f"metric {m!r} is not in the capability inventory")
        elif manifest is not None and not manifest.allows_metric(m):
            out.append(f"metric {m!r} is not available for this fixture")
    return out


def version_stamp() -> dict:
    from src.research.hypothesis_oos import v5a2_admissibility as ADM
    from src.research.hypothesis_oos import v5a2_translate as TR
    from src.research.hypothesis_oos import v6_baseline as BL
    from src.research.hypothesis_oos import v6_classes as K
    from src.research.hypothesis_oos import v6_conditioning as CD
    from src.research.hypothesis_oos import v6_numeric_contract as NC
    return {"validator_version": VALIDATOR_VERSION,
            "adjudication_level": "HYPOTHESIS",
            "response_fatal_conditions": [
                "payload is not an object",
                "`hypotheses` missing or not an array",
                "an element of `hypotheses` is not an object",
                "identity binding (fixture_id / packet_hash) does not match the packet sent"],
            "admissibility_version": ADM.ADMISSIBILITY_VERSION,
            "translation_version": TR.TRANSLATION_VERSION,
            "lifecycle_version": lifecycle.LIFECYCLE_VERSION,
            "query_plan_version": QP.QUERY_PLAN_VERSION,
            **schema_v4.version_stamp(),
            **firewall_v5.version_stamp(),
            **NC.version_stamp(), **BL.version_stamp(), **CD.version_stamp(),
            **K.version_stamp()}
