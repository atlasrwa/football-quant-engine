"""V7.1 semantic intermediate representation (`v71_ir_v1`).

The deterministic bridge between a structured research hypothesis and a measurable query.
It exists because V7 had no such layer: a comparator was a *label* carried through to an
executor that implemented two of the nine declared semantics and fell through to a generic
subject-vs-subject contrast for the rest.

Construction rules
------------------
1. Built ONLY from structural fields plus the frozen `ontology`. Never from the hypothesis'
   prose `question`, never from an LLM, never from an outcome.
2. Fails CLOSED. Anything the structural fields cannot settle becomes an explicit status
   (`SEMANTICALLY_AMBIGUOUS`, `UNSUPPORTED_FILTER_DIMENSION`, ...) and is never measured.
3. A condition whose value is non-restrictive (`ANY`/`ALL`/null) is NOT a condition. It is
   recorded as `dropped_non_restrictive` so a degenerate comparator cannot masquerade as a
   conditioned one.
4. Every IR is round-trippable: `describe()` reconstructs the football question in words, and
   the golden round-trip suite asserts the reconstruction matches the intended meaning.

ZERO SPEND. No effects.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from src.research.hypothesis_v7 import canonical as V7C

from . import ontology as O

IR_VERSION = "v71_ir_v1"

#: Metric-name normalisation is REUSED verbatim from the frozen V7 canonicaliser rather than
#: restated, so the two experiments can never disagree about which strings denote the same
#: measured quantity. The map encodes only synonymy -- never anything about effects.
METRIC_SYNONYMS = dict(V7C.METRIC_SYNONYMS)


def normalise_metric(m):
    """`total_shots` -> `shots`. An unmapped name is passed through unchanged so the
    capability layer can report it as a NAMED unknown rather than silently dropping it."""
    if m is None:
        return None
    return METRIC_SYNONYMS.get(str(m).strip().lower(), str(m).strip().lower())

# ---- statuses --------------------------------------------------------------------------
OK = "OK"
SEMANTICALLY_AMBIGUOUS = "SEMANTICALLY_AMBIGUOUS"
UNSUPPORTED_FILTER_DIMENSION = "UNSUPPORTED_FILTER_DIMENSION"
UNKNOWN_COMPARATOR = "UNKNOWN_COMPARATOR"
INVALID_ROLE_BINDING = "INVALID_ROLE_BINDING"
MISSING_REQUIRED_CONDITION = "MISSING_REQUIRED_CONDITION"
MISSING_REQUIRED_SIMILARITY = "MISSING_REQUIRED_SIMILARITY"
UNSUPPORTED_TEMPORAL_RESOLUTION = "UNSUPPORTED_TEMPORAL_RESOLUTION"

#: Structural fields whose absence makes the football question unanswerable.
REQUIRED_SPEC_FIELDS = ("target_metrics", "subject", "side", "comparison")


@dataclass(frozen=True)
class Filter:
    """One restrictive condition on an entity's prior observations."""
    dimension: str
    value: str
    axis: str | None = None

    def key(self) -> tuple:
        return (self.dimension, self.axis, self.value)

    def describe(self) -> str:
        d = O.FILTER_DIMENSIONS.get(self.dimension, {})
        if self.dimension == "opponent_profile":
            return f"the opponent was in the {self.value} tercile of {self.axis}"
        if self.dimension == "historical_venue_conditioning":
            return f"the match was played {self.value}"
        if self.dimension == "competition":
            return "the match was in the same competition as the target fixture"
        return f"{self.dimension}={self.value}" if d else f"<unsupported {self.dimension}>"


@dataclass(frozen=True)
class Selector:
    """A fully specified set of prior observations. Cohort and baseline are both Selectors.

    Structural equality of two Selectors means they read the SAME observations with the SAME
    weighting -- which is exactly the degeneracy invariant `IDENTICAL_COHORT_BASELINE`.
    """
    entity_role: str
    perspective: str
    filters: tuple = ()
    window: str = "ALL_PRIOR"
    weighting: str = "UNIFORM"
    complement: bool = False       # read the COMPLEMENT of `filters` instead
    similar_to_opponent: str | None = None   # "SIMILAR" | "DISSIMILAR" | None

    def key(self) -> tuple:
        return (self.entity_role, self.perspective,
                tuple(sorted(f.key() for f in self.filters)),
                self.window, self.weighting, self.complement, self.similar_to_opponent)

    def describe(self) -> str:
        who = {"SUBJECT": "the subject's",
               "FIXTURE_OPPONENT": "the fixture opponent's",
               "COMPETITION_ENVIRONMENT": "the competition environment's"}[self.entity_role]
        what = ("production" if self.perspective == "FOR" else "concession")
        parts = [f"{who} {what}"]
        if self.window == "ALL_PRIOR":
            parts.append("over all prior matches")
        else:
            parts.append(f"over its last {self.window[1:]} prior matches")
        if self.similar_to_opponent == "SIMILAR":
            parts.append("against opponents similar to the fixture opponent")
        elif self.similar_to_opponent == "DISSIMILAR":
            parts.append("against opponents NOT similar to the fixture opponent")
        if self.filters:
            joined = " and ".join(f.describe() for f in self.filters)
            parts.append(("excluding matches where " if self.complement
                          else "restricted to matches where ") + joined)
        if self.weighting == "TIME_DECAY":
            parts.append("weighted toward recent matches")
        return ", ".join(parts)


