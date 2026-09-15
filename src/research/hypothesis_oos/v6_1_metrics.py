"""V6.1 evaluator-wide metric contract layer + registry (`v6_1_metrics_v1`).

WHY THIS MODULE EXISTS
----------------------
V6's decisive FAIL was produced by `compiler_valid_rate = 1.153` -- a proportion above 1.0,
which is mathematically impossible. The root cause was not one arithmetic slip; it was the
absence of a GENERIC metric contract. Nothing in the evaluator asserted that a quantity
called a "rate" obeys `0 <= numerator <= denominator` and therefore `0 <= value <= 1`. An
impossible value passed silently into the discipline gate and decided the verdict.

This module is that missing contract. It defines metric TYPES with explicit invariants, a
machine-readable REGISTRY describing every rate the evaluator computes (its numerator and
denominator population, abstention/availability treatment, zero-denominator convention, legal
domain, aggregation level, and arm-comparison direction), and an enforcement function that
runs IN THE PRODUCTION EVALUATOR PATH -- not only in tests. An impossible metric raises a
`MetricContractViolation`, which the V6.1 verdict maps to EVALUATOR/APPARATUS invalidity, so
it can never silently feed a scientific verdict.

ZERO SPEND. Pure arithmetic; no network, no model.
"""
from __future__ import annotations

import math

METRICS_VERSION = "v6_1_metrics_v1"

# ---- metric types --------------------------------------------------------------------
TYPE_RATE = "RATE"                     # numerator/denominator proportion in [0,1]
TYPE_COUNT = "COUNT"                   # non-negative integer
TYPE_SIGNED_RATE_DELTA = "SIGNED_RATE_DELTA"   # difference of two rates, in [-1,1]
TYPE_PROBABILITY = "PROBABILITY"       # value in [0,1]
TYPE_SD = "SD"                         # standard deviation, >= 0
TYPE_SAMPLE_SIZE = "SAMPLE_SIZE"       # non-negative integer

#: The explicit, preregistered convention for a rate whose denominator is 0. A rate over an
#: empty eligible population is UNDEFINED, represented as None -- never silently 0.0 or 1.0.
#: Downstream (verdict discipline/primary) treats a None rate as "not measured" and excludes
#: it, exactly as the frozen scorecard already does for empty-denominator rates.
ZERO_DENOMINATOR_VALUE = None


class MetricContractViolation(Exception):
    """An evaluator metric violated its declared contract. This is an APPARATUS/EVALUATOR
    invalidity, never a scientific verdict. Raised inside the production evaluator path so an
    impossible metric aborts evaluation rather than feeding a PASS/MIXED/FAIL."""

    def __init__(self, metric_name: str, detail: str):
        super().__init__(f"{metric_name}: {detail}")
        self.metric_name = metric_name
        self.detail = detail


def _is_finite_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def check_rate(name: str, numerator, denominator):
    """Enforce the RATE contract and RETURN the value (or the zero-denominator convention).

    Invariants (all enforced, raising MetricContractViolation on breach):
      * numerator and denominator finite;
      * numerator >= 0, denominator >= 0;
      * numerator <= denominator;
      * denominator > 0  ->  0 <= value <= 1;
      * denominator == 0 ->  value is the frozen ZERO_DENOMINATOR_VALUE (None).
    """
    if not _is_finite_number(numerator):
        raise MetricContractViolation(name, f"numerator not finite: {numerator!r}")
    if not _is_finite_number(denominator):
        raise MetricContractViolation(name, f"denominator not finite: {denominator!r}")
    if numerator < 0:
        raise MetricContractViolation(name, f"negative numerator {numerator}")
    if denominator < 0:
        raise MetricContractViolation(name, f"negative denominator {denominator}")
    if numerator > denominator:
        raise MetricContractViolation(
            name, f"numerator {numerator} > denominator {denominator}; a proportion cannot "
                  f"exceed its eligible population (this is the V6 compiler_valid_rate class "
                  f"of defect)")
    if denominator == 0:
        return ZERO_DENOMINATOR_VALUE
    value = numerator / denominator
    if not (0.0 <= value <= 1.0):
        raise MetricContractViolation(name, f"value {value} outside [0,1]")
    return value


