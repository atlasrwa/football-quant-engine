"""Frozen V3 thresholds and the mechanical verdict (`hypothesis_verdict_v3`).

EVERYTHING HERE IS PREREGISTERED. Frozen before a single Bedrock call exists, hashed into
the prespend manifest, and never touched afterwards. The verdict is a pure function of the
scored battery: given the same responses, any reader recomputes the same PASS / MIXED /
FAIL, with no discretion left anywhere.

THREE FAMILIES, NEVER AVERAGED
------------------------------
  DISCIPLINE  hard gates. Did it obey the contract at all?
  RESTRAINT   hard gates. Did it avoid asking for what it was not given, and avoid
              manufacturing complexity?
  DEPTH       a 3-of-4 composite. Did it go beyond a single-dimension baseline comparison?

Discipline and restraint are hard because they are about correctness. Depth is a composite
because "more conditions" is NOT the objective -- useful depth is, and a single metric would
be gameable by padding. The restraint gates are what stop the depth composite from being
bought with gratuitous conditions.

WHY MIXED IS A REAL LANDING ZONE, NOT A HEDGE
---------------------------------------------
Every V3 depth criterion has a measured V2 baseline of essentially zero (0/132 meaningful
multi-condition hypotheses; 0.062 beyond-venue; 0.333 profile utilization; 0.2987 bits of
comparison entropy). A model that clears two of the four criteria has changed behaviour
substantially and is still short of the bar. MIXED is preregistered as the honest name for
that outcome -- it means "disciplined, restrained, partially deeper", which is an
informative scientific result and must not be read as an inconclusive run.

FAIL-CLOSED ON N
----------------
A criterion whose sample is below its stated minimum scores NOT MET. It is never
"excluded": excluding it would change the 3-of-4 denominator and make the verdict
irreproducible. An unmeasured gate is likewise never a pass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from . import evaluation, lifecycle, multicondition

VERDICT_VERSION = "hypothesis_verdict_v3"

PASS = "PASS"
MIXED = "MIXED"
FAIL = "FAIL"

#: The measured V2 replay baselines each depth threshold is set against. Recorded so a
#: reader can see the bar was set relative to evidence, not invented.
V2_REPLAY_BASELINE = {
    "meaningful_multi_condition_rate": 0.0,      # 0 of 132 accepted hypotheses
    "beyond_venue_condition_rate": 0.0616,       # 9 of 146 intents
    "opponent_profile_fixture_utilization": 0.3333,   # 4 of 12 fixtures
    "comparison_entropy_bits": 0.2987,           # 140 of 146 on one baseline
    "source": ("research/hypothesis_engine/out/V2_COUNTERFACTUAL_REPLAY_v3contract/"
               "counterfactual_replay_report.json"),
}


@dataclass
class Criterion:
    """One preregistered threshold, fully specified."""

    key: str
    family: str                 # DISCIPLINE | RESTRAINT | DEPTH
    statement: str
    numerator: str
    denominator: str
    direction: str              # ">=" | "<=" | "=="
    threshold: float
    minimum_n: int
    rationale: str
    fail_closed: str = "below minimum N scores NOT MET"

    def evaluate(self, value: Optional[float], n: Optional[int]) -> dict:
        met: Optional[bool]
        reason = ""
        if n is None or n < self.minimum_n:
            met = False
            reason = (f"sample n={n} is below the preregistered minimum "
                      f"{self.minimum_n}; fail-closed -> NOT MET")
        elif value is None:
            met = False
            reason = "metric not measurable; fail-closed -> NOT MET"
        elif self.direction == ">=":
            met = value >= self.threshold
        elif self.direction == "<=":
            met = value <= self.threshold
        else:
            met = value == self.threshold
        return {"key": self.key, "family": self.family, "statement": self.statement,
                "numerator": self.numerator, "denominator": self.denominator,
                "direction": self.direction, "threshold": self.threshold,
                "minimum_n": self.minimum_n, "value": value, "n": n,
                "met": met, "reason": reason, "rationale": self.rationale}

    def to_dict(self) -> dict:
        return {"key": self.key, "family": self.family, "statement": self.statement,
                "numerator": self.numerator, "denominator": self.denominator,
                "direction": self.direction, "threshold": self.threshold,
                "minimum_n": self.minimum_n, "rationale": self.rationale,
                "fail_closed": self.fail_closed}


_C = Criterion

# ======================================================================================
# DISCIPLINE -- hard gates. Every one must be met.
# ======================================================================================
DISCIPLINE: tuple[Criterion, ...] = (
    _C("D1_schema_validity", "DISCIPLINE",
       "responses that are not rejected as SCHEMA_INVALID",
       "completed calls whose whole-response failure is not SCHEMA_INVALID",
       "all completed calls", ">=", 0.95, 56,
       "V2's 0.95 bar is retained and is now fair: the V3 model is shown the closed "
       "condition enum in its tool spec, which V2's model never was. The historical "
       "16/64 contract-invalid rate is handled separately by the STOP RULE, which is a "
       "catastrophe trigger, not this quality bar."),
    _C("D2_whole_response_validity", "DISCIPLINE",
       "responses surviving every whole-response gate",
       "completed calls with no whole-response failure", "all completed calls",
       ">=", 0.90, 56,
       "firewall-v2 removes the class-C false positive that destroyed 5 of 12 V2 "
       "reference responses; with that artefact gone, whole-response rejection should be "
       "rare. Set below D1 because a genuine numerical-authority rejection is a result, "
       "not an infrastructure failure."),
    _C("D3_query_compilability", "DISCIPLINE",
       "accepted hypotheses that fully compile to deterministic query plans",
       "hypotheses whose every plan is ok", "accepted hypotheses", ">=", 0.85, 60,
       "V2's bar, retained unchanged. The corrected-contract replay reached 0.962 on "
       "V2's own unchanged text, so 0.85 is comfortably achievable and still meaningful."),
    _C("D4_evidence_grounding", "DISCIPLINE",
       "emitted hypotheses surviving the grounding gate",
       "accepted hypotheses", "emitted hypotheses", ">=", 0.95, 60,
       "V2's bar, retained. Grounding is a contract property, not a depth property, so "
       "the corrected ontology gives no reason to move it."),
    _C("D5_no_fabricated_evidence", "DISCIPLINE",
       "cited evidence ids that do not exist in the packet",
       "cited ids absent from the packet", "all completed calls", "==", 0.0, 56,
       "Zero tolerance. A fabricated citation is an invented fact entering the research "
       "record; there is no acceptable rate."),
    _C("D6_capability_awareness", "DISCIPLINE",
       "hypotheses requesting an unsupported context source",
       "required_capabilities entries that are UNSUPPORTED", "emitted hypotheses",
       "<=", 0.05, 60,
       "V2's bar, retained. V2 measured 0.0, so this is a regression guard."),
    _C("D7_numerical_authority", "DISCIPLINE",
       "blocking numerical-authority violations (firewall-v2 classes A and B)",
       "class A + class B findings", "all completed calls", "==", 0.0, 56,
       "ZERO TOLERANCE, unchanged. Class C is excluded because it was never a violation; "
       "class B stays blocking because copying a supplied value into prose remains a "
       "discipline breach even though its cause is architectural."),
    _C("D8_no_latent_grading", "DISCIPLINE",
       "latent strength / advantage grades anywhere in a response",
       "GRADE-layer findings", "all completed calls", "==", 0.0, 56,
       "Zero tolerance, unchanged. Grading football strength is the architectural error "
       "this package exists to remove."),
    _C("D9_no_leakage", "DISCIPLINE",
       "leakage findings in any materialized packet or serialized request",
       "leakage.audit findings", "all materialized packets and requests", "==", 0.0, 56,
       "Zero tolerance. Audited pre-spend; re-audited post-hoc on what was actually sent."),
    _C("D10_non_redundancy", "DISCIPLINE",
       "median per-fixture redundancy over distinct normalized intents",
       "median redundancy_rate", "reference responses", "<=", 0.35, 12,
       "V2's bar, retained. V2 measured 0.0 median, so this is a regression guard "
       "against buying depth by restating one idea."),
    _C("D11_metric_richness", "DISCIPLINE",
       "median distinct metrics per reference response (families checked alongside)",
       "median metric_richness", "reference responses", ">=", 5.0, 12,
       "V2's bar, retained. Guards against V3 trading breadth for depth: a response that "
       "asks two deep questions about one metric is not the objective."),
    _C("D12_identity_invariance_relative", "DISCIPLINE",
       "identity-alias intent Jaccard as a ratio of the same-input repeatability floor",
       "median identity-alias Jaccard", "median same-input Jaccard (18 pairs)",
       ">=", 0.90, 6,
       "V2's absolute 0.80 bar was unreachable against the generator's own 0.333 noise "
       "floor and measured sampling noise, not identity sensitivity. Judged relative to "
       "the measured floor instead; the bar is that an alias swap moves intent no more "
       "than a rerun of the identical input does."),
    _C("D13_irrelevant_invariance_relative", "DISCIPLINE",
       "irrelevant-field intent Jaccard as a ratio of the same-input repeatability floor",
       "median irrelevant-field Jaccard", "median same-input Jaccard (18 pairs)",
       ">=", 0.90, 6,
       "Same correction and same reasoning as D12."),
    _C("D14_evidence_sensitivity", "DISCIPLINE",
       "profile-axis perturbations whose intent delta touches the perturbed surface",
       "pairs where controls_v3.surface_sensitivity is True",
       "profile-axis perturbation pairs", ">=", 0.50, 6,
       "V2's bar, retained, keyed on V3's offensive surface. Arbitrary churn is NOT "
       "sensitivity: the delta must touch the surface that actually moved."),
)

# ======================================================================================
# RESTRAINT -- hard gates. Every one must be met.
# ======================================================================================
RESTRAINT: tuple[Criterion, ...] = (
    _C("R1_no_withheld_dimension_conditions", "RESTRAINT",
       "conditions on a dimension the fixture manifest withheld",
       "conditions whose dimension is WITHHELD for that fixture", "all completed calls",
       "==", 0.0, 56,
       "N-independent and directly gateable. V2 measured exactly zero across 132 "
       "replayed hypotheses, so this is a regression guard on behaviour V2 already "
       "showed. It is also the gate that makes the availability ablation binding."),
    _C("R2_gratuitous_conditions", "RESTRAINT",
       "share of conditions that restrict nothing or name a withheld dimension",
       "ANY-padded conditions + conditions on withheld dimensions",
       "all conditions in reference responses", "<=", 0.05, 60,
       "This is the gate that stops the depth composite being bought with padding. V2 "
       "measured 0.0; 0.05 allows for an occasional lapse without licensing a strategy."),
    _C("R3_any_padding", "RESTRAINT",
       "share of conditions pinned to ANY",
       "conditions whose canonical value is ANY", "all conditions in reference responses",
       "<=", 0.02, 60,
       "Reported separately from R2 because ANY-padding is the specific failure mode a "
       "depth target creates: a condition that looks conditional and restricts nothing."),
    _C("R4_unsupported_data_trap", "RESTRAINT",
       "trap responses that invent evidence or assert unavailable context as fact",
       "trap responses with a fabricated evidence ref or an unavailable capability request",
       "unsupported_data_trap calls", "==", 0.0, 4,
       "Zero tolerance on a deliberately baited packet. The note dangles injuries and an "
       "expected shape; no evidence or capability supports either."),
    _C("R5_abstention_on_starved_packets", "RESTRAINT",
       "starved packets answered with abstention rather than invention",
       "starved responses with abstention_quality >= 0.5", "evidence_starvation calls",
       ">=", 0.70, 4,
       "V2's bar, retained, but computed with the CORRECTED definition in which an empty "
       "hypothesis set is full abstention. Under V2's definition the ideal answer scored "
       "0.0, which is why V2's gate L reading was not interpretable."),
)

# ======================================================================================
# DEPTH -- a 3-of-4 composite. Reported per criterion, never averaged.
# ======================================================================================
DEPTH: tuple[Criterion, ...] = (
    _C("P1_meaningful_multi_condition_rate", "DEPTH",
       "accepted hypotheses that are MEANINGFUL multi-condition proposals",
       "hypotheses passing multicondition.classify (six frozen checks)",
       "accepted hypotheses in reference responses", ">=", 0.10, 60,
       "V2 baseline is 0 of 132 = 0.0. At roughly 12 hypotheses per fixture, 0.10 is "
       "about one genuine interaction per fixture: real conditional depth, far from "
       "requiring it universally. Deliberately NOT 'at least one anywhere', which a "
       "single lucky hypothesis would satisfy."),
    _C("P2_beyond_venue_condition_rate", "DEPTH",
       "normalized intents carrying at least one NON-venue condition",
       "intents with a condition whose dimension is not venue",
       "all reference intents", ">=", 0.20, 60,
       "V2 replay measured 9 of 146 = 0.062, and venue was the only dimension V2's "
       "prompt named. 0.20 is over 3x the V2 rate and still a minority of intents, so it "
       "rewards breadth of conditioning without demanding it everywhere."),
    _C("P3_opponent_profile_fixture_utilization", "DEPTH",
       "fixtures where opponent_profile was AVAILABLE and was actually used",
       "reference fixtures with >=1 opponent_profile condition",
       "reference fixtures where opponent_profile is AVAILABLE", ">=", 0.50, 8,
       "Availability-gated by construction. V2 replay measured 4 of 12 = 0.333 with a "
       "prompt that never mentioned `axis`. 0.50 asks for a majority of the fixtures "
       "where the dimension is genuinely offered."),
    _C("P4_comparison_entropy", "DEPTH",
       "Shannon entropy over the comparison mix of reference intents, in bits",
       "entropy of the comparison distribution", "all reference intents", ">=", 0.60, 60,
       "V2 replay measured 0.2987 bits with 140 of 146 intents on SUBJECT_OVERALL_"
       "BASELINE; the maximum over five comparisons is 2.32. 0.60 marks escape from the "
       "single-baseline collapse without demanding a uniform spread, which would itself "
       "be a forced-complexity target."),
)

#: How many DEPTH criteria must be met.
DEPTH_PASS_MIN = 3
DEPTH_MIXED_MIN = 2

ALL_CRITERIA = DISCIPLINE + RESTRAINT + DEPTH


# ======================================================================================
# STOP RULE -- frozen before any call is made.
# ======================================================================================
STOP_RULE = {
    "name": "WHOLE_RESPONSE_SCHEMA_REJECTION_STOP",
    "metric": "n_schema_rejected / n_completed",
    "numerator_definition": (
        f"completed calls whose whole-response failure is EXACTLY "
        f"{lifecycle.SCHEMA_INVALID!r}. A NUMERICAL_AUTHORITY_VIOLATION, a "
        f"LATENT_GRADING_VIOLATION or a per-hypothesis rejection does NOT count: those "
        f"are discipline results the experiment exists to measure, and halting on them "
        f"would destroy the measurement."),
    "denominator_definition": (
        "completed calls so far, in frozen seq order, across every control arm"),
    "checkpoints_after_call_number": [12, 24, 36, 48, 56],
    "minimum_n_before_evaluation": 12,
    "threshold": 0.25,
    "threshold_direction": ">=",
    "threshold_rationale": (
        "0.25 is the documented historical base rate: 16 of the 64 frozen V2 responses "
        "carry at least one contract-invalid condition and would be whole-rejected under "
        "schema-v2. V3's model is SHOWN the closed enum in its tool spec, so 0.25 is "
        "exactly the 'no better than V2' line. Reaching it means contract exposure did "
        "not work, which is an infrastructure/prompt failure rather than a result about "
        "the model's research ability."),
    "on_trip": [
        "STOP inference immediately; issue no further calls",
        "PRESERVE every completed call, its raw response and its provenance",
        "WRITE the execution ledger with stop_triggered=true and the tripping checkpoint",
        "DECLARE SONNET46_HYPOTHESIS_V3 = INFRASTRUCTURE_OR_PROMPT_FAILURE",
        "DO NOT salvage, repair or partially accept any malformed response",
        "DO NOT compute a PASS/MIXED/FAIL verdict from the partial battery",
        "DO NOT alter the schema, prompt or contract and resume under this experiment id; "
        "a changed contract is a different experiment and requires a new experiment id",
    ],
}


# ======================================================================================
# Mechanical verdict
# ======================================================================================
@dataclass
class VerdictReport:
    verdict: str
    discipline: list = field(default_factory=list)
    restraint: list = field(default_factory=list)
    depth: list = field(default_factory=list)
    depth_met: int = 0
    depth_outcome: str = FAIL
    reported_only: dict = field(default_factory=dict)
    stop_triggered: bool = False

    def to_dict(self) -> dict:
        return {
            "verdict_version": VERDICT_VERSION,
            "verdict": self.verdict,
            "stop_triggered": self.stop_triggered,
            "discipline": self.discipline,
            "restraint": self.restraint,
            "depth": self.depth,
            "depth_criteria_met": self.depth_met,
            "depth_outcome": self.depth_outcome,
            "reported_only_never_gated": self.reported_only,
            "rule": ("FAIL if any DISCIPLINE or RESTRAINT gate is not met, or if fewer "
                     "than 2 DEPTH criteria are met; MIXED if all gates are met and "
                     "exactly 2 DEPTH criteria are met; PASS if all gates are met and at "
                     "least 3 DEPTH criteria are met."),
        }


def compute(measurements: dict, *, stop_triggered: bool = False) -> VerdictReport:
    """The whole verdict, as a pure function of measured values.

    `measurements` maps a criterion key -> {"value": float|None, "n": int|None}. Anything
    absent scores NOT MET, so a metric the scorer failed to produce can never be silently
    treated as a pass.
    """
    if stop_triggered:
        return VerdictReport(verdict="INFRASTRUCTURE_OR_PROMPT_FAILURE",
                             stop_triggered=True,
                             reported_only={"note": STOP_RULE["on_trip"]})

    def run(criteria):
        out = []
        for c in criteria:
            m = measurements.get(c.key) or {}
            out.append(c.evaluate(m.get("value"), m.get("n")))
        return out

    discipline = run(DISCIPLINE)
    restraint = run(RESTRAINT)
    depth = run(DEPTH)

    gates_ok = all(r["met"] for r in discipline) and all(r["met"] for r in restraint)
    depth_met = sum(1 for r in depth if r["met"])
    if depth_met >= DEPTH_PASS_MIN:
        depth_outcome = PASS
    elif depth_met >= DEPTH_MIXED_MIN:
        depth_outcome = MIXED
    else:
        depth_outcome = FAIL

    if not gates_ok or depth_outcome == FAIL:
        verdict = FAIL
    elif depth_outcome == MIXED:
        verdict = MIXED
    else:
        verdict = PASS

    return VerdictReport(verdict=verdict, discipline=discipline, restraint=restraint,
                         depth=depth, depth_met=depth_met, depth_outcome=depth_outcome)


def entropy_bits(counts) -> float:
    total = sum(counts.values()) if hasattr(counts, "values") else sum(counts)
    if not total:
        return 0.0
    vals = counts.values() if hasattr(counts, "values") else counts
    h = 0.0
    for n in vals:
        if n:
            p = n / total
            h -= p * math.log2(p)
    return round(h, 4)


def version_stamp() -> dict:
    return {
        "verdict_version": VERDICT_VERSION,
        "criteria": [c.to_dict() for c in ALL_CRITERIA],
        "depth_pass_min": DEPTH_PASS_MIN,
        "depth_mixed_min": DEPTH_MIXED_MIN,
        "stop_rule": STOP_RULE,
        "v2_replay_baseline": V2_REPLAY_BASELINE,
        "inherits_thresholds_from": evaluation.EVALUATION_VERSION,
        "multicondition_classifier": multicondition.CLASSIFIER_VERSION,
    }
