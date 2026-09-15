"""Availability-gated research ontology (`hypothesis_availability_v1`).

THE FAILURE THIS PREVENTS
-------------------------
V2 measured Sonnet against a research space the packets did not actually contain.
`half_score_state` and `period` were withheld by ALL TWELVE fixture manifests -- the
TheStatsAPI-adapted corpus carries no half-time goals -- so score-state research was
impossible, and Sonnet using it zero times was CORRECT BEHAVIOUR being read as shallowness.

The rule this module enforces in both directions:

    A dimension may be REWARDED only where it is genuinely offered, and may NEVER be
    PENALISED where it is not. Abstaining from an unavailable dimension is correct, and
    is excluded from the denominator rather than scored as a zero.

TWO KINDS OF "AVAILABLE", KEPT SEPARATE
---------------------------------------
They are not the same question and conflating them is how V2's matrix went wrong:

  * COMPILE-AVAILABLE -- the deterministic engine could measure it. Decided by
    `capability.CONTEXT_SOURCES` and the fixture manifest; this is what
    `query_plan.compile_hypothesis` checks.

  * EVIDENCE-SUPPORTED -- the model was actually SHOWN something that could motivate
    selecting it. Decided by the scopes present in `packet["evidence"]`.

A dimension can be compile-available and evidence-unsupported. Depth is only *expected*
where it is BOTH, because expecting a model to select a cohort it was shown no evidence
for is asking it to guess.

Recomputed against the frozen V2 packets, this produces a materially stricter -- and more
honest -- matrix than the V2 diagnosis document's §2 table:

  * every evidence item in all 52 materialized packets carries `scope.window = ALL_PRIOR`
    and `scope.venue = ALL`. There is NO second horizon and NO venue split in evidence.
    `SUBJECT_RECENT_VS_LONG_BASELINE` is therefore evidence-unsupported in all 12
    fixtures, not "Y" as the §2 matrix recorded it.
  * no evidence item carries a league-level scope, so `LEAGUE_ENVIRONMENT_BASELINE` is
    evidence-unsupported everywhere too.
  * formation coverage is only half the story: contrast is the other half. A subject whose
    recorded formations are all one family offers no interaction to measure even at 25%
    coverage.

CONTRAST
--------
A condition dimension with fewer than two observed levels for the subject cannot express a
comparison: "corners under BACK_FOUR vs corners overall" is the same cohort twice. Such a
dimension is reported AVAILABLE_LOW_CONTRAST -- selectable (the compiler accepts it, and a
model may have a reason) but excluded from the depth denominator, so neither using it nor
abstaining from it moves the depth reading.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import capability, condition_contract, vocabulary

AVAILABILITY_VERSION = "hypothesis_availability_v1"


# --------------------------------------------------------------------------------------
# Statuses
# --------------------------------------------------------------------------------------
AVAILABLE = "AVAILABLE"                              # compile-available + evidence-supported
LOW_CONTRAST = "AVAILABLE_LOW_CONTRAST"              # offered, but <2 observed levels
NO_EVIDENCE = "COMPILE_AVAILABLE_NO_EVIDENCE"        # engine could measure, packet shows none
WITHHELD = "WITHHELD"                                # manifest does not offer it at all

#: Statuses over which a depth metric may be computed. Everything else is EXCLUDED from
#: the denominator -- never counted as a zero.
EXPECTABLE_STATUSES = frozenset({AVAILABLE})

#: Fewer than this many observed levels means the dimension expresses no contrast.
MIN_LEVELS_FOR_CONTRAST = 2

#: Dimensions whose contrast is readable from the packet's `formation_distribution`.
_FORMATION_DIMENSIONS = ("own_formation_family", "opponent_formation_family")


@dataclass(frozen=True)
class DimensionAvailability:
    name: str
    status: str
    reason: str
    coverage_rate: Optional[float] = None
    observed_levels: tuple[str, ...] = ()
    #: For an axis-bearing dimension: the axes this FIXTURE can actually resolve -- an axis
    #: whose base metric is absent from the inventory or from the fixture's available
    #: metrics is not offered and not accepted. See `condition_contract.unresolvable_axes`.
    available_axes: tuple[str, ...] = ()
    withheld_axes: tuple[str, ...] = ()

    @property
    def expectable(self) -> bool:
        """True when depth on this dimension may be counted in a denominator."""
        return self.status in EXPECTABLE_STATUSES

    @property
    def selectable(self) -> bool:
        """True when the model is permitted to condition on it at all."""
        return self.status != WITHHELD

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "reason": self.reason,
                "coverage_rate": self.coverage_rate,
                "observed_levels": list(self.observed_levels),
                "available_axes": list(self.available_axes),
                "withheld_axes": list(self.withheld_axes),
                "expectable": self.expectable, "selectable": self.selectable}


@dataclass(frozen=True)
class ComparisonAvailability:
    name: str
    status: str
    reason: str

    @property
    def expectable(self) -> bool:
        return self.status in EXPECTABLE_STATUSES

    @property
    def selectable(self) -> bool:
        return self.status != WITHHELD

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "reason": self.reason,
                "expectable": self.expectable, "selectable": self.selectable}


@dataclass
class ResearchOntology:
    """What THIS fixture's packet actually supports being asked about."""

    availability_version: str
    fixture_id: str
    dimensions: dict = field(default_factory=dict)      # name -> DimensionAvailability
    comparisons: dict = field(default_factory=dict)     # name -> ComparisonAvailability
    evidence_windows: tuple[str, ...] = ()
    evidence_venues: tuple[str, ...] = ()
    evidence_subjects: tuple[str, ...] = ()

    # -- selection surface (what the model may choose from) ----------------------------
    def selectable_dimensions(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, d in self.dimensions.items() if d.selectable))

    def withheld_dimensions(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, d in self.dimensions.items() if not d.selectable))

    def selectable_comparisons(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, c in self.comparisons.items() if c.selectable))

    # -- measurement surface (what depth may be scored over) ---------------------------
    def expectable_dimensions(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, d in self.dimensions.items() if d.expectable))

    def expectable_comparisons(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, c in self.comparisons.items() if c.expectable))

    def is_expectable(self, dimension: str) -> bool:
        d = self.dimensions.get(dimension)
        return bool(d and d.expectable)

    def to_dict(self) -> dict:
        return {
            "availability_version": self.availability_version,
            "fixture_id": self.fixture_id,
            "dimensions": {k: v.to_dict() for k, v in sorted(self.dimensions.items())},
            "comparisons": {k: v.to_dict() for k, v in sorted(self.comparisons.items())},
            "evidence_windows": list(self.evidence_windows),
            "evidence_venues": list(self.evidence_venues),
            "evidence_subjects": list(self.evidence_subjects),
            "selectable_dimensions": list(self.selectable_dimensions()),
            "withheld_dimensions": list(self.withheld_dimensions()),
            "expectable_dimensions": list(self.expectable_dimensions()),
            "selectable_comparisons": list(self.selectable_comparisons()),
            "expectable_comparisons": list(self.expectable_comparisons()),
        }


