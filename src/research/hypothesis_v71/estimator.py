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

import hashlib
import math

from src.research.hypothesis_v7 import measurement as V7M
from src.research.hypothesis_v7 import pit as V7PIT

ESTIMATOR_VERSION = "v71_estimator_v2"

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


# ---- small-cluster inference (section 8 / Endpoint B) ----------------------------------
#: Endpoint B has ~8 multiplicity-family clusters. A clustered SE referenced to a normal (or
#: even a t) distribution is ANTI-CONSERVATIVE with so few clusters: the asymptotics the
#: normal approximation relies on simply have not kicked in, and a nominal p-value read off
#: that reference distribution overstates the evidence.
#:
#: FROZEN CHOICE: an EXACT, ENUMERATED cluster-level sign-flip (Rademacher wild-cluster) test.
#:   * The test statistic is the CLUSTER-MEAN aggregate of the per-cluster mean paired
#:     (treated - control) difference -- i.e. the frozen matched-treated estimand. It is NOT
#:     recomputed from raw rows, so a large control pool cannot drive precision.
#:   * The reference distribution is generated by flipping the SIGN of each cluster's
#:     contribution. With G clusters there are 2^G sign vectors; for G <= MAX_ENUMERATED_G we
#:     ENUMERATE all of them (fully deterministic, no sampling, no seed), otherwise we would
#:     fall back to a deterministic SHA-256 counter stream -- but the design has ~8 clusters,
#:     so enumeration is exact.
#:   * The two-sided p-value is the fraction of sign-flipped statistics whose magnitude is
#:     >= the observed magnitude. Under the sharp null of no effect, flipping a cluster's sign
#:     is distribution-preserving, so this p-value is exact in finite samples.
#:
#: Why sign-flip rather than a wild-cluster-t bootstrap: with a handful of clusters the exact
#: enumeration is both cheaper and free of any bootstrap-sampling noise, and it needs no
#: variance estimate that is itself unstable at G=8. The trade-off is that the sign-flip test
#: assumes the per-cluster contributions are (under the null) symmetric about zero; that is
#: exactly the assumption the paired treated-minus-control construction is built to satisfy.
MAX_ENUMERATED_G = 20
SIGN_FLIP_MIN_CLUSTERS = 3
SMALL_CLUSTER_METHOD = "EXACT_ENUMERATED_CLUSTER_SIGN_FLIP"


class InferenceRefused(Exception):
    """Small-cluster inference cannot be stated on this input. Fails closed."""


def cluster_means(values, clusters):
    """The per-cluster mean of `values`, keyed and returned in sorted cluster order.

    This is the ONLY reduction from rows to clusters. Everything downstream operates on these
    G numbers, so the raw row count (and therefore any control-pool size) cannot influence the
    inference: precision is a function of G and the between-cluster dispersion alone.
    """
    groups = {}
    for v, c in zip(values, clusters):
        groups.setdefault(c, []).append(float(v))
    return [(c, sum(g) / len(g)) for c, g in sorted(groups.items())]


def sign_flip_test(values, clusters):
    """Exact enumerated cluster sign-flip test of the sharp null 'mean cluster effect == 0'.

    Returns a dict with the point estimate (unchanged frozen estimand), the cluster count, the
    exact two-sided p-value, and the enumeration size. Fails closed on an impossible input.
    """
    cm = cluster_means(values, clusters)
    g = len(cm)
    if g < SIGN_FLIP_MIN_CLUSTERS:
        # Below three clusters there is no meaningful reference distribution; report the
        # estimate with an explicitly limited inferential status rather than a fabricated p.
        est = (sum(m for _c, m in cm) / g) if g else None
        return {"method": SMALL_CLUSTER_METHOD, "n_clusters": g,
                "point_estimate": est, "p_value": None,
                "inference_status": "INSUFFICIENT_CLUSTERS_FOR_INFERENCE",
                "enumerated": False, "n_sign_vectors": 0}
    means = [m for _c, m in cm]
    observed = sum(means) / g
    if math.isnan(observed):
        raise InferenceRefused("cluster-mean statistic is NaN")

    if g <= MAX_ENUMERATED_G:
        total = 1 << g
        ge = 0
        obs_abs = abs(observed)
        for mask in range(total):
            s = 0.0
            for i in range(g):
                s += means[i] if (mask >> i) & 1 else -means[i]
            if abs(s / g) >= obs_abs - 1e-15:
                ge += 1
        p = ge / total
        enumerated, n_vec = True, total
    else:                                          # not reached at G~8; deterministic fallback
        n_vec = 100000
        ge = 0
        obs_abs = abs(observed)
        for k in range(n_vec):
            s = 0.0
            for i in range(g):
                bit = int.from_bytes(
                    hashlib.sha256(f"{k}|{i}".encode()).digest()[:1], "big") & 1
                s += means[i] if bit else -means[i]
            if abs(s / g) >= obs_abs - 1e-15:
                ge += 1
        p = ge / n_vec
        enumerated = False

    assert_in_range("p_value", p, where="sign-flip p")
    return {"method": SMALL_CLUSTER_METHOD, "n_clusters": g,
            "point_estimate": observed, "p_value": p,
            "inference_status": "EXACT" if enumerated else "DETERMINISTIC_APPROX",
            "enumerated": enumerated, "n_sign_vectors": n_vec,
            "cluster_means": [round(m, 10) for m in means]}


def small_cluster_inference(values, clusters):
    """Endpoint-B small-cluster inference wrapper: the exact sign-flip p-value alongside the
    clustered SE and cluster count. The SE is reported for descriptive comparison ONLY; the
    frozen p-value is the sign-flip one, never the normal-approximation SE ratio."""
    se, _n = clustered_se(values, clusters)
    flip = sign_flip_test(values, clusters)
    return {
        "primary_p_value": flip["p_value"],
        "primary_method": flip["method"],
        "inference_status": flip["inference_status"],
        "n_clusters": flip["n_clusters"],
        "point_estimate": flip["point_estimate"],
        "clustered_se_descriptive_only": se,
        "normal_approx_p_is_not_used": True,
        "enumeration": {"enumerated": flip["enumerated"],
                        "n_sign_vectors": flip["n_sign_vectors"]},
    }


def version_stamp() -> dict:
    return {"estimator_version": ESTIMATOR_VERSION,
            "primitives_source": V7M.MEASUREMENT_VERSION,
            "experimental_unit": EXPERIMENTAL_UNIT,
            "cluster_unit": CLUSTER_UNIT,
            "rate_denominators": dict(RATE_DENOMINATORS),
            "range_contracts": {k: list(v) for k, v in RANGE_CONTRACTS.items()},
            "small_cluster_method": SMALL_CLUSTER_METHOD,
            "small_cluster_max_enumerated_clusters": MAX_ENUMERATED_G,
            "small_cluster_min_clusters_for_inference": SIGN_FLIP_MIN_CLUSTERS,
            "normal_approximation_p_value_is_not_the_primary": True,
            "raw_control_pool_n_cannot_drive_precision": True,
            "impossible_value_aborts_the_evaluator": True,
            "cluster_count_reported_with_every_clustered_se": True}
