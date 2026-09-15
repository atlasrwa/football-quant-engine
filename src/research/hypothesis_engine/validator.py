"""Deterministic hypothesis validator (`hypothesis_validator_v1`).

    The LLM proposes what to measure. It does not own any downstream numerical conclusion.

NO-SALVAGE DISCIPLINE
---------------------
Inherited from the legacy `validator.py`, and kept deliberately: a response that violates
the schema, the numerical-authority firewall or the latent-grading ban is rejected WHOLE.
There is no partial acceptance, no field stripping, no "keep the good hypotheses".

The reason is scientific, not stylistic. If a model emitted a probability in hypothesis 7,
hypotheses 1-6 were produced by the same reasoning process under the same misunderstanding
of its role, and silently keeping them would put unaudited predictive judgement into the
research record.

Per-hypothesis rejection applies only AFTER the whole-response gates pass, and only for
reasons specific to that hypothesis (an unresolvable evidence ref, an unavailable metric).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from . import capability, firewall, lifecycle, schema as schema_mod, vocabulary

VALIDATOR_VERSION = "hypothesis_validator_v1"


@dataclass
class HypothesisVerdict:
    hypothesis_id: str
    accepted: bool
    failure: Optional[str] = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"hypothesis_id": self.hypothesis_id, "accepted": self.accepted,
                "failure": self.failure, "reasons": list(self.reasons)}


@dataclass
class ValidationResult:
    accepted: bool
    #: set when the WHOLE response was rejected
    failure: Optional[str] = None
    reasons: list[str] = field(default_factory=list)
    verdicts: list[HypothesisVerdict] = field(default_factory=list)
    accepted_hypotheses: list[dict] = field(default_factory=list)

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
        }


# --------------------------------------------------------------------------------------
# Minimal JSON-schema checker.
#
# Implemented here rather than pulled from jsonschema so the validator has no runtime
# dependency the research environment might lack, and so every rejection message names the
# exact path. It covers precisely the constructs `hypothesis_set_schema_v1` uses.
# --------------------------------------------------------------------------------------
def _check(node: dict, value, path: str, errs: list[str]) -> None:
    # ---- combinator keywords ----------------------------------------------------------
    # STRICTLY ADDITIVE. `hypothesis_set_schema_v1` contains no `const`, `allOf`, `if` or
    # `not` node, so every v1 validation path below is reached with this block inert and
    # the frozen V2 pipeline's behaviour is unchanged (asserted in
    # test_condition_contract_v3.py). `hypothesis_set_schema_v2` needs them because the
    # condition contract is a CROSS-FIELD rule -- the legal set of `value` depends on
    # `dimension`, and `axis` is required for some dimensions and forbidden for others.
    # That rule is exactly what v1 could not express and what the compiler was left to
    # enforce alone, which is how a wrong-cased value passed schema and died at compile.
    if "const" in node:
        if value != node["const"]:
            errs.append(f"{path}: {value!r} != const {node['const']!r}")
    for sub in node.get("allOf") or ():
        _check(sub, value, path, errs)
    if "if" in node:
        probe: list[str] = []
        _check(node["if"], value, path, probe)
        branch = node.get("then") if not probe else node.get("else")
        if branch is not None:
            _check(branch, value, path, errs)
    if "not" in node:
        probe = []
        _check(node["not"], value, path, probe)
        if not probe:
            errs.append(f"{path}: must not match the forbidden shape "
                        f"{json.dumps(node['not'], sort_keys=True)}")

    t = node.get("type")

    if t == "object":
        if not isinstance(value, dict):
            errs.append(f"{path}: expected object, got {type(value).__name__}")
            return
        for req in node.get("required", []):
            if req not in value:
                errs.append(f"{path}.{req}: required field missing")
        props = node.get("properties", {})
        if node.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    errs.append(f"{path}.{k}: unknown field (additionalProperties=false)")
        for k, sub in props.items():
            if k in value:
                _check(sub, value[k], f"{path}.{k}", errs)
        return

    if t == "array":
        if not isinstance(value, list):
            errs.append(f"{path}: expected array, got {type(value).__name__}")
            return
        if "minItems" in node and len(value) < node["minItems"]:
            errs.append(f"{path}: {len(value)} items < minItems {node['minItems']}")
        if "maxItems" in node and len(value) > node["maxItems"]:
            errs.append(f"{path}: {len(value)} items > maxItems {node['maxItems']}")
        item = node.get("items")
        if item:
            for i, v in enumerate(value):
                _check(item, v, f"{path}[{i}]", errs)
        return

    if t == "string":
        if not isinstance(value, str):
            errs.append(f"{path}: expected string, got {type(value).__name__}")
            return
        enum = node.get("enum")
        if enum is not None and value not in enum:
            errs.append(f"{path}: {value!r} not in enum ({len(enum)} allowed)")
        if "minLength" in node and len(value) < node["minLength"]:
            errs.append(f"{path}: length {len(value)} < minLength {node['minLength']}")
        if "maxLength" in node and len(value) > node["maxLength"]:
            errs.append(f"{path}: length {len(value)} > maxLength {node['maxLength']}")
        pat = node.get("pattern")
        if pat:
            import re
            if not re.match(pat, value):
                errs.append(f"{path}: {value!r} does not match pattern {pat}")
        return

    if t is not None:
        errs.append(f"{path}: unsupported schema type {t!r}")


def validate_schema(payload) -> list[str]:
    errs: list[str] = []
    _check(schema_mod.build_schema(), payload, "$", errs)
    return errs


def validate_schema_against(schema_doc: dict, payload) -> list[str]:
    """Validate a payload against an EXPLICIT schema document.

    Exists so the V3 path can use `schema_v2.build_schema()` (the closed condition
    contract) through the same checker, without `validate_schema` -- and therefore the
    frozen V2 pipeline -- changing which schema it points at.
    """
    errs: list[str] = []
    _check(schema_doc, payload, "$", errs)
    return errs


# --------------------------------------------------------------------------------------
# Whole-response gates
# --------------------------------------------------------------------------------------
def validate(
    payload,
    *,
    packet: Optional[dict] = None,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
    expected_packet_hash: Optional[str] = None,
    expected_fixture_id: Optional[str] = None,
) -> ValidationResult:
    """Validate one hypothesis-set response.

    Order matters: cheap structural gates first, then the firewall, then per-hypothesis
    grounding. A failure at any whole-response gate returns immediately with no accepted
    hypotheses.
    """
    # ---- gate 1: schema (also the firewall's structural layer) ------------------------
    if not isinstance(payload, dict):
        return ValidationResult(False, lifecycle.SCHEMA_INVALID,
                                [f"response is {type(payload).__name__}, not an object"])
    errs = validate_schema(payload)
    if errs:
        return ValidationResult(False, lifecycle.SCHEMA_INVALID, errs)

    # ---- gate 2: identity binding -----------------------------------------------------
    reasons: list[str] = []
    if expected_fixture_id and payload.get("fixture_id") != expected_fixture_id:
        reasons.append(f"fixture_id {payload.get('fixture_id')!r} != expected "
                       f"{expected_fixture_id!r}")
    if expected_packet_hash and payload.get("packet_hash") != expected_packet_hash:
        reasons.append(f"packet_hash {payload.get('packet_hash')!r} != the hash of the "
                       f"packet actually sent ({expected_packet_hash!r}); the response "
                       f"cannot be bound to its evidence")
    if reasons:
        return ValidationResult(False, lifecycle.SCHEMA_INVALID, reasons)

    # ---- gate 3: numerical-authority firewall (whole response) -------------------------
    violations = firewall.scan(payload)
    grading = [v for v in violations if v.layer == "GRADE"]
    numeric = [v for v in violations if v.layer != "GRADE"]
    if numeric:
        return ValidationResult(False, lifecycle.NUMERICAL_AUTHORITY_VIOLATION,
                                [str(v) for v in numeric])
    if grading:
        return ValidationResult(False, lifecycle.LATENT_GRADING_VIOLATION,
                                [str(v) for v in grading])

    # ---- gate 4: per-hypothesis grounding / capability ---------------------------------
    valid_ids = set()
    if packet:
        valid_ids = {it.get("id") for it in (packet.get("evidence") or []) if it.get("id")}

    verdicts: list[HypothesisVerdict] = []
    accepted: list[dict] = []

    for h in payload.get("hypotheses", []) or []:
        hid = h.get("hypothesis_id", "<anon>")
        v = _validate_one(h, hid, valid_ids, manifest, bool(packet))
        verdicts.append(v)
        if v.accepted:
            accepted.append(h)

    return ValidationResult(True, None, [], verdicts, accepted)


def _validate_one(h: dict, hid: str, valid_ids: set, manifest, have_packet: bool
                  ) -> HypothesisVerdict:
    reasons: list[str] = []

    sufficiency = h.get("sufficiency")
    refs = h.get("evidence_refs") or []

    # ---- evidence grounding -----------------------------------------------------------
    # Abstention is a valid, first-class outcome (mandate §16): a hypothesis marked
    # INSUFFICIENT_EVIDENCE is ACCEPTED as an honest abstention and carries no refs.
    if sufficiency == vocabulary.SUFFICIENCY[1]:      # INSUFFICIENT_EVIDENCE
        if refs:
            reasons.append("an INSUFFICIENT_EVIDENCE abstention must not cite evidence; "
                           "citing evidence contradicts the abstention")
            return HypothesisVerdict(hid, False, lifecycle.INSUFFICIENT_EVIDENCE, reasons)
        return HypothesisVerdict(hid, True)

    if not refs:
        return HypothesisVerdict(
            hid, False, lifecycle.INSUFFICIENT_EVIDENCE,
            ["a SUFFICIENT hypothesis must cite at least one evidence id; if the packet "
             "did not support the question, mark it INSUFFICIENT_EVIDENCE instead"])

    if have_packet:
        unknown = [r for r in refs if r not in valid_ids]
        if unknown:
            return HypothesisVerdict(
                hid, False, lifecycle.INSUFFICIENT_EVIDENCE,
                [f"evidence_refs not present in the packet actually sent: {unknown[:5]}; "
                 f"a reference the packet does not contain is ungrounded football "
                 f"knowledge, not evidence"])

    # ---- required capabilities --------------------------------------------------------
    for cap_name in h.get("required_capabilities") or []:
        spec = capability.context_source(cap_name)
        if spec is None:
            return HypothesisVerdict(
                hid, False, lifecycle.UNSUPPORTED_CONTEXT_SOURCE,
                [f"required capability {cap_name!r} is not a known context source"])
        if spec.status != capability.SUPPORTED:
            return HypothesisVerdict(
                hid, False, lifecycle.UNSUPPORTED_CONTEXT_SOURCE,
                [f"required capability {cap_name!r} is {spec.status}: {spec.note}"])

    # ---- metric availability ----------------------------------------------------------
    for m in h.get("target_metrics") or []:
        if not capability.is_supported_metric(m):
            return HypothesisVerdict(
                hid, False, lifecycle.UNSUPPORTED_METRIC,
                [f"metric {m!r} is not in the capability inventory"])
        if manifest is not None and not manifest.allows_metric(m):
            return HypothesisVerdict(
                hid, False, lifecycle.UNSUPPORTED_METRIC,
                [f"metric {m!r} is not available for this fixture"])

    return HypothesisVerdict(hid, True, None, reasons)
