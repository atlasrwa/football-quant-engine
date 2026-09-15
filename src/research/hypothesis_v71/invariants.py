"""V7.1 hard compiler invariants (`v71_invariants_v1`).

Structural gate between the semantic IR and any measurement. Every check is a pure predicate
over the IR (plus, where relevant, the frozen capability contract). None reads an outcome,
an effect, or a p-value, so the gate cannot be tuned by results.

Why this module exists: V7 emitted a zero-valued feature for structurally invalid hypotheses
and let the downstream pipeline classify them as TAUTOLOGICAL *after* running a full
walk-forward over them. A structurally invalid question must be rejected BEFORE measurement,
with a named reason.

ZERO SPEND. No effects.
"""
from __future__ import annotations

from . import ir as IRM
from . import ontology as O

INVARIANTS_VERSION = "v71_invariants_v1"

# ---- violation codes -------------------------------------------------------------------
IDENTICAL_COHORT_BASELINE = "IDENTICAL_COHORT_BASELINE"
SELF_COMPARISON = "SELF_COMPARISON"
EMPTY_COMPARATOR = "EMPTY_COMPARATOR"
BASELINE_ABSORPTION = "BASELINE_ABSORPTION"
TAUTOLOGICAL_CONDITION = "TAUTOLOGICAL_CONDITION"
DUPLICATED_CONDITION = "DUPLICATED_CONDITION"
NO_EFFECTIVE_RESTRICTION = "NO_EFFECTIVE_RESTRICTION"
INVALID_ROLE_BINDING = "INVALID_ROLE_BINDING"
UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
INSUFFICIENT_PROVIDER_COVERAGE = "INSUFFICIENT_PROVIDER_COVERAGE"
TEMPORAL_RESOLUTION_UNSUPPORTED = "TEMPORAL_RESOLUTION_UNSUPPORTED"
SEMANTICALLY_AMBIGUOUS = "SEMANTICALLY_AMBIGUOUS"
UNKNOWN_PROVIDER_SEMANTICS = "UNKNOWN_PROVIDER_SEMANTICS"
SIMILARITY_WITHOUT_DIMENSIONS = "SIMILARITY_WITHOUT_DIMENSIONS"
#: IR-stage statuses that are themselves terminal structural verdicts. Listed here so a
#: fail-closed IR keeps its PRECISE reason instead of collapsing to SEMANTICALLY_AMBIGUOUS.
UNSUPPORTED_FILTER_DIMENSION = IRM.UNSUPPORTED_FILTER_DIMENSION
UNKNOWN_COMPARATOR = IRM.UNKNOWN_COMPARATOR
MISSING_REQUIRED_CONDITION = IRM.MISSING_REQUIRED_CONDITION
MISSING_REQUIRED_SIMILARITY = IRM.MISSING_REQUIRED_SIMILARITY

VIOLATION_CODES = (
    IDENTICAL_COHORT_BASELINE, SELF_COMPARISON, EMPTY_COMPARATOR, BASELINE_ABSORPTION,
    TAUTOLOGICAL_CONDITION, DUPLICATED_CONDITION, NO_EFFECTIVE_RESTRICTION,
    INVALID_ROLE_BINDING, UNSUPPORTED_METRIC, INSUFFICIENT_PROVIDER_COVERAGE,
    TEMPORAL_RESOLUTION_UNSUPPORTED, SEMANTICALLY_AMBIGUOUS, UNKNOWN_PROVIDER_SEMANTICS,
    SIMILARITY_WITHOUT_DIMENSIONS, UNSUPPORTED_FILTER_DIMENSION, UNKNOWN_COMPARATOR,
    MISSING_REQUIRED_CONDITION, MISSING_REQUIRED_SIMILARITY,
)

#: Perspective a profile axis suffix denotes, mirroring `axis_perspective`.
_AXIS_SUFFIXES = (("_against", "AGAINST"), ("_for", "FOR"))