# --------------------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------------------
def _evidence_scopes(packet: dict) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    windows: set[str] = set()
    venues: set[str] = set()
    subjects: set[str] = set()
    for item in packet.get("evidence") or []:
        scope = (item or {}).get("scope") or {}
        for key, sink in (("window", windows), ("venue", venues), ("subject", subjects)):
            v = scope.get(key)
            if isinstance(v, str):
                sink.add(v)
    return tuple(sorted(windows)), tuple(sorted(venues)), tuple(sorted(subjects))


def resolve_axes(dimension: str, available_metrics: Iterable[str]) -> tuple[tuple, tuple]:
    """(available_axes, withheld_axes) for one dimension against a fixture's metric set.

    An axis is offered only when BOTH hold:
      * its base metric exists in `capability.METRICS` -- this is what excludes the two
        broken vocabulary entries `shots_for` / `shots_against`, which name a `shots`
        metric the inventory does not have; and
      * that base metric is available for THIS fixture.

    Gating happens twice, deliberately: the axis is absent from the exposed condition
    space (the model never sees it) AND rejected at validation if emitted anyway. Exposure
    alone is not a contract.
    """
    declared = condition_contract.dimension_axes(dimension)
    if not declared:
        return (), ()
    metrics = set(available_metrics or ())
    ok, bad = [], []
    for axis in declared:
        base = condition_contract.axis_base_metric(axis)
        if base and capability.metric(base) is not None and base in metrics:
            ok.append(axis)
        else:
            bad.append(axis)
    return tuple(ok), tuple(bad)


