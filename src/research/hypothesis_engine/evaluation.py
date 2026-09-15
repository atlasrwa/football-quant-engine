"""Hypothesis-generation evaluation battery (`hypothesis_evaluation_v1`).

    The test question is: "Is the model good at generating relevant, grounded, valid,
    stable football hypotheses that exploit our available raw metrics and compile into
    useful deterministic historical queries?"

    NOT: "Can the model predict the match?"

SCORING PHILOSOPHY (mandate §28)
--------------------------------
First-stage quality is *"did it ask a valid and potentially useful question?"* -- NOT
*"was the answer significant?"*. A well-formed hypothesis that the data later fails to
support is a successful research proposal, not a model failure. That is what research is.

So nothing in this module scores a hypothesis against a football outcome. Survival rates
through the funnel (data sufficiency, historical signal, OOS, prospective) are tracked
separately and attributed to the RESEARCH PROGRAMME, not used to punish the generator.

Every metric here is deterministic and computable offline from a stored response, so the
battery can be dry-run at zero cost before a single paid call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import (capability, firewall, lifecycle, normalize, query_plan, validator,
               vocabulary)

EVALUATION_VERSION = "hypothesis_evaluation_v1"


# --------------------------------------------------------------------------------------
# Pass/fail thresholds, fixed BEFORE any result exists (the legacy generation's discipline:
# "the bar was taken from the repository and not moved after seeing results").
# --------------------------------------------------------------------------------------
THRESHOLDS = {
    # A -- schema validity. Structured output with a closed schema should be near-perfect.
    "schema_validity_rate": 0.95,
    # B -- query compilability, per accepted hypothesis.
    "query_compile_rate": 0.85,
    # C -- evidence grounding.
    "grounding_rate": 0.95,
    # D -- capability awareness: asking for unavailable data.
    "max_unavailable_request_rate": 0.05,
    # E -- numerical authority. HARD GATE, zero tolerance.
    "max_numerical_authority_violations": 0,
    "max_latent_grading_violations": 0,
    # G -- non-redundancy.
    "max_redundancy_rate": 0.35,
    # H -- metric richness, median distinct metrics per fixture.
    "min_median_metric_richness": 5,
    "min_median_family_richness": 3,
    # I -- identity robustness: intent Jaccard under an alias swap.
    "min_identity_intent_jaccard": 0.80,
    # J -- meaningful-evidence sensitivity: fraction of perturbations that move intent.
    "min_evidence_perturbation_trip_rate": 0.50,
    # K -- irrelevant-perturbation invariance.
    "min_irrelevant_invariance_rate": 0.90,
    # L -- abstention quality: on packets built to be unanswerable.
    "min_abstention_rate_on_starved_packets": 0.70,
}


@dataclass
class FixtureScore:
    """Per-fixture deterministic scoring of one response."""

    fixture_id: str
    schema_valid: bool
    whole_response_failure: Optional[str] = None
    n_hypotheses: int = 0
    n_accepted: int = 0
    n_abstentions: int = 0
    n_grounded: int = 0
    n_compilable: int = 0
    n_plans: int = 0
    numerical_violations: int = 0
    grading_violations: int = 0
    unavailable_requests: int = 0
    metric_richness: int = 0
    family_richness: int = 0
    dimension_richness: int = 0
    redundancy_rate: float = 0.0
    distinct_intents: int = 0
    failure_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["evaluation_version"] = EVALUATION_VERSION
        return d


def score_response(
    payload,
    *,
    packet: dict,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
) -> FixtureScore:
    """Deterministically score one response. No model, no judgement, no outcome."""
    fixture_id = packet.get("fixture_id", "")

    result = validator.validate(
        payload, packet=packet,
        expected_packet_hash=packet.get("packet_hash"),
        expected_fixture_id=fixture_id, manifest=manifest)

    if not result.accepted:
        viol = firewall.scan(payload) if isinstance(payload, dict) else []
        return FixtureScore(
            fixture_id=fixture_id,
            schema_valid=result.failure != lifecycle.SCHEMA_INVALID,
            whole_response_failure=result.failure,
            n_hypotheses=len((payload or {}).get("hypotheses", []) or [])
            if isinstance(payload, dict) else 0,
            numerical_violations=sum(1 for v in viol if v.layer != "GRADE"),
            grading_violations=sum(1 for v in viol if v.layer == "GRADE"),
        )

    hyps = payload.get("hypotheses", []) or []
    abstentions = [h for h in hyps
                   if h.get("sufficiency") == vocabulary.SUFFICIENCY[1]]

    compiled = query_plan.compile_set(
        {"fixture_id": fixture_id, "hypotheses": result.accepted_hypotheses},
        cutoff_unix=packet.get("information_cutoff_unix", 0), manifest=manifest)

    n_plans = sum(len(v) for v in compiled["results"].values())

    unavailable = 0
    for h in hyps:
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

    prof = normalize.intent_profile(payload)

    return FixtureScore(
        fixture_id=fixture_id,
        schema_valid=True,
        n_hypotheses=len(hyps),
        n_accepted=result.n_accepted,
        n_abstentions=len(abstentions),
        n_grounded=result.n_accepted,
        n_compilable=compiled["n_fully_compilable"],
        n_plans=n_plans,
        numerical_violations=0,
        grading_violations=0,
        unavailable_requests=unavailable,
        metric_richness=prof["metric_richness"],
        family_richness=prof["family_richness"],
        dimension_richness=prof["dimension_richness"],
        redundancy_rate=prof["redundancy_rate"],
        distinct_intents=prof["n_distinct_intents"],
        failure_breakdown=breakdown,
    )


def _median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return float(s[m]) if len(s) % 2 else (s[m - 1] + s[m]) / 2


@dataclass
class BatteryReport:
    n_fixtures: int
    metrics: dict
    gates: dict
    passed: bool
    per_fixture: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "evaluation_version": EVALUATION_VERSION,
            "n_fixtures": self.n_fixtures,
            "metrics": dict(self.metrics),
            "gates": dict(self.gates),
            "passed": self.passed,
            "thresholds": dict(THRESHOLDS),
            "per_fixture": [s.to_dict() if hasattr(s, "to_dict") else s
                            for s in self.per_fixture],
        }


def aggregate(
    scores: Sequence[FixtureScore],
    *,
    identity_jaccards: Sequence[float] = (),
    evidence_perturbation_trips: Sequence[bool] = (),
    irrelevant_perturbation_invariances: Sequence[bool] = (),
    starved_abstention_flags: Sequence[bool] = (),
) -> BatteryReport:
    """Roll per-fixture scores and control outcomes into the pass/fail battery."""
    n = len(scores)
    if n == 0:
        return BatteryReport(0, {}, {}, False, [])

    total_h = sum(s.n_hypotheses for s in scores)
    total_acc = sum(s.n_accepted for s in scores)

    metrics = {
        # A
        "schema_validity_rate": sum(1 for s in scores if s.schema_valid) / n,
        # B -- share of ACCEPTED hypotheses that fully compile
        "query_compile_rate": (sum(s.n_compilable for s in scores) / total_acc)
        if total_acc else 0.0,
        # C -- share of all emitted hypotheses that survive grounding
        "grounding_rate": (total_acc / total_h) if total_h else 0.0,
        # D
        "unavailable_request_rate": (sum(s.unavailable_requests for s in scores) / total_h)
        if total_h else 0.0,
        # E -- hard gate
        "numerical_authority_violations": sum(s.numerical_violations for s in scores),
        "latent_grading_violations": sum(s.grading_violations for s in scores),
        # G / H
        "median_redundancy_rate": _median([s.redundancy_rate for s in scores]),
        "median_metric_richness": _median([s.metric_richness for s in scores]),
        "median_family_richness": _median([s.family_richness for s in scores]),
        "median_dimension_richness": _median([s.dimension_richness for s in scores]),
        "median_distinct_intents": _median([s.distinct_intents for s in scores]),
        # abstention behaviour on normal packets, reported not gated
        "abstention_rate": (sum(s.n_abstentions for s in scores) / total_h)
        if total_h else 0.0,
        # I / J / K / L -- controls
        "identity_intent_jaccard_median": _median(list(identity_jaccards)),
        "evidence_perturbation_trip_rate": (
            sum(1 for x in evidence_perturbation_trips if x) / len(evidence_perturbation_trips)
        ) if evidence_perturbation_trips else None,
        "irrelevant_invariance_rate": (
            sum(1 for x in irrelevant_perturbation_invariances if x)
            / len(irrelevant_perturbation_invariances)
        ) if irrelevant_perturbation_invariances else None,
        "abstention_rate_on_starved_packets": (
            sum(1 for x in starved_abstention_flags if x) / len(starved_abstention_flags)
        ) if starved_abstention_flags else None,
    }

    T = THRESHOLDS
    gates: dict[str, Optional[bool]] = {
        "A_schema_validity": metrics["schema_validity_rate"] >= T["schema_validity_rate"],
        "B_query_compilability": metrics["query_compile_rate"] >= T["query_compile_rate"],
        "C_evidence_grounding": metrics["grounding_rate"] >= T["grounding_rate"],
        "D_capability_awareness":
            metrics["unavailable_request_rate"] <= T["max_unavailable_request_rate"],
        "E_numerical_authority":
            metrics["numerical_authority_violations"]
            <= T["max_numerical_authority_violations"]
            and metrics["latent_grading_violations"]
            <= T["max_latent_grading_violations"],
        "G_non_redundancy": metrics["median_redundancy_rate"] <= T["max_redundancy_rate"],
        "H_metric_richness":
            metrics["median_metric_richness"] >= T["min_median_metric_richness"]
            and metrics["median_family_richness"] >= T["min_median_family_richness"],
    }

    # Control gates are None (not False) when the control was not run -- "we did not
    # measure it" stays visibly distinct from "it failed", exactly as the legacy
    # eligibility core insisted.
    gates["I_identity_robustness"] = (
        metrics["identity_intent_jaccard_median"] >= T["min_identity_intent_jaccard"]
        if identity_jaccards else None)
    gates["J_evidence_sensitivity"] = (
        metrics["evidence_perturbation_trip_rate"]
        >= T["min_evidence_perturbation_trip_rate"]
        if evidence_perturbation_trips else None)
    gates["K_irrelevant_invariance"] = (
        metrics["irrelevant_invariance_rate"] >= T["min_irrelevant_invariance_rate"]
        if irrelevant_perturbation_invariances else None)
    gates["L_abstention_quality"] = (
        metrics["abstention_rate_on_starved_packets"]
        >= T["min_abstention_rate_on_starved_packets"]
        if starved_abstention_flags else None)

    # Fail closed: an unmeasured gate is NOT a pass.
    passed = all(v is True for v in gates.values())

    return BatteryReport(n, metrics, gates, passed, list(scores))


# --------------------------------------------------------------------------------------
# Funnel survival -- tracked, never used to score the generator (mandate §28)
# --------------------------------------------------------------------------------------
def funnel_survival(provenances: Sequence[lifecycle.HypothesisProvenance]) -> dict:
    """What fraction of proposals survived each stage.

    This is the economic/scientific value of the research layer over time. It is
    deliberately reported separately from `aggregate`, because a valid question that the
    data does not support is a successful proposal and must not lower the generator's
    score.
    """
    stages = lifecycle.PROGRESS_STATES
    reached = {s: 0 for s in stages}
    for p in provenances:
        seen = {e.state for e in p.events}
        for s in stages:
            if s in seen:
                reached[s] += 1
    n = len(provenances) or 1
    return {
        "evaluation_version": EVALUATION_VERSION,
        "n_proposed": len(provenances),
        "reached": reached,
        "survival_rate": {s: round(reached[s] / n, 4) for s in stages},
        "note": "Survival measures the research programme, not the generator. A valid "
                "hypothesis the data does not support is a successful proposal.",
    }
