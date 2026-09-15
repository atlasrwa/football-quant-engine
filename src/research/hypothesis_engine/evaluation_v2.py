"""Hypothesis-generation evaluation battery v2 (`hypothesis_evaluation_v2`).

THREE AXES, MEASURED SEPARATELY, NEVER AVERAGED
-----------------------------------------------
V2 produced one pass/fail verdict in which a compliance failure and a depth failure were
indistinguishable, and in which a correct abstention scored the same as a wrong answer.
v2 of the battery keeps them apart:

  DISCIPLINE  hard gates. Same philosophy, same thresholds, same no-salvage rule.
  DEPTH       REPORTED, never gated, and every quantity availability-gated so an
              unavailable dimension is EXCLUDED from the denominator, never zeroed.
  RESTRAINT   REPORTED. Gratuitous complexity lowers it, so "always emit an interaction"
              is not a winning strategy and the prompt cannot be gamed into circularity.

THE THRESHOLDS ARE NOT MOVED
----------------------------
`evaluation.THRESHOLDS` is reused verbatim. Nothing here lowers a bar. Two DEFINITIONS are
corrected, both of which were scoring instrument defects rather than bars:

  1. ABSTENTION. v1 computed `n_abstentions / n_hypotheses` and returned 0.0 for an empty
     list, so the IDEAL response to a starved packet -- `{"hypotheses": []}` -- scored as
     the worst possible abstention. An empty hypothesis set is now FULL abstention (1.0).

  2. INVARIANCE. v1 compared identity-swap and irrelevant-field intent Jaccard against an
     ABSOLUTE 0.80, a bar the generator could not clear against ITSELF: V2's measured
     same-input repeatability floor was 0.333. An invariance gate above the noise floor
     measures sampling noise, not identity sensitivity. v2 expresses invariance RELATIVE
     to the measured same-input floor: an alias swap must not move intent materially more
     than re-running the identical input does.

Both corrections make the instrument measure what it claims to measure. Neither makes a
failing response pass: a model that genuinely invents on starved packets still fails
abstention, and a model whose intent collapses under an alias swap still fails invariance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import (availability, capability, evaluation, firewall_v2, lifecycle, normalize,
               query_plan, schema_v2, validator_v2, vocabulary)

EVALUATION_VERSION = "hypothesis_evaluation_v2"

#: Reused verbatim. No bar is moved.
THRESHOLDS = dict(evaluation.THRESHOLDS)

#: Invariance is judged RELATIVE to the measured same-input repeatability floor: an alias
#: swap or an irrelevant-field edit may not move intent more than this fraction below what
#: re-running the identical input already moves it.
INVARIANCE_FLOOR_RATIO = 0.90


# --------------------------------------------------------------------------------------
# Corrected definitions
# --------------------------------------------------------------------------------------
def abstention_quality(payload: dict) -> float:
    """Fraction of the response that is an abstention. An EMPTY SET IS FULL ABSTENTION.

    v1 returned 0.0 here, scoring the single most correct answer to an unanswerable packet
    as the single worst. That is the defect, not the bar.
    """
    if not isinstance(payload, dict):
        return 0.0
    hyps = payload.get("hypotheses")
    if hyps is None:
        return 0.0
    if len(hyps) == 0:
        return 1.0
    n_abst = sum(1 for h in hyps
                 if isinstance(h, dict)
                 and h.get("sufficiency") == vocabulary.SUFFICIENCY[1])
    return n_abst / len(hyps)


def abstained(payload: dict, threshold: float = 0.5) -> bool:
    return abstention_quality(payload) >= threshold


def relative_invariance(observed_median: Optional[float],
                        repeatability_floor: Optional[float]) -> dict:
    """Express an invariance reading against the generator's own same-input noise floor.

    Returns `passed=None` when the floor was not measured -- "we did not measure it" must
    stay visibly distinct from "it failed", which is the eligibility-core discipline this
    package inherits.
    """
    if observed_median is None or repeatability_floor is None:
        return {"observed_median": observed_median,
                "repeatability_floor": repeatability_floor,
                "ratio": None, "required_ratio": INVARIANCE_FLOOR_RATIO,
                "passed": None,
                "note": "not measured; an unmeasured control is not a pass"}
    if repeatability_floor <= 0.0:
        return {"observed_median": observed_median,
                "repeatability_floor": repeatability_floor,
                "ratio": None, "required_ratio": INVARIANCE_FLOOR_RATIO,
                "passed": None,
                "note": ("the generator does not reproduce its own intent on the identical "
                         "input at all, so no invariance claim is measurable above noise")}
    ratio = observed_median / repeatability_floor
    return {"observed_median": round(observed_median, 4),
            "repeatability_floor": round(repeatability_floor, 4),
            "ratio": round(ratio, 4),
            "required_ratio": INVARIANCE_FLOOR_RATIO,
            "passed": ratio >= INVARIANCE_FLOOR_RATIO,
            "note": ("invariance is judged against the measured same-input floor, not an "
                     "absolute Jaccard the generator cannot reach against itself")}


# --------------------------------------------------------------------------------------
# Per-fixture scoring
# --------------------------------------------------------------------------------------
@dataclass
class FixtureScoreV2:
    fixture_id: str
    schema_valid: bool
    whole_response_failure: Optional[str] = None
    n_hypotheses: int = 0
    n_accepted: int = 0
    n_compilable: int = 0
    n_plans: int = 0
    abstention_quality: float = 0.0
    firewall_classes: dict = field(default_factory=dict)
    n_blocking_violations: int = 0
    n_suppressed_violations: int = 0
    unavailable_requests: int = 0
    metric_richness: int = 0
    family_richness: int = 0
    redundancy_rate: float = 0.0
    distinct_intents: int = 0
    failure_breakdown: dict = field(default_factory=dict)
    #: reported, availability-gated -- never folded into a gate
    depth: dict = field(default_factory=dict)
    restraint: dict = field(default_factory=dict)
    ontology: dict = field(default_factory=dict)
    canonicalization: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["evaluation_version"] = EVALUATION_VERSION
        return d


def score_response(
    payload,
    *,
    packet: dict,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
) -> FixtureScoreV2:
    """Deterministically score one response. No model, no judgement, no outcome."""
    fixture_id = packet.get("fixture_id", "")
    ontology = availability.build_ontology(packet, manifest)

    result = validator_v2.validate(
        payload, packet=packet, manifest=manifest,
        expected_packet_hash=packet.get("packet_hash"),
        expected_fixture_id=fixture_id)

    canon = result.canonical_payload if result.canonical_payload is not None else payload
    findings = result.firewall_findings
    classes = firewall_v2.classification_counts(findings)

    base = dict(
        fixture_id=fixture_id,
        schema_valid=result.failure != lifecycle.SCHEMA_INVALID,
        whole_response_failure=result.failure,
        n_hypotheses=len((canon or {}).get("hypotheses") or [])
        if isinstance(canon, dict) else 0,
        abstention_quality=abstention_quality(canon if isinstance(canon, dict) else {}),
        firewall_classes=classes,
        n_blocking_violations=len(firewall_v2.blocking(findings)),
        n_suppressed_violations=len(firewall_v2.suppressed(findings)),
        ontology=ontology.to_dict(),
        canonicalization=result.canonicalization or {},
    )

    if not result.accepted:
        return FixtureScoreV2(**base)

    compiled = query_plan.compile_set(
        {"fixture_id": fixture_id, "hypotheses": result.accepted_hypotheses},
        cutoff_unix=packet.get("information_cutoff_unix", 0), manifest=manifest)

    unavailable = 0
    for h in canon.get("hypotheses") or []:
        for cap_name in h.get("required_capabilities") or []:
            if not capability.is_supported_context_source(cap_name):
                unavailable += 1

    breakdown: dict[str, int] = {}
    for v in result.verdicts:
        if not v.accepted and v.failure:
            breakdown[v.failure] = breakdown.get(v.failure, 0) + 1
    for results in compiled["results"].values():
        for r in results:
            if not r["ok"] and r["failure"]:
                breakdown[r["failure"]] = breakdown.get(r["failure"], 0) + 1

    prof = normalize.intent_profile(canon)
    intents = [i.to_dict() for i in normalize.normalize_set(
        {"hypotheses": result.accepted_hypotheses})]

    return FixtureScoreV2(
        **base,
        n_accepted=result.n_accepted,
        n_compilable=compiled["n_fully_compilable"],
        n_plans=sum(len(v) for v in compiled["results"].values()),
        unavailable_requests=unavailable,
        metric_richness=prof["metric_richness"],
        family_richness=prof["family_richness"],
        redundancy_rate=prof["redundancy_rate"],
        distinct_intents=prof["n_distinct_intents"],
        failure_breakdown=breakdown,
        depth={
            "dimension_utilization": availability.depth_utilization(intents, ontology),
            "comparison_utilization": availability.comparison_utilization(
                intents, ontology),
            "expectable_dimensions": list(ontology.expectable_dimensions()),
            "excluded_dimensions": [
                n for n, d in sorted(ontology.dimensions.items()) if not d.expectable],
        },
        restraint=availability.restraint_profile(
            {"hypotheses": result.accepted_hypotheses}, ontology),
    )


# --------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------
@dataclass
class BatteryReportV2:
    n_fixtures: int
    discipline_metrics: dict
    discipline_gates: dict
    depth_report: dict
    restraint_report: dict
    passed: bool
    per_fixture: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "evaluation_version": EVALUATION_VERSION,
            "n_fixtures": self.n_fixtures,
            "discipline_metrics": self.discipline_metrics,
            "discipline_gates": self.discipline_gates,
            "depth_report": self.depth_report,
            "restraint_report": self.restraint_report,
            "passed": self.passed,
            "axes_note": ("discipline is GATED; depth and restraint are REPORTED and "
                          "never averaged into the verdict, so a compliance failure can "
                          "never masquerade as a depth failure or vice versa"),
            "per_fixture": [s.to_dict() if hasattr(s, "to_dict") else s
                            for s in self.per_fixture],
        }


def aggregate(
    scores: Sequence[FixtureScoreV2],
    *,
    repeatability_jaccard_median: Optional[float] = None,
    identity_jaccards: Sequence[float] = (),
    irrelevant_jaccards: Sequence[float] = (),
    evidence_perturbation_trips: Sequence[bool] = (),
    starved_payloads: Sequence[dict] = (),
) -> BatteryReportV2:
    n = len(scores)
    if n == 0:
        return BatteryReportV2(0, {}, {}, {}, {}, False, [])

    total_h = sum(s.n_hypotheses for s in scores)
    total_acc = sum(s.n_accepted for s in scores)
    T = THRESHOLDS

    # ---- abstention, with the corrected definition ------------------------------------
    starved_flags = [abstained(p) for p in starved_payloads]

    discipline = {
        "schema_validity_rate": sum(1 for s in scores if s.schema_valid) / n,
        "query_compile_rate": (sum(s.n_compilable for s in scores) / total_acc)
        if total_acc else 0.0,
        "grounding_rate": (total_acc / total_h) if total_h else 0.0,
        "unavailable_request_rate": (sum(s.unavailable_requests for s in scores) / total_h)
        if total_h else 0.0,
        "numerical_authority_violations_blocking":
            sum(s.n_blocking_violations for s in scores),
        "firewall_class_counts": {
            cls: sum(s.firewall_classes.get(cls, 0) for s in scores)
            for cls in (firewall_v2.CLASS_A, firewall_v2.CLASS_B, firewall_v2.CLASS_C)},
        "median_redundancy_rate": evaluation._median([s.redundancy_rate for s in scores]),
        "median_metric_richness": evaluation._median([s.metric_richness for s in scores]),
        "median_family_richness": evaluation._median([s.family_richness for s in scores]),
        "median_distinct_intents": evaluation._median([s.distinct_intents for s in scores]),
        "repeatability_jaccard_median": repeatability_jaccard_median,
        "abstention_rate_on_starved_packets": (
            sum(1 for f in starved_flags if f) / len(starved_flags))
        if starved_flags else None,
        "evidence_perturbation_trip_rate": (
            sum(1 for x in evidence_perturbation_trips if x)
            / len(evidence_perturbation_trips)) if evidence_perturbation_trips else None,
    }

    identity_rel = relative_invariance(
        evaluation._median(list(identity_jaccards)) if identity_jaccards else None,
        repeatability_jaccard_median)
    irrelevant_rel = relative_invariance(
        evaluation._median(list(irrelevant_jaccards)) if irrelevant_jaccards else None,
        repeatability_jaccard_median)
    discipline["identity_invariance_relative"] = identity_rel
    discipline["irrelevant_invariance_relative"] = irrelevant_rel

    gates: dict[str, Optional[bool]] = {
        "A_schema_validity":
            discipline["schema_validity_rate"] >= T["schema_validity_rate"],
        "B_query_compilability":
            discipline["query_compile_rate"] >= T["query_compile_rate"],
        "C_evidence_grounding": discipline["grounding_rate"] >= T["grounding_rate"],
        "D_capability_awareness":
            discipline["unavailable_request_rate"] <= T["max_unavailable_request_rate"],
        # E keeps ZERO TOLERANCE. Class A and class B both count; only class C -- which
        # carries no number and is explained entirely by an approved metric name -- is
        # excluded, because it was never a violation.
        "E_numerical_authority":
            discipline["numerical_authority_violations_blocking"]
            <= T["max_numerical_authority_violations"],
        "G_non_redundancy":
            discipline["median_redundancy_rate"] <= T["max_redundancy_rate"],
        "H_metric_richness":
            discipline["median_metric_richness"] >= T["min_median_metric_richness"]
            and discipline["median_family_richness"] >= T["min_median_family_richness"],
        "I_identity_robustness_relative": identity_rel["passed"],
        "K_irrelevant_invariance_relative": irrelevant_rel["passed"],
        "J_evidence_sensitivity": (
            discipline["evidence_perturbation_trip_rate"]
            >= T["min_evidence_perturbation_trip_rate"])
        if evidence_perturbation_trips else None,
        "L_abstention_quality": (
            discipline["abstention_rate_on_starved_packets"]
            >= T["min_abstention_rate_on_starved_packets"])
        if starved_flags else None,
    }
    passed = all(v is True for v in gates.values())

    # ---- DEPTH: reported, availability-gated, never a gate ----------------------------
    dim_expectable: dict[str, int] = {}
    dim_used: dict[str, int] = {}
    for s in scores:
        for dim, row in (s.depth.get("dimension_utilization") or {}).items():
            if row["counted_in_denominator"]:
                dim_expectable[dim] = dim_expectable.get(dim, 0) + 1
                if row["n_intents_using"] > 0:
                    dim_used[dim] = dim_used.get(dim, 0) + 1

    depth_report = {
        "availability_gated_dimension_utilization": {
            dim: {"n_fixtures_expectable": dim_expectable[dim],
                  "n_using": dim_used.get(dim, 0),
                  "utilization": round(dim_used.get(dim, 0) / dim_expectable[dim], 4)}
            for dim in sorted(dim_expectable)},
        "dimensions_excluded_everywhere": sorted(
            {d for s in scores for d in (s.depth.get("excluded_dimensions") or [])}
            - set(dim_expectable)),
        "note": ("a dimension the packets withheld is EXCLUDED from every denominator "
                 "above. It is never scored as a zero, and abstaining from it costs "
                 "nothing."),
    }

    # ---- RESTRAINT: reported ----------------------------------------------------------
    n_hyp = sum((s.restraint or {}).get("n_hypotheses", 0) for s in scores)
    restraint_report = {
        "n_hypotheses": n_hyp,
        "mean_interaction_rate": (
            sum((s.restraint or {}).get("interaction_rate", 0.0) for s in scores) / n),
        "mean_justified_interaction_rate": (
            sum((s.restraint or {}).get("justified_interaction_rate", 0.0)
                for s in scores) / n),
        "any_padding_conditions": sum(
            (s.restraint or {}).get("any_padding_conditions", 0) for s in scores),
        "conditions_on_withheld_dimensions": sum(
            (s.restraint or {}).get("conditions_on_withheld_dimensions", 0)
            for s in scores),
        "note": ("gratuitous complexity LOWERS this reading, so padding conditions or "
                 "proposing withheld dimensions is not a winning strategy"),
    }

    return BatteryReportV2(n, discipline, gates, depth_report, restraint_report,
                           passed, list(scores))


def version_stamp() -> dict:
    return {
        "evaluation_version": EVALUATION_VERSION,
        "thresholds": dict(THRESHOLDS),
        "invariance_floor_ratio": INVARIANCE_FLOOR_RATIO,
        **validator_v2.version_stamp(),
        **availability.version_stamp(),
    }