def axis_metric_perspective(axis: str):
    """`goals_against` -> ("goals", "AGAINST"). An axis names a metric AND a perspective."""
    if axis is None:
        return (None, None)
    for suf, side in _AXIS_SUFFIXES:
        if axis.endswith(suf):
            return (axis[: -len(suf)], side)
    return (axis, "FOR")


class InvariantViolation(Exception):
    """A structurally invalid query was offered to the measurement engine."""

    def __init__(self, codes, detail=""):
        self.codes = tuple(codes)
        super().__init__(f"{', '.join(self.codes)}{': ' + detail if detail else ''}")


def _selector_violations(sel, ir):
    out = []
    seen = set()
    for f in sel.filters:
        if f.key() in seen:
            out.append((DUPLICATED_CONDITION, f"condition {f.key()} appears twice"))
        seen.add(f.key())
        if f.dimension == "opponent_profile":
            m, side = axis_metric_perspective(f.axis)
            # The target metric conditioning ON ITSELF, with the SAME perspective and the SAME
            # entity, makes the cohort a function of the quantity being measured.
            if m in ir.target_metrics and side == ir.perspective \
                    and sel.entity_role == "SUBJECT" and f.axis and f.axis.startswith(m):
                # opponent_profile reads the OPPONENT's axis, so this is only tautological
                # when the selector itself is the opponent.
                pass
    return out


