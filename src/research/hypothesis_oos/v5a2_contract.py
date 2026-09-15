"""Condition canonicalization over the V5A.2 ontology (`v5a2_condition_contract_v1`).

`condition_contract.py` does exactly this job for the INTERNAL vocabulary, and it is frozen
(hashed into the V3 and V5A preregistrations). This module is the same discipline applied
to the ONE model-visible language defined in `v5a2_ontology`, and it deliberately reuses
`condition_contract.fold` rather than restating the folding rule, so the two cannot disagree
about what counts as a spelling.

The alias family is unchanged and still mechanical only: case, hyphen/space -> underscore,
surrounding whitespace. There is no semantic aliasing. In particular `venue` does NOT fold
onto `historical_venue_conditioning`: those are two different claims about what evidence a
question needs (task S6), and quietly resolving one to the other would reintroduce exactly
the ambiguity the split exists to remove. A bare `venue` fails closed with a reason that
names both terms.

ZERO SPEND.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.research.hypothesis_engine.condition_contract import (
    AXIS_NOT_APPLICABLE, MALFORMED_CONDITION, MISSING_AXIS, UNKNOWN_AXIS,
    UNKNOWN_DIMENSION, UNKNOWN_VALUE, fold,
)
from src.research.hypothesis_oos import v5a2_ontology as O

CONTRACT_VERSION = "v5a2_condition_contract_v1"

CONTRACT_REASONS = (UNKNOWN_DIMENSION, UNKNOWN_VALUE, MISSING_AXIS, UNKNOWN_AXIS,
                    AXIS_NOT_APPLICABLE, MALFORMED_CONDITION)

#: Retired spellings that MUST NOT be silently resolved, mapped to the guidance shown when
#: one appears. `venue` was a single term carrying two meanings in V5A.1; a model writing it
#: is making a claim we cannot disambiguate on its behalf.
AMBIGUOUS_RETIRED_TERMS = {
    "venue": (f"{O.HISTORICAL_VENUE_CONDITIONING!r} to split PRIOR matches by where they "
              f"were played, or {O.TARGET_FIXTURE_VENUE_CONTEXT!r} for the fact that the "
              f"upcoming fixture has a home side"),
}


def _resolve(token: str, legal) -> Optional[str]:
    folded = fold(token)
    for candidate in legal:
        if fold(candidate) == folded:
            return candidate
    return None


@dataclass(frozen=True)
class CanonicalCondition:
    dimension: str
    value: str
    axis: Optional[str] = None
    canonicalized: bool = False

    def to_dict(self) -> dict:
        d = {"dimension": self.dimension, "value": self.value}
        if self.axis:
            d["axis"] = self.axis
        return d


@dataclass(frozen=True)
class ContractFailure:
    reason: str
    detail: str
    dimension: Optional[str] = None
    value: Optional[str] = None
    axis: Optional[str] = None

    def to_dict(self) -> dict:
        return {"reason": self.reason, "detail": self.detail, "dimension": self.dimension,
                "value": self.value, "axis": self.axis}


def canonicalize_condition(raw: Any):
    if not isinstance(raw, dict):
        return ContractFailure(MALFORMED_CONDITION,
                               f"condition must be an object, got {type(raw).__name__}")

    dim_raw, val_raw, axis_raw = raw.get("dimension"), raw.get("value"), raw.get("axis")
    if not isinstance(dim_raw, str):
        return ContractFailure(MALFORMED_CONDITION,
                               f"`dimension` must be a string, got {type(dim_raw).__name__}")
    if not isinstance(val_raw, str):
        return ContractFailure(MALFORMED_CONDITION,
                               f"`value` must be a string, got {type(val_raw).__name__}",
                               dimension=dim_raw)

    legal_dims = O.condition_dimension_terms()
    dimension = dim_raw if dim_raw in legal_dims else _resolve(dim_raw, legal_dims)
    if dimension is None:
        hint = AMBIGUOUS_RETIRED_TERMS.get(fold(dim_raw).lower())
        detail = (f"dimension {dim_raw!r} is not a term this packet declares; declared "
                  f"conditionable terms: {legal_dims}")
        if hint:
            detail += (f". {dim_raw!r} is deliberately not a term: write {hint}")
        return ContractFailure(UNKNOWN_DIMENSION, detail,
                               dimension=dim_raw, value=val_raw, axis=axis_raw)

    legal_values = O.values_for(dimension)
    value = _resolve(val_raw, legal_values)
    if value is None:
        return ContractFailure(
            UNKNOWN_VALUE,
            f"value {val_raw!r} is not legal for {dimension!r} and is not a spelling of "
            f"any legal value; legal: {list(legal_values)}",
            dimension=dimension, value=val_raw, axis=axis_raw)

    legal_axes = O.axes_for(dimension)
    axis: Optional[str] = None
    if axis_raw is not None:
        if not isinstance(axis_raw, str):
            return ContractFailure(MALFORMED_CONDITION,
                                   f"`axis` must be a string, got {type(axis_raw).__name__}",
                                   dimension=dimension, value=value)
        if not legal_axes:
            return ContractFailure(
                AXIS_NOT_APPLICABLE,
                f"`axis` is only meaningful for {list(O.axis_required_terms())}, not "
                f"{dimension!r}", dimension=dimension, value=value, axis=axis_raw)
        axis = _resolve(axis_raw, legal_axes)
        if axis is None:
            return ContractFailure(
                UNKNOWN_AXIS,
                f"axis {axis_raw!r} is not a measurable profile axis and is not a spelling "
                f"of one; legal: {list(legal_axes)}",
                dimension=dimension, value=value, axis=axis_raw)
    elif legal_axes:
        return ContractFailure(
            MISSING_AXIS,
            f"{dimension!r} requires an `axis` naming the measured axis the band applies "
            f"to; legal: {list(legal_axes)}", dimension=dimension, value=value)

    canonicalized = (dim_raw != dimension or val_raw != value
                     or (axis_raw is not None and axis_raw != axis))
    return CanonicalCondition(dimension, value, axis, canonicalized)


@dataclass
class CanonicalizationReport:
    contract_version: str = CONTRACT_VERSION
    n_conditions: int = 0
    n_canonicalized: int = 0
    n_failed: int = 0
    failures: dict = None
    alias_counts: dict = None

    def __post_init__(self):
        if self.failures is None:
            self.failures = {}
        if self.alias_counts is None:
            self.alias_counts = {}

    @property
    def ok(self) -> bool:
        return self.n_failed == 0

    def to_dict(self) -> dict:
        return {"contract_version": self.contract_version,
                "n_conditions": self.n_conditions,
                "n_canonicalized": self.n_canonicalized,
                "n_failed": self.n_failed, "ok": self.ok,
                "failures": {k: list(v) for k, v in sorted(self.failures.items())},
                "alias_counts": {"|".join(k): v
                                 for k, v in sorted(self.alias_counts.items())}}


def canonicalize_payload(payload: dict):
    """Return (canonicalized copy, report).

    A condition that fails is left EXACTLY as the model wrote it and recorded in the
    report -- never dropped, never repaired. Downstream schema validation must still see
    and reject the real thing, so a contract failure stays a visible failure rather than
    being laundered into a pass.
    """
    report = CanonicalizationReport()
    if not isinstance(payload, dict):
        return payload, report
    out = dict(payload)
    hyps = payload.get("hypotheses")
    if not isinstance(hyps, list):
        return out, report

    new_hyps = []
    for idx, h in enumerate(hyps):
        if not isinstance(h, dict):
            new_hyps.append(h)
            continue
        hid = h.get("hypothesis_id", f"<anon{idx}>")
        conds = h.get("conditions")
        if not isinstance(conds, list):
            new_hyps.append(h)
            continue
        new_conds = []
        for raw in conds:
            report.n_conditions += 1
            res = canonicalize_condition(raw)
            if isinstance(res, ContractFailure):
                report.n_failed += 1
                report.failures.setdefault(hid, []).append(res.to_dict())
                new_conds.append(raw)
                continue
            if res.canonicalized:
                report.n_canonicalized += 1
                key = (res.dimension, str(raw.get("value")), res.value)
                report.alias_counts[key] = report.alias_counts.get(key, 0) + 1
            new_conds.append(res.to_dict())
        nh = dict(h)
        nh["conditions"] = new_conds
        new_hyps.append(nh)
    out["hypotheses"] = new_hyps
    return out, report


def condition_schema() -> dict:
    """JSON-Schema for ONE condition, closed over the ontology.

    Structurally identical to `condition_contract.condition_schema()` -- same flat shape,
    same `allOf` branch style -- because `firewall._FIELD_NAME_EXEMPT_PATHS` and
    `vocabulary.BAND_EXEMPT_PATH_SUFFIXES` key on the literal path `conditions.value`.
    Only the vocabulary it projects differs.
    """
    branches = []
    for dim in O.condition_dimension_terms():
        values, axes = list(O.values_for(dim)), list(O.axes_for(dim))
        then: dict = {"type": "object",
                      "properties": {"value": {"type": "string", "enum": values}}}
        if axes:
            then["required"] = ["axis"]
            then["properties"]["axis"] = {"type": "string", "enum": axes}
        else:
            then["not"] = {"type": "object", "required": ["axis"]}
        branches.append({"if": {"type": "object",
                                "properties": {"dimension": {"const": dim}},
                                "required": ["dimension"]},
                         "then": then})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimension", "value"],
        "properties": {
            "dimension": {"type": "string", "enum": O.condition_dimension_terms()},
            "value": {"type": "string", "enum": list(O.all_condition_values())},
            "axis": {"type": "string", "enum": list(O.all_condition_axes())},
        },
        "allOf": branches,
    }