@dataclass(frozen=True)
class IR:
    """The canonical semantic representation of one research hypothesis."""
    target_metrics: tuple
    subject: str
    perspective: str
    comparator: str
    cohort: Selector | None
    baseline: Selector | None
    temporal_resolution: str
    provider_requirements: tuple
    research_family: str | None
    status: str
    reasons: tuple = ()
    dropped_non_restrictive: tuple = ()
    unsupported_dimensions: tuple = ()

    # ---- identity ----
    def canonical(self) -> dict:
        return {
            "IR_VERSION": IR_VERSION,
            "TARGET_METRICS": list(self.target_metrics),
            "SUBJECT": self.subject,
            "PERSPECTIVE": self.perspective,
            "COMPARATOR": self.comparator,
            "COHORT": list(self.cohort.key()) if self.cohort else None,
            "BASELINE": list(self.baseline.key()) if self.baseline else None,
            "TEMPORAL_RESOLUTION": self.temporal_resolution,
            "PROVIDER_REQUIREMENTS": list(self.provider_requirements),
            "RESEARCH_FAMILY": self.research_family,
        }

    def ir_id(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"),
                          default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def describe(self) -> str:
        """Reconstruct the football question in words. Load-bearing: the golden round-trip
        suite asserts this matches the intended human-readable meaning."""
        if self.status != OK:
            return f"[{self.status}] {'; '.join(self.reasons)}"
        metrics = ", ".join(self.target_metrics)
        return (f"For {metrics}: does {self.cohort.describe()} differ from "
                f"{self.baseline.describe()}?")


# ---- condition normalisation -----------------------------------------------------------
def normalise_conditions(conditions) -> tuple:
    """Split raw conditions into (restrictive filters, dropped non-restrictive, unsupported).

    A raw condition may arrive as a dict or as the JSON string a canonical spec carries.
    """
    keep, dropped, unsupported = [], [], []
    seen = set()
    for c in conditions or []:
        d = c
        if isinstance(c, str):
            try:
                d = json.loads(c)
            except (ValueError, TypeError):
                d = {"dimension": c}
        if not isinstance(d, dict):
            unsupported.append(str(c))
            continue
        dim, val, axis = d.get("dimension"), d.get("value"), d.get("axis")
        if dim not in O.FILTER_DIMENSIONS:
            unsupported.append(f"{dim}={val}")
            continue
        if val in O.NON_RESTRICTIVE_VALUES:
            dropped.append(f"{dim}={val}")
            continue
        spec = O.FILTER_DIMENSIONS[dim]
        if val not in spec["values"]:
            unsupported.append(f"{dim}={val}")
            continue
        if "axis" in spec["needs"] and not axis:
            unsupported.append(f"{dim} without required axis")
            continue
        f = Filter(dimension=dim, value=val, axis=axis)
        # A logical condition repeated is still one restriction. Canonicalise rather than
        # carry the duplicate: two specs differing only by repetition are ONE question.
        if f.key() in seen:
            dropped.append(f"duplicate:{dim}={val}")
            continue
        seen.add(f.key())
        keep.append(f)
    keep.sort(key=lambda f: f.key())
    return tuple(keep), tuple(sorted(dropped)), tuple(sorted(unsupported))


def _resolve_filters(mode, filters):
    """Turn a binding's filter MODE into (filters, complement, similar_to_opponent)."""
    if mode == "SPEC_CONDITIONS":
        return filters, False, None
    if mode == "NONE":
        return (), False, None
    if mode == "COMPLEMENT_OF_SPEC_CONDITIONS":
        return filters, True, None
    if mode == "VENUE_OF_TARGET":
        return (Filter("historical_venue_conditioning", "TARGET_VENUE"),), False, None
    if mode == "VENUE_OF_TARGET_OPPONENT":
        return (Filter("historical_venue_conditioning", "TARGET_VENUE_OPPONENT"),), \
            False, None
    if mode == "SIMILAR_TO_FIXTURE_OPPONENT":
        return filters, False, "SIMILAR"
    if mode == "DISSIMILAR_TO_FIXTURE_OPPONENT":
        return filters, False, "DISSIMILAR"
    raise ValueError(f"unknown filter mode {mode!r}")


def _build_selector(bind, perspective, filters, window):
    f, comp, sim = _resolve_filters(bind["filters"], filters)
    w = bind["window"]
    return Selector(entity_role=bind["role"],
                    perspective=perspective if bind["perspective"] == "SPEC"
                    else bind["perspective"],
                    filters=f,
                    window=(window if w == "SPEC_WINDOW" else w),
                    weighting=bind["weighting"],
                    complement=comp,
                    similar_to_opponent=sim)


def build_ir(spec: dict, *, temporal_resolution: str = "MATCH") -> IR:
    """Deterministically bind a structured hypothesis to its semantic IR, or fail closed."""
    reasons = []
    metrics = tuple(sorted({normalise_metric(m)
                            for m in (spec.get("target_metrics") or []) if m}))
    subject = (spec.get("subject") or "").strip().upper() or None
    perspective = (spec.get("side") or "").strip().upper() or None
    comparator = (spec.get("comparison") or "").strip().upper() or None
    window = (spec.get("window") or "ALL_PRIOR").strip().upper()
    family = (spec.get("research_family") or "").strip().upper() or None
    caps = tuple(sorted(str(c) for c in (spec.get("required_capabilities") or [])))
    filters, dropped, unsupported = normalise_conditions(spec.get("conditions"))

    def fail(status, why):
        reasons.append(why)
        return IR(metrics, subject, perspective, comparator, None, None,
                  temporal_resolution, caps, family, status, tuple(reasons),
                  dropped, unsupported)

    for f in REQUIRED_SPEC_FIELDS:
        if not spec.get(f):
            return fail(SEMANTICALLY_AMBIGUOUS, f"structural field '{f}' is absent")
    if perspective not in O.PERSPECTIVES:
        return fail(INVALID_ROLE_BINDING, f"perspective {perspective!r} is not FOR/AGAINST")
    if subject not in ("HOME_TEAM", "AWAY_TEAM"):
        return fail(INVALID_ROLE_BINDING, f"subject {subject!r} is not a fixture role")
    if window not in O.WINDOWS:
        return fail(SEMANTICALLY_AMBIGUOUS, f"window {window!r} is outside the ontology")
    if temporal_resolution not in O.TEMPORAL_RESOLUTIONS:
        return fail(UNSUPPORTED_TEMPORAL_RESOLUTION,
                    f"temporal resolution {temporal_resolution!r} is outside the ontology")
    binding = O.COMPARATOR_BINDINGS.get(comparator)
    if binding is None:
        return fail(UNKNOWN_COMPARATOR,
                    f"comparator {comparator!r} has no frozen selector binding")
    if unsupported:
        return fail(UNSUPPORTED_FILTER_DIMENSION,
                    "condition dimensions this corpus cannot honour: " + ", ".join(unsupported))
    if binding.get("requires_conditions") and not filters:
        return fail(MISSING_REQUIRED_CONDITION,
                    f"{comparator} needs at least one restrictive condition to define a "
                    f"cohort distinct from its baseline")
    if binding.get("requires_similarity") and not caps:
        return fail(MISSING_REQUIRED_SIMILARITY,
                    f"{comparator} needs similarity dimensions it did not declare")
    req = binding.get("requires_filter")
    if req and not any(f.dimension == req["dimension"] and f.value == req["value"]
                       for f in filters):
        return fail(MISSING_REQUIRED_CONDITION,
                    f"{comparator} needs condition {req['dimension']}={req['value']}")

    cohort = _build_selector(binding["cohort"], perspective, filters, window)
    baseline = _build_selector(binding["baseline"], perspective, filters, window)
    return IR(metrics, subject, perspective, comparator, cohort, baseline,
              temporal_resolution, caps, family, OK, (), dropped, unsupported)


def version_stamp() -> dict:
    return {"ir_version": IR_VERSION, "ontology_version": O.ONTOLOGY_VERSION,
            "required_spec_fields": list(REQUIRED_SPEC_FIELDS),
            "statuses": [OK, SEMANTICALLY_AMBIGUOUS, UNSUPPORTED_FILTER_DIMENSION,
                         UNKNOWN_COMPARATOR, INVALID_ROLE_BINDING,
                         MISSING_REQUIRED_CONDITION, MISSING_REQUIRED_SIMILARITY,
                         UNSUPPORTED_TEMPORAL_RESOLUTION],
            "fails_closed": True, "reads_prose": False, "uses_llm": False,
            "reads_outcomes": False,
            "metric_synonyms_source": V7C.CANONICAL_VERSION,
            "n_metric_synonyms": len(METRIC_SYNONYMS),
            "non_restrictive_values_dropped": [v for v in O.NON_RESTRICTIVE_VALUES]}
