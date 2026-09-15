"""The canonical condition contract (`hypothesis_condition_contract_v1`).

WHY THIS MODULE EXISTS
----------------------
V2 failed for a mechanical reason that had nothing to do with football: the output schema
typed `conditions[].value` as a FREE STRING, while `query_plan.compile_hypothesis` checked
that value against the dimension's UPPERCASE closed enum. `venue=home` therefore passed
schema validation and died at compile time with UNSUPPORTED_DIMENSION. 40 of 43 observed
reference compile failures were exactly this, and because venue was the model's most-used
conditional structure, the encoding defect made the research look both uncompilable and
shallow at the same time.

This module makes that class of defect impossible by construction.

    ONE SOURCE OF TRUTH, THREE CONSUMERS.

`vocabulary.DIMENSIONS` remains the sole place a condition enum is *defined*. This module
is the canonicalization + projection layer over it, and every downstream layer takes its
notion of "legal" from here:

    schema validation  <- schema_v2.build_schema()      (projects this contract)
    normalization      <- canonicalize_payload()        (applies this contract)
    query compilation  <- query_plan.compile_hypothesis (checks vocabulary.DIMENSIONS)
    evaluation         <- availability / replay layers  (read this contract)

No layer re-declares an enum. `test_condition_contract_v3.py` asserts the projection is
value-identical to `vocabulary.DIMENSIONS` for every dimension, so the two cannot drift.

THE EXTERNAL BOUNDARY IS THE ONLY PLACE SPELLING IS NEGOTIABLE
--------------------------------------------------------------
An LLM writes `home`, `Home`, `HOME`, `back-three`. Those are spellings of one intent, and
rejecting them outright buys nothing scientifically -- it only measures typing. So the
boundary accepts a DETERMINISTIC, MECHANICAL alias family:

    case folding, plus separator folding (space / hyphen -> underscore), plus surrounding
    whitespace.

and nothing else. There is no semantic aliasing: `high_possession` does NOT become
(band=HIGH, axis=possession_for), because that would be the engine inventing the model's
intent. Anything the mechanical folding does not resolve fails CLOSED with a precise,
named reason.

After canonicalization there is EXACTLY ONE internal representation of an intent. Two
responses that differ only in casing normalize to the identical `Condition`, the identical
intent key and the identical plan hash.

FAIL-CLOSED REASONS
-------------------
Every rejection names which of the following it is, so a failure can always be attributed
to a real semantic/capability problem rather than to two components disagreeing about
encoding:

    UNKNOWN_DIMENSION     dimension is not in vocabulary.DIMENSIONS
    UNKNOWN_VALUE         value does not fold to any legal value for that dimension
    MISSING_AXIS          opponent_profile without the required axis
    UNKNOWN_AXIS          axis does not fold to a legal PROFILE_AXES member
    AXIS_NOT_APPLICABLE   axis supplied on a dimension that has no axes
    MALFORMED_CONDITION   condition is not an object, or value is not a string
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from . import vocabulary

CONTRACT_VERSION = "hypothesis_condition_contract_v1"


# --------------------------------------------------------------------------------------
# Fail-closed reason codes.
# --------------------------------------------------------------------------------------
UNKNOWN_DIMENSION = "UNKNOWN_DIMENSION"
UNKNOWN_VALUE = "UNKNOWN_VALUE"
MISSING_AXIS = "MISSING_AXIS"
UNKNOWN_AXIS = "UNKNOWN_AXIS"
AXIS_NOT_APPLICABLE = "AXIS_NOT_APPLICABLE"
MALFORMED_CONDITION = "MALFORMED_CONDITION"

CONTRACT_REASONS = (
    UNKNOWN_DIMENSION, UNKNOWN_VALUE, MISSING_AXIS, UNKNOWN_AXIS,
    AXIS_NOT_APPLICABLE, MALFORMED_CONDITION,
)

#: Dimensions that require an `axis`, read off the vocabulary rather than hardcoded: a
#: dimension declares axes iff an axis is meaningful for it.
def axis_required_dimensions() -> tuple[str, ...]:
    return tuple(sorted(d for d, spec in vocabulary.DIMENSIONS.items() if "axes" in spec))


def dimension_values(dimension: str) -> tuple[str, ...]:
    """The canonical closed value set for a dimension. Projected, never redeclared."""
    spec = vocabulary.dimension(dimension)
    if spec is None:
        raise KeyError(dimension)
    return tuple(spec["values"])


def dimension_axes(dimension: str) -> tuple[str, ...]:
    spec = vocabulary.dimension(dimension)
    if spec is None:
        raise KeyError(dimension)
    return tuple(spec.get("axes") or ())


# --------------------------------------------------------------------------------------
# Axis -> metric resolution.
#
# `vocabulary.PROFILE_AXES` names a MEASURED axis, and its docstring asserts "Every axis
# must be a supported metric." That assertion is FALSE for two entries: `shots_for` and
# `shots_against` have no `shots` metric in `capability.METRICS` (the canonical name is
# `total_shots`). An `opponent_profile` condition on such an axis passes schema-v2 and
# passes `query_plan.compile_hypothesis` -- which only checks `axis in PROFILE_AXES` --
# and then has no metric for the measurement layer to resolve the band from.
#
# This is the SAME CLASS OF DEFECT as the V2 venue-casing mismatch: two layers disagreeing
# about what is legal. It is closed here rather than in `vocabulary.py`, because the frozen
# V2 prespend manifest records `schema_content_hash` and `battery_hash` over the current
# vocabulary and V2 must stay exactly reproducible.
# --------------------------------------------------------------------------------------
#: The orientation suffixes an axis name carries. An axis is <metric><suffix>.
AXIS_SIDE_SUFFIXES = ("_for", "_against")


def axis_base_metric(axis: str) -> Optional[str]:
    """The inventory metric an axis measures, or None if the axis is not well-formed.

    Written as an explicit suffix strip, NOT `rsplit("_", 1)`: the rule is "remove a
    trailing _for/_against", and `total_bookings_for` must resolve to `total_bookings`,
    not to `total_bookings_for`.rsplit -> `total_bookings`. Both happen to agree there, but
    only the suffix rule is the actual contract, so only it is implemented.
    """
    for suffix in AXIS_SIDE_SUFFIXES:
        if axis.endswith(suffix):
            return axis[: -len(suffix)]
    return None


def axis_is_resolvable(axis: str) -> bool:
    """True when the axis names a metric the capability inventory can actually measure."""
    from . import capability
    base = axis_base_metric(axis)
    return bool(base) and capability.metric(base) is not None


def unresolvable_axes() -> tuple[str, ...]:
    """Every `PROFILE_AXES` entry with no backing inventory metric.

    Computed, not hardcoded, so adding an axis to the vocabulary without adding its metric
    is caught by `test_the_axis_metric_hole_is_exactly_two_known_entries` rather than
    silently widening the hole.
    """
    return tuple(a for a in vocabulary.PROFILE_AXES if not axis_is_resolvable(a))


def resolvable_axes() -> tuple[str, ...]:
    return tuple(a for a in vocabulary.PROFILE_AXES if axis_is_resolvable(a))


def all_canonical_values() -> tuple[str, ...]:
    """Union of every legal condition value across every dimension, sorted.

    Used as the schema's base `value` enum; the per-dimension `if/then` branches then
    narrow it to the dimension's own set, so a cross-dimension value (e.g. venue=HIGH) is
    still a schema rejection.
    """
    seen: set[str] = set()
    for dim in vocabulary.DIMENSIONS:
        seen.update(dimension_values(dim))
    return tuple(sorted(seen))


def all_canonical_axes() -> tuple[str, ...]:
    seen: set[str] = set()
    for dim in vocabulary.DIMENSIONS:
        seen.update(dimension_axes(dim))
    return tuple(sorted(seen))


# --------------------------------------------------------------------------------------
# Mechanical folding -- the ONLY alias family accepted at the boundary.
# --------------------------------------------------------------------------------------
def fold(token: str) -> str:
    """Fold an externally-supplied token to its comparison form.

    Case, separators and surrounding whitespace are spelling, not meaning. Everything else
    is meaning and is left alone so it can fail closed.
    """
    return (token.strip()
                 .replace("-", "_")
                 .replace(" ", "_")
                 .upper())


def _resolve(token: str, legal: tuple[str, ...]) -> Optional[str]:
    """Return the canonical member of `legal` that `token` folds onto, else None."""
    folded = fold(token)
    for candidate in legal:
        if fold(candidate) == folded:
            return candidate
    return None


def is_alias(token: str, canonical: str) -> bool:
    """True when `token` is a non-identical spelling that folds onto `canonical`."""
    return token != canonical and fold(token) == fold(canonical)


# --------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CanonicalCondition:
    dimension: str
    value: str
    axis: Optional[str] = None
    #: True when the incoming spelling differed from the canonical one (an alias was
    #: resolved). Reported so the replay can count exactly how many failures were pure
    #: encoding artefacts.
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
        return {"reason": self.reason, "detail": self.detail,
                "dimension": self.dimension, "value": self.value, "axis": self.axis}


def canonicalize_condition(raw: Any) -> CanonicalCondition | ContractFailure:
    """Canonicalize ONE condition, or fail closed with a precise reason.

    This is the single entry point the boundary uses. It never guesses, never drops a
    condition it cannot resolve, and never returns a partially-canonical result.
    """
    if not isinstance(raw, dict):
        return ContractFailure(
            MALFORMED_CONDITION,
            f"condition must be an object, got {type(raw).__name__}")

    dim_raw = raw.get("dimension")
    val_raw = raw.get("value")
    axis_raw = raw.get("axis")

    if not isinstance(dim_raw, str):
        return ContractFailure(
            MALFORMED_CONDITION,
            f"`dimension` must be a string, got {type(dim_raw).__name__}")
    if not isinstance(val_raw, str):
        return ContractFailure(
            MALFORMED_CONDITION,
            f"`value` must be a string, got {type(val_raw).__name__}",
            dimension=dim_raw)

    dimension = _resolve_dimension(dim_raw)
    if dimension is None:
        return ContractFailure(
            UNKNOWN_DIMENSION,
            f"dimension {dim_raw!r} is not a supported cohort dimension; supported: "
            f"{vocabulary.dimension_names()}",
            dimension=dim_raw, value=val_raw)

    legal_values = dimension_values(dimension)
    value = _resolve(val_raw, legal_values)
    if value is None:
        return ContractFailure(
            UNKNOWN_VALUE,
            f"value {val_raw!r} is not legal for dimension {dimension!r} and is not a "
            f"spelling of any legal value; legal: {list(legal_values)}",
            dimension=dimension, value=val_raw, axis=axis_raw)

    legal_axes = dimension_axes(dimension)
    axis: Optional[str] = None
    if axis_raw is not None:
        if not isinstance(axis_raw, str):
            return ContractFailure(
                MALFORMED_CONDITION,
                f"`axis` must be a string, got {type(axis_raw).__name__}",
                dimension=dimension, value=value)
        if not legal_axes:
            return ContractFailure(
                AXIS_NOT_APPLICABLE,
                f"`axis` is only meaningful for {list(axis_required_dimensions())}, "
                f"not {dimension!r}",
                dimension=dimension, value=value, axis=axis_raw)
        axis = _resolve(axis_raw, legal_axes)
        if axis is None:
            return ContractFailure(
                UNKNOWN_AXIS,
                f"axis {axis_raw!r} is not a measurable profile axis and is not a "
                f"spelling of one; legal: {list(legal_axes)}",
                dimension=dimension, value=value, axis=axis_raw)
    elif legal_axes:
        return ContractFailure(
            MISSING_AXIS,
            f"dimension {dimension!r} requires an `axis` naming the measured dimension "
            f"the band applies to; legal: {list(legal_axes)}",
            dimension=dimension, value=value)

    canonicalized = (dim_raw != dimension
                     or val_raw != value
                     or (axis_raw is not None and axis_raw != axis))
    return CanonicalCondition(dimension=dimension, value=value, axis=axis,
                              canonicalized=canonicalized)


def _resolve_dimension(token: str) -> Optional[str]:
    if token in vocabulary.DIMENSIONS:
        return token
    return _resolve(token, tuple(sorted(vocabulary.DIMENSIONS)))


# --------------------------------------------------------------------------------------
# Payload-level canonicalization.
#
# Applied at the external boundary, BEFORE schema validation and BEFORE compilation, so
# that everything downstream sees exactly one representation.
# --------------------------------------------------------------------------------------
@dataclass
class CanonicalizationReport:
    """What the boundary did to a response, in auditable detail."""

    contract_version: str
    n_conditions: int = 0
    n_canonicalized: int = 0
    n_failed: int = 0
    #: hypothesis_id -> list of ContractFailure dicts
    failures: dict = None
    #: (dimension, incoming_spelling, canonical_spelling) -> count
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
        return {
            "contract_version": self.contract_version,
            "n_conditions": self.n_conditions,
            "n_canonicalized": self.n_canonicalized,
            "n_failed": self.n_failed,
            "ok": self.ok,
            "failures": {k: list(v) for k, v in sorted(self.failures.items())},
            "alias_counts": {"|".join(k): v
                             for k, v in sorted(self.alias_counts.items())},
        }


def canonicalize_payload(payload: dict) -> tuple[dict, CanonicalizationReport]:
    """Return (canonicalized copy of payload, report).

    A condition that fails the contract is left EXACTLY AS THE MODEL WROTE IT in the
    returned payload and recorded in the report. It is never dropped and never repaired:
    downstream schema validation and compilation must still see -- and reject -- the real
    thing, so a contract failure stays visible as a failure rather than being silently
    laundered into a passing response.
    """
    report = CanonicalizationReport(contract_version=CONTRACT_VERSION)
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


# --------------------------------------------------------------------------------------
# Schema projection.
#
# schema_v2 imports these and does not type any enum of its own.
# --------------------------------------------------------------------------------------
def condition_schema() -> dict:
    """JSON-Schema for ONE condition, closed over the canonical contract.

    Shape note: the flat `{dimension, value, axis}` object is preserved deliberately.
    `firewall._FIELD_NAME_EXEMPT_PATHS` and `vocabulary.BAND_EXEMPT_PATH_SUFFIXES` both
    key on the literal path `conditions.value`; restructuring conditions into a per-family
    object would silently turn every cohort value into a `forbidden_field` violation and
    every `HIGH` band into a `level_grade`. Cross-field rules are expressed with `if/then`
    on the flat shape instead.
    """
    branches: list[dict] = []
    for dim in sorted(vocabulary.DIMENSIONS):
        values = list(dimension_values(dim))
        axes = list(dimension_axes(dim))
        # `type: object` is stated explicitly on every subschema so a checker that
        # dispatches on `type` (the project's own `validator._check`) applies object
        # semantics inside `if` / `then` / `not` rather than treating them as untyped
        # no-ops.
        then: dict = {"type": "object",
                      "properties": {"value": {"type": "string", "enum": values}}}
        if axes:
            # The compiler requires an axis here; so must the schema, or "profile without
            # axis" remains emittable (0/4 of V2's profile conditions carried one).
            then["required"] = ["axis"]
            then["properties"]["axis"] = {"type": "string", "enum": axes}
        else:
            # An axis on a dimension that has none is a contract error, not a no-op.
            then["not"] = {"type": "object", "required": ["axis"]}
        branches.append({
            "if": {"type": "object",
                   "properties": {"dimension": {"const": dim}},
                   "required": ["dimension"]},
            "then": then,
        })

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimension", "value"],
        "properties": {
            "dimension": {"type": "string", "enum": vocabulary.dimension_names()},
            # Closed at the union level, then narrowed per dimension by `allOf` below.
            # This is the field that was a free string in v1.
            "value": {"type": "string", "enum": list(all_canonical_values())},
            "axis": {"type": "string", "enum": list(all_canonical_axes())},
        },
        "allOf": branches,
    }


def contract_snapshot() -> dict:
    """Machine-readable contract, embedded in the prompt and in provenance."""
    return {
        "contract_version": CONTRACT_VERSION,
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "dimensions": {
            dim: {
                "values": list(dimension_values(dim)),
                "axes": list(dimension_axes(dim)),
                "axis_required": bool(dimension_axes(dim)),
                "context_source": vocabulary.DIMENSIONS[dim]["context_source"],
            }
            for dim in sorted(vocabulary.DIMENSIONS)
        },
        "alias_policy": (
            "Condition dimension, value and axis tokens are matched after folding case, "
            "hyphens and spaces. No other alias is accepted. Unresolvable tokens fail "
            "closed with a named reason."),
        "fail_closed_reasons": list(CONTRACT_REASONS),
    }