def _formation_levels(packet: dict) -> tuple[str, ...]:
    """Observed formation families, counted per SUBJECT.

    Contrast is a within-subject property: "does THIS team behave differently when it
    lines up with three at the back" needs this team to have done both. A fixture where
    each side played exactly one family all season offers none, however good the coverage
    rate looks.
    """
    best: tuple[str, ...] = ()
    for _subject, dist in sorted((packet.get("formation_distribution") or {}).items()):
        if not isinstance(dist, dict):
            continue
        levels = tuple(sorted(k for k, n in dist.items() if n))
        if len(levels) > len(best):
            best = levels
    return best


def build_ontology(packet: dict,
                   manifest: Optional[capability.FixtureCapabilityManifest] = None
                   ) -> ResearchOntology:
    """Derive the gated ontology for one fixture packet.

    Reads only the packet and its manifest. Declares no enum of its own: the dimension and
    comparison names come from `vocabulary`, mediated by `condition_contract`.
    """
    fixture_id = packet.get("fixture_id", "")
    cm = packet.get("capability_manifest") or {}
    offered = set(manifest.available_dimensions if manifest is not None
                  else (cm.get("available_dimensions") or ()))
    coverage = dict((manifest.coverage if manifest is not None else cm.get("coverage")) or {})
    notes = tuple((manifest.notes if manifest is not None else cm.get("notes")) or ())
    windows, venues, subjects = _evidence_scopes(packet)
    formation_levels = _formation_levels(packet)

    available_metrics = list(manifest.available_metrics if manifest is not None
                             else (cm.get("available_metrics") or ()))

    dims: dict[str, DimensionAvailability] = {}
    for name in sorted(vocabulary.DIMENSIONS):
        cov = (coverage.get(name) or {}).get("coverage_rate")
        ok_axes, bad_axes = resolve_axes(name, available_metrics)
        if name not in offered:
            src = vocabulary.DIMENSIONS[name]["context_source"]
            reason = (f"the fixture manifest does not offer {name!r} "
                      f"(context source {src!r}); "
                      + ("; ".join(notes) if notes else "no coverage for this fixture"))
            dims[name] = DimensionAvailability(name, WITHHELD, reason, cov,
                                               available_axes=(), withheld_axes=bad_axes)
            continue

        if name in _FORMATION_DIMENSIONS:
            if len(formation_levels) < MIN_LEVELS_FOR_CONTRAST:
                dims[name] = DimensionAvailability(
                    name, LOW_CONTRAST,
                    f"offered at coverage {cov}, but only "
                    f"{len(formation_levels)} formation family/families were observed "
                    f"({list(formation_levels)}); a condition on it compares a cohort "
                    f"with itself",
                    cov, formation_levels, ok_axes, bad_axes)
                continue
            dims[name] = DimensionAvailability(
                name, AVAILABLE,
                f"offered at coverage {cov} with {len(formation_levels)} observed "
                f"families {list(formation_levels)}",
                cov, formation_levels, ok_axes, bad_axes)
            continue

        if name == "venue":
            # The cohort engine can always split by venue; whether the model was SHOWN a
            # venue split is a separate question, and only the first one gates selection.
            dims[name] = DimensionAvailability(
                name, AVAILABLE,
                "offered by the manifest; venue is a property of every cohort fixture",
                cov, ("HOME", "AWAY"), ok_axes, bad_axes)
            continue

        if ok_axes or not condition_contract.dimension_axes(name):
            dims[name] = DimensionAvailability(
                name, AVAILABLE, f"offered by the fixture manifest (coverage {cov})",
                cov, (), ok_axes, bad_axes)
        else:
            # An axis-bearing dimension with NO resolvable axis cannot express a cohort.
            dims[name] = DimensionAvailability(
                name, WITHHELD,
                f"{name!r} requires an axis, and none of its declared axes "
                f"{list(bad_axes)} resolves to a metric available for this fixture",
                cov, (), (), bad_axes)

    comps: dict[str, ComparisonAvailability] = {}
    has_two_horizons = len(windows) >= 2
    has_league_scope = any(s not in ("HOME", "AWAY") for s in subjects)
    for name in vocabulary.COMPARISONS:
        if name == "SUBJECT_RECENT_VS_LONG_BASELINE":
            comps[name] = ComparisonAvailability(
                name, AVAILABLE if has_two_horizons else NO_EVIDENCE,
                (f"evidence spans horizons {list(windows)}" if has_two_horizons else
                 f"the packet supplies exactly one horizon {list(windows)}; a "
                 f"recent-vs-long comparison needs both a short and a long window in "
                 f"evidence before it can be selected on evidence"))
        elif name == "LEAGUE_ENVIRONMENT_BASELINE":
            comps[name] = ComparisonAvailability(
                name, AVAILABLE if has_league_scope else NO_EVIDENCE,
                (f"league-scope evidence present" if has_league_scope else
                 f"no evidence item carries a league-level scope (subjects seen: "
                 f"{list(subjects)})"))
        elif name == "SUBJECT_VENUE_BASELINE":
            offered_venue = dims["venue"].selectable
            split = any(v not in ("ALL",) for v in venues)
            comps[name] = ComparisonAvailability(
                name,
                AVAILABLE if (offered_venue and split) else
                (NO_EVIDENCE if offered_venue else WITHHELD),
                ("venue-split evidence present" if split else
                 f"venue is compile-available but every evidence item is scoped "
                 f"venue={list(venues)}, so no venue split was shown"))
        elif name == "SUBJECT_COMPETITION_BASELINE":
            ok = dims["competition"].selectable
            comps[name] = ComparisonAvailability(
                name, AVAILABLE if ok else WITHHELD,
                "competition dimension offered" if ok else "competition withheld")
        else:
            comps[name] = ComparisonAvailability(
                name, AVAILABLE,
                "an unconditional subject baseline needs no extra context")

    return ResearchOntology(
        availability_version=AVAILABILITY_VERSION,
        fixture_id=fixture_id, dimensions=dims, comparisons=comps,
        evidence_windows=windows, evidence_venues=venues, evidence_subjects=subjects)