def check_value_in_unit_interval(name: str, value):
    """A RATE/PROBABILITY value already computed elsewhere must lie in [0,1] (or be None)."""
    if value is None:
        return None
    if not _is_finite_number(value):
        raise MetricContractViolation(name, f"value not finite: {value!r}")
    if not (0.0 <= value <= 1.0):
        raise MetricContractViolation(name, f"value {value} outside [0,1]")
    return value


def check_signed_rate_delta(name: str, delta):
    if delta is None:
        return None
    if not _is_finite_number(delta):
        raise MetricContractViolation(name, f"delta not finite: {delta!r}")
    if not (-1.0 <= delta <= 1.0):
        raise MetricContractViolation(name, f"signed rate delta {delta} outside [-1,1]")
    return delta


def check_count(name: str, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MetricContractViolation(name, f"count must be a non-negative int: {value!r}")
    return value


def check_sd(name: str, value):
    if value is None:
        return None
    if not _is_finite_number(value) or value < 0:
        raise MetricContractViolation(name, f"SD must be finite and >= 0: {value!r}")
    return value


def check_sample_size(name: str, value):
    return check_count(name, value)


# ---- the machine-readable metric registry --------------------------------------------
# Every rate/proportion the V6.1 evaluator computes, with explicit semantics. `eligibility`
# is the population the denominator counts; `abstention` states whether abstaining
# hypotheses are IN/OUT of numerator and denominator. Aggregation level and arm-comparison
# direction are recorded so a reader can see the contract without reading the code.
REGISTRY = {
    # ---- per-response scorecard rates (frozen v6_scorecard; audited, all in [0,1]) ----
    "qualified_rate": {
        "type": TYPE_RATE, "numerator": "n_qualified",
        "denominator": "n_nonabstaining", "eligibility": "non-abstaining hypotheses",
        "abstention": "excluded from numerator AND denominator",
        "availability": "an availability-violating hypothesis is non-abstaining and counts "
                        "in the denominator but not the numerator",
        "zero_denominator": "None (all-abstention response)", "domain": "[0,1]",
        "aggregation": "per response", "arm_direction": "higher is better (PRIMARY input)"},
    "evidence_specific_qualified_rate": {
        "type": TYPE_RATE, "numerator": "n_evidence_specific_qualified",
        "denominator": "n_nonabstaining", "eligibility": "non-abstaining hypotheses",
        "abstention": "excluded from numerator AND denominator",
        "availability": "as qualified_rate", "zero_denominator": "None",
        "domain": "[0,1]", "aggregation": "per response",
        "arm_direction": "higher is better (diagnostic)"},
    "valid_evidence_reference_rate": {
        "type": TYPE_RATE, "numerator": "n_valid_refs", "denominator": "n_refs",
        "eligibility": "all evidence references across all recovered hypotheses",
        "abstention": "abstention refs are included (they cite evidence too)",
        "availability": "n/a", "zero_denominator": "None (no references)",
        "domain": "[0,1]", "aggregation": "per response",
        "arm_direction": "higher is better (diagnostic)"},
    "fabricated_evidence_rate": {
        "type": TYPE_RATE, "numerator": "n_fabricated_refs", "denominator": "n_refs",
        "eligibility": "all evidence references across all recovered hypotheses",
        "abstention": "abstention refs included", "availability": "n/a",
        "zero_denominator": "None", "domain": "[0,1]", "aggregation": "per response",
        "arm_direction": "lower is better (DISCIPLINE axis)"},
    "abstention_rate": {
        "type": TYPE_RATE, "numerator": "n_abstentions", "denominator": "n_recoverable",
        "eligibility": "all recovered hypotheses",
        "abstention": "abstentions ARE the numerator; denominator is all recovered",
        "availability": "n/a", "zero_denominator": "None (no recovered hypotheses)",
        "domain": "[0,1]", "aggregation": "per response",
        "arm_direction": "descriptive (not a discipline axis)"},
    "grounded_abstention_rate": {
        "type": TYPE_RATE, "numerator": "n_abstentions_with_refs",
        "denominator": "n_abstentions", "eligibility": "abstaining hypotheses only",
        "abstention": "denominator IS the abstaining population",
        "availability": "n/a", "zero_denominator": "None (no abstentions)",
        "domain": "[0,1]", "aggregation": "per response",
        "arm_direction": "descriptive"},
    "meaningful_interaction_rate": {
        "type": TYPE_RATE, "numerator": "n_meaningful_interactions",
        "denominator": "n_interactions", "eligibility": "interaction hypotheses only",
        "abstention": "n/a (interactions are non-abstaining)", "availability": "n/a",
        "zero_denominator": "None (no interactions)", "domain": "[0,1]",
        "aggregation": "per response", "arm_direction": "descriptive"},
    "redundancy_rate": {
        "type": TYPE_RATE, "numerator": "n_redundant", "denominator": "n_recoverable",
        "eligibility": "all recovered hypotheses",
        "abstention": "included in denominator (an abstention can be redundant)",
        "availability": "n/a", "zero_denominator": "None", "domain": "[0,1]",
        "aggregation": "per response", "arm_direction": "lower is better (DISCIPLINE axis)"},
    "discipline_violation_rate": {
        "type": TYPE_RATE,
        "numerator": "count of firewall/numeric-contract/grounding/availability violations",
        "denominator": "n_recoverable", "eligibility": "all recovered hypotheses",
        "abstention": "included in denominator; abstentions are not violations so they only "
                      "enlarge the denominator (conservative)",
        "availability": "availability violations ARE counted in the numerator",
        "zero_denominator": "None", "domain": "[0,1]", "aggregation": "per response",
        "arm_direction": "lower is better (DISCIPLINE axis)"},
    # ---- verdict-level pooled discipline axis: THE REPAIRED METRIC ----
    "compiler_valid_rate": {
        "type": TYPE_RATE,
        "numerator": "n_nonabstaining_compiler_valid (non-abstaining AND compiler_valid)",
        "denominator": "n_nonabstaining",
        "eligibility": "NON-ABSTAINING hypotheses only",
        "abstention": "EXCLUDED from numerator AND denominator (the V6 defect included "
                      "compilable abstentions in the numerator against a non-abstaining "
                      "denominator, producing rate>1)",
        "availability": "an availability-violating hypothesis is non-abstaining; it is in "
                        "the denominator and in the numerator iff it compiles",
        "zero_denominator": "None (no non-abstaining hypotheses in the arm)",
        "domain": "[0,1]", "aggregation": "pooled across responses within an arm",
        "arm_direction": "higher is better; degradation = research compiles LESS than base"},
    # ---- primary endpoint statistic (fixture-balanced) ----
    "paired_qualified_rate_diff": {
        "type": TYPE_SIGNED_RATE_DELTA,
        "numerator": "per-fixture (research qualified_rate mean - base qualified_rate mean)",
        "denominator": "n/a (a difference of two rates)",
        "eligibility": "paired fixtures with a measured qualified_rate in both arms",
        "abstention": "inherited from qualified_rate", "availability": "inherited",
        "zero_denominator": "fixture excluded if either arm has no measured rate",
        "domain": "[-1,1]", "aggregation": "mean over paired fixtures (fixture-balanced)",
        "arm_direction": "positive = research better (PRIMARY)"},
}


def registry_rows() -> list:
    """The registry as a sorted list of rows, for a report or a frozen artifact."""
    return [{"metric_name": k, **v} for k, v in sorted(REGISTRY.items())]


def version_stamp() -> dict:
    return {"metrics_version": METRICS_VERSION,
            "metric_types": [TYPE_RATE, TYPE_COUNT, TYPE_SIGNED_RATE_DELTA,
                             TYPE_PROBABILITY, TYPE_SD, TYPE_SAMPLE_SIZE],
            "zero_denominator_value": ZERO_DENOMINATOR_VALUE,
            "enforced_in_production_path": True,
            "n_registered_metrics": len(REGISTRY),
            "repairs": "compiler_valid_rate numerator restricted to non-abstaining "
                       "compiler-valid hypotheses (V6 defect: abstentions inflated it > 1)"}
