"""V7.1 statistical contracts (`v71_estimator_v1`). Section 14.

The numerical primitives are REUSED from the frozen V7 measurement engine. What V7.1 adds is
a set of CONTRACTS that make an impossible number abort the evaluator instead of flowing into
a result:

  * **The experimental unit is declared, not implied.** A canonical hypothesis-family is one
    unit. Origin multiplicity, repeated fixtures and duplicated control rows may never inflate
    it; `assert_unit_not_inflated` checks the nominal count against the distinct-unit count.
  * **Every rate has an explicit denominator contract.** A rate reported without naming what
    it is a fraction of is the single easiest way to publish a misleading funnel.
  * **Range contracts.** A correlation outside [-1, 1], a rate outside [0, 1], a negative
    effective sample size or a p-value outside [0, 1] is an EVALUATOR DEFECT. It raises.
    (V6 shipped a compiler-valid rate above 1; that class of bug ends here.)
  * **Clustering is on the frozen inferential unit** and the cluster count is reported beside
    every clustered standard error, because a clustered SE on very few clusters is not a
    standard error in any useful sense.
"""
from __future__ import annotations

import math

from src.research.hypothesis_v7 import measurement as V7M
from src.research.hypothesis_v7 import pit as V7PIT

ESTIMATOR_VERSION = "v71_estimator_v1"

#: Reused frozen primitives. Restating them would let the experiments drift.
pearson = V7M.pearson
ols_residualize = V7M.ols_residualize
t_two_sided_p = V7M.t_two_sided_p
benjamini_hochberg = V7M.benjamini_hochberg
empirical_bayes = V7M.empirical_bayes
kish_effective_n = V7PIT.kish_effective_n
weight_concentration = V7PIT.weight_concentration

#: The unit of confirmatory evidence. One canonical family = one vote, whatever its origin
#: multiplicity or how many fixtures it was evaluated over.
EXPERIMENTAL_UNIT = "CANONICAL_HYPOTHESIS_FAMILY"
#: The unit standard errors are clustered on.
CLUSTER_UNIT = "MULTIPLICITY_FAMILY"

#: Denominator contracts for every rate the endpoints report. A rate whose denominator is not
#: in this table may not be published.
RATE_DENOMINATORS = {
    "measurable_rate": "canonical families in the arm's universe",
    "support_eligible_rate": "canonical families in the arm's universe",
    "oos_surviving_rate": "canonical families in the arm's universe",
    "direction_agreement": "evaluable (fold x competition) cells for the metric",
    "data_compatibility_rate": "canonical families in the arm's universe",
    "unmatched_fraction": "treated families offered to matching",
}

#: Range contracts. A value outside its interval is a defect in the evaluator, not a finding.
RANGE_CONTRACTS = {
    "correlation": (-1.0, 1.0),
    "rate": (0.0, 1.0),
    "p_value": (0.0, 1.0),
    "direction_agreement": (0.0, 1.0),
    "effective_sample": (0.0, float("inf")),
    "weight_concentration": (0.0, 1.0),
}


class EvaluatorContractViolation(Exception):
    """An impossible value reached the evaluator. The run is invalid, not merely noisy."""


def assert_in_range(kind: str, value, *, where: str = "") -> None:
    if value is None:
        return
    lo, hi = RANGE_CONTRACTS[kind]
    v = float(value)
    if math.isnan(v) or v < lo or v > hi:
        raise EvaluatorContractViolation(
            f"{kind}={value!r} outside [{lo}, {hi}]{' at ' + where if where else ''}")


def assert_rate(name: str, numerator, denominator, value) -> None:
    """A rate must name its denominator, and must equal numerator/denominator."""
    if name not in RATE_DENOMINATORS:
        raise EvaluatorContractViolation(f"rate {name!r} has no denominator contract")
    assert_in_range("rate", value, where=name)
    if denominator in (0, None):
        if value not in (0, 0.0, None):
            raise EvaluatorContractViolation(
                f"{name}: non-zero rate on an empty denominator")
        return
    if numerator > denominator:
        raise EvaluatorContractViolation(
            f"{name}: numerator {numerator} exceeds denominator {denominator}")
    if abs(float(value) - numerator / denominator) > 1e-9:
        raise EvaluatorContractViolation(
            f"{name}: reported {value} != {numerator}/{denominator}")


def assert_unit_not_inflated(nominal_n: int, distinct_units) -> None:
    """Nominal N may never exceed the number of distinct experimental units.

    This is what stops repeated control rows, origin multiplicity or repeated fixtures from
    being counted as independent evidence.
    """
    n_distinct = len(set(distinct_units))
    if nominal_n > n_distinct:
        raise EvaluatorContractViolation(
            f"nominal N={nominal_n} exceeds {n_distinct} distinct "
            f"{EXPERIMENTAL_UNIT.lower()}s: repeated rows are being counted as evidence")


def clustered_se(values, clusters):
    """Cluster-robust SE of a mean, with the cluster count returned beside it.

    The count is not optional: a clustered SE on a handful of clusters is not interpretable,
    and reporting the SE without the count invites reading it as if it were.
    """
    groups = {}
    for v, c in zip(values, clusters):
        groups.setdefault(c, []).append(float(v))
    n = sum(len(g) for g in groups.values())
    if n == 0 or len(groups) < 2:
        return (None, len(groups))
    mean = sum(sum(g) for g in groups.values()) / n
    total = sum((sum(x - mean for x in g)) ** 2 for g in groups.values())
    var = total / (n ** 2) * (len(groups) / (len(groups) - 1))
    se = math.sqrt(var) if var > 0 else 0.0
    return (se, len(groups))


def version_stamp() -> dict:
    return {"estimator_version": ESTIMATOR_VERSION,
            "primitives_source": V7M.MEASUREMENT_VERSION,
            "experimental_unit": EXPERIMENTAL_UNIT,
            "cluster_unit": CLUSTER_UNIT,
            "rate_denominators": dict(RATE_DENOMINATORS),
            "range_contracts": {k: list(v) for k, v in RANGE_CONTRACTS.items()},
            "impossible_value_aborts_the_evaluator": True,
            "cluster_count_reported_with_every_clustered_se": True}