# --------------------------------------------------------------------------------------
# Exposure: what the model is shown it may select.
# --------------------------------------------------------------------------------------
def fixture_condition_space(ontology: ResearchOntology) -> dict:
    """The per-fixture selection surface, for the prompt.

    Deliberately NOT a per-fixture JSON schema: `prompt.prompt_content_hash()` and the
    prespend manifests bind a single schema hash across every control, and a schema that
    varied by fixture would break that provenance check. Selection is exposed in the
    prompt and enforced by the manifest check already inside
    `query_plan.compile_hypothesis` and `validator._validate_one`.

    Withheld dimensions are simply ABSENT. They are not listed as "do not use", because
    naming a dimension is itself a nudge -- the model should not learn that score-state
    exists as a thing worth mentioning on a fixture that cannot support it.
    """
    out: dict[str, dict] = {}
    for name in ontology.selectable_dimensions():
        d = ontology.dimensions[name]
        entry: dict = {"values": list(condition_contract.dimension_values(name))}
        if condition_contract.dimension_axes(name):
            entry["axis_required"] = True
            # the GATED list, never the raw vocabulary tuple
            entry["axes"] = list(d.available_axes)
        if d.status == LOW_CONTRAST:
            entry["contrast"] = "LOW"
            entry["observed_levels"] = list(d.observed_levels)
        out[name] = entry
    return {
        "availability_version": AVAILABILITY_VERSION,
        "fixture_id": ontology.fixture_id,
        "dimensions": out,
        "comparisons": list(ontology.selectable_comparisons()),
    }


# --------------------------------------------------------------------------------------
# Measurement: depth and restraint, both gated.
# --------------------------------------------------------------------------------------
def depth_utilization(intents: list, ontology: ResearchOntology) -> dict:
    """Per-dimension utilization, with unavailable dimensions EXCLUDED, not zeroed.

    `intents` are `normalize.Intent` objects (or their dicts). The returned record says,
    for every dimension, whether it counted at all -- so a reader can never mistake
    "excluded because impossible" for "available and unused".
    """
    rows = [i.to_dict() if hasattr(i, "to_dict") else i for i in intents]
    used = Counter()
    for r in rows:
        for c in r.get("conditions") or []:
            used[c.get("dimension")] += 1

    out: dict[str, dict] = {}
    for name, d in sorted(ontology.dimensions.items()):
        out[name] = {
            "status": d.status,
            "counted_in_denominator": d.expectable,
            "n_intents_using": used.get(name, 0),
            "utilization": (round(used.get(name, 0) / len(rows), 4)
                            if (d.expectable and rows) else None),
        }
    return out