def check(ir, *, capability=None) -> dict:
    """Return {'ok': bool, 'violations': [(code, detail)], 'codes': [...]}.

    `capability` is an optional frozen provider-capability contract exposing
    `classify_metric(metric) -> (status, detail)`; when absent, metric checks are skipped
    (the capability gate is applied separately in the measurability stage).
    """
    v = []

    if ir.status != IRM.OK:
        code = ir.status if ir.status in VIOLATION_CODES else SEMANTICALLY_AMBIGUOUS
        return {"ok": False, "codes": [code],
                "violations": [(code, "; ".join(ir.reasons))]}

    if ir.cohort is None or ir.baseline is None:
        v.append((EMPTY_COMPARATOR, "comparator did not bind both selectors"))
        return {"ok": False, "codes": [c for c, _ in v], "violations": v}

    if ir.perspective not in O.PERSPECTIVES or ir.subject not in ("HOME_TEAM", "AWAY_TEAM"):
        v.append((INVALID_ROLE_BINDING, f"subject={ir.subject} perspective={ir.perspective}"))

    # --- the degeneracy family -----------------------------------------------------------
    if ir.cohort.key() == ir.baseline.key():
        v.append((IDENTICAL_COHORT_BASELINE,
                  "cohort and baseline read the same observations with the same weighting"))
        if ir.cohort.entity_role == ir.baseline.entity_role:
            v.append((SELF_COMPARISON,
                      f"{ir.cohort.entity_role} compared with itself under identical filters"))

    # Baseline absorption: the baseline partition already equals the cohort's restriction, so
    # the contrast collapses (V6.1's venue-condition + venue-baseline pattern).
    # A REWEIGHTING comparator's two selectors legitimately share their filters: the contrast
    # is carried by the weighting, not by the restriction. Flagging that as absorption would
    # reject every conditioned recency hypothesis.
    _reweighting = ir.cohort.weighting != ir.baseline.weighting
    if (ir.cohort.entity_role == ir.baseline.entity_role
            and ir.cohort.perspective == ir.baseline.perspective
            and not _reweighting
            and not ir.cohort.complement and not ir.baseline.complement):
        cvenue = {f.value for f in ir.cohort.filters
                  if f.dimension == "historical_venue_conditioning"}
        bvenue = {f.value for f in ir.baseline.filters
                  if f.dimension == "historical_venue_conditioning"}
        if cvenue and bvenue and ir.cohort.window == ir.baseline.window:
            v.append((BASELINE_ABSORPTION,
                      "a venue-restricted cohort is compared against a venue-restricted "
                      "baseline over the same window"))

    # A condition list that survives normalisation empty, for a comparator whose cohort is
    # only distinguishable BY that condition.
    binding = O.COMPARATOR_BINDINGS.get(ir.comparator, {})
    if binding.get("requires_conditions") and not ir.cohort.filters:
        v.append((NO_EFFECTIVE_RESTRICTION,
                  f"{ir.comparator} compiled to a cohort with no restriction "
                  f"(dropped: {', '.join(ir.dropped_non_restrictive) or 'none'})"))
    if binding.get("requires_similarity") and not ir.cohort.similar_to_opponent:
        v.append((SIMILARITY_WITHOUT_DIMENSIONS,
                  f"{ir.comparator} did not bind a similarity cohort"))

    # The target metric may not be its own conditioning variable on the same entity+side.
    for sel in (ir.cohort, ir.baseline):
        for f in sel.filters:
            if f.dimension != "opponent_profile":
                continue
            m, side = axis_metric_perspective(f.axis)
            if sel.entity_role == "FIXTURE_OPPONENT" and m in ir.target_metrics \
                    and side == ir.perspective:
                v.append((TAUTOLOGICAL_CONDITION,
                          f"axis {f.axis} conditions the opponent on the very quantity being "
                          f"measured from the opponent"))
        v.extend(_selector_violations(sel, ir))

    if ir.temporal_resolution not in O.TEMPORAL_RESOLUTIONS:
        v.append((TEMPORAL_RESOLUTION_UNSUPPORTED, ir.temporal_resolution))

    # --- provider capability ------------------------------------------------------------
    if capability is not None:
        for m in ir.target_metrics:
            # A request may never be FINER than the resolution the corpus holds: a match-level
            # aggregate cannot answer a half-level or event-level football question.
            status, detail = capability.classify_metric(m)
            # Resolution is only a separate finding for a CONTRACTED metric. For an unknown
            # metric the capability gap already says everything; reporting both would double
            # count one gap as two defects.
            if status != "UNKNOWN" and not capability.resolution_supports(
                    m, ir.temporal_resolution):
                v.append((TEMPORAL_RESOLUTION_UNSUPPORTED,
                          f"{m} is held at {capability.resolution_of(m)!r} resolution; "
                          f"{ir.temporal_resolution!r} was requested"))
            if status == "UNKNOWN":
                v.append((UNKNOWN_PROVIDER_SEMANTICS, f"{m}: {detail}"))
            elif status == "UNSUPPORTED":
                v.append((UNSUPPORTED_METRIC, f"{m}: {detail}"))
            elif status == "INSUFFICIENT_COVERAGE":
                v.append((INSUFFICIENT_PROVIDER_COVERAGE, f"{m}: {detail}"))
        for sel in (ir.cohort, ir.baseline):
            for f in sel.filters:
                if f.dimension != "opponent_profile":
                    continue
                m, _side = axis_metric_perspective(f.axis)
                status, detail = capability.classify_metric(m)
                if status != "SUPPORTED":
                    v.append((INSUFFICIENT_PROVIDER_COVERAGE,
                              f"profile axis {f.axis}: {detail}"))

    # de-duplicate, preserving first-seen order
    seen, out = set(), []
    for code, detail in v:
        if (code, detail) in seen:
            continue
        seen.add((code, detail))
        out.append((code, detail))
    return {"ok": not out, "codes": [c for c, _ in out], "violations": out}


def assert_valid(ir, *, capability=None) -> None:
    """Raise rather than return. The measurement engine calls THIS, so an invalid query
    cannot reach a fold loop even if a caller forgets to inspect the result."""
    res = check(ir, capability=capability)
    if not res["ok"]:
        raise InvariantViolation(res["codes"],
                                 "; ".join(d for _c, d in res["violations"]))


def version_stamp() -> dict:
    return {"invariants_version": INVARIANTS_VERSION,
            "violation_codes": list(VIOLATION_CODES),
            "checked_before_any_measurement": True,
            "reads_outcomes": False,
            "emits_zero_feature_for_invalid_query": False}