def comparison_utilization(intents: list, ontology: ResearchOntology) -> dict:
    rows = [i.to_dict() if hasattr(i, "to_dict") else i for i in intents]
    used = Counter(r.get("comparison") for r in rows)
    return {
        name: {
            "status": c.status,
            "counted_in_denominator": c.expectable,
            "n_intents_using": used.get(name, 0),
            "utilization": (round(used.get(name, 0) / len(rows), 4)
                            if (c.expectable and rows) else None),
        }
        for name, c in sorted(ontology.comparisons.items())
    }


def restraint_profile(payload: dict, ontology: ResearchOntology) -> dict:
    """Restraint, measured on the RAW hypotheses rather than normalized intents.

    Normalization drops `ANY`-valued conditions, which is correct for intent identity but
    would hide exactly the padding this measures: a hypothesis dressed up with
    `venue=ANY` looks conditional and restricts nothing.
    """
    n_conditions = 0
    n_any_padding = 0
    n_on_withheld = 0
    n_hyps = 0
    n_conditional = 0
    n_interaction = 0
    n_justified_interaction = 0
    withheld = set(ontology.withheld_dimensions())

    for h in payload.get("hypotheses") or []:
        if not isinstance(h, dict):
            continue
        n_hyps += 1
        conds = [c for c in (h.get("conditions") or []) if isinstance(c, dict)]
        restricting = []
        for c in conds:
            n_conditions += 1
            dim = c.get("dimension")
            val = c.get("value")
            if isinstance(val, str) and condition_contract.fold(val) == "ANY":
                n_any_padding += 1
                continue
            if dim in withheld:
                n_on_withheld += 1
            restricting.append(c)
        if restricting:
            n_conditional += 1
        if len(restricting) >= 2:
            n_interaction += 1
            if all(ontology.dimensions.get(c.get("dimension"))
                   and ontology.dimensions[c.get("dimension")].expectable
                   for c in restricting):
                n_justified_interaction += 1

    return {
        "availability_version": AVAILABILITY_VERSION,
        "n_hypotheses": n_hyps,
        "n_conditions": n_conditions,
        "conditional_rate": round(n_conditional / n_hyps, 4) if n_hyps else 0.0,
        "interaction_rate": round(n_interaction / n_hyps, 4) if n_hyps else 0.0,
        "justified_interaction_rate": (round(n_justified_interaction / n_hyps, 4)
                                       if n_hyps else 0.0),
        # --- gratuitous complexity: depth that measures nothing ----------------------
        "any_padding_conditions": n_any_padding,
        "conditions_on_withheld_dimensions": n_on_withheld,
        "gratuitous_condition_rate": (round((n_any_padding + n_on_withheld) / n_conditions, 4)
                                      if n_conditions else 0.0),
    }


def version_stamp() -> dict:
    return {
        "availability_version": AVAILABILITY_VERSION,
        "vocabulary_version": vocabulary.VOCABULARY_VERSION,
        "condition_contract_version": condition_contract.CONTRACT_VERSION,
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
        "statuses": [AVAILABLE, LOW_CONTRAST, NO_EVIDENCE, WITHHELD],
        "expectable_statuses": sorted(EXPECTABLE_STATUSES),
    }


def unavailable_axis_reasons(hypothesis: dict, ontology: ResearchOntology) -> list[str]:
    """Reasons this hypothesis names an axis the fixture cannot resolve.

    The second of the two gates. Exposure keeps a broken axis out of the model's sight;
    this keeps it out of the research record if the model writes one anyway.
    """
    out: list[str] = []
    for c in hypothesis.get("conditions") or []:
        if not isinstance(c, dict):
            continue
        axis = c.get("axis")
        if axis is None:
            continue
        dim = c.get("dimension")
        d = ontology.dimensions.get(dim)
        if d is None:
            continue
        if axis not in d.available_axes:
            base = condition_contract.axis_base_metric(axis) if isinstance(axis, str) else None
            out.append(
                f"condition on {dim!r} names axis {axis!r}, which this fixture cannot "
                f"resolve: base metric {base!r} is "
                + ("not in the capability inventory"
                   if not base or capability.metric(base) is None
                   else "not available for this fixture")
                + f"; available axes here: {list(d.available_axes)}")
    return out
