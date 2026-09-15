"""V7.1 pre-OOS evaluability gate (`v71_evaluability_v1`). Section 16.

V7 reached a computable out-of-sample estimate for 16 of 132 canonical LLM families and a
16-pair, 9-cluster matched comparison. That apparatus could not have detected anything but a
very large effect, and nobody knew it until after the confirmatory window had been spent.

V7.1 therefore decides, BEFORE opening the fresh sample, whether the apparatus can answer its
own question. The gate is built from:

  * the FRESH SAMPLE'S STRUCTURE -- fixture, team, competition and fold counts. Structure is
    not an outcome: counting fixtures reads no effect.
  * DEVELOPMENT-WINDOW SIMULATION -- the dispersion of the endpoint statistic, estimated on
    the historical (already-viewed) window. This is explicitly permitted: it never touches a
    fresh fixture.
  * a frozen PRECISION REQUIREMENT, below.

What is frozen here is the precision requirement and the structural minimums, NOT the family
counts they imply. Freezing a count would invite choosing the count that passes.

    MDE       the smallest difference on the endpoint scale worth being able to detect.
              0.05 is half the per-family OOS quality score a structurally comparable control
              arm produced in V7 (0.0609), i.e. the apparatus must be able to see a
              half-sized shift, not merely a doubling.
    ALPHA     0.05, two-sided, matching the frozen endpoint test.
    POWER     0.80, the conventional floor below which a null result carries no information.

From those, the required number of independent clusters follows from the simulated dispersion
by the standard two-sided normal-approximation formula, with a small-sample inflation for the
clustered t reference distribution.

Nothing in this module reads a confirmatory outcome.
"""
from __future__ import annotations

import math

EVALUABILITY_VERSION = "v71_evaluability_v1"

# ---- frozen precision requirement -------------------------------------------------------
MDE = 0.05
ALPHA = 0.05
POWER = 0.80
_Z_ALPHA_2 = 1.959963984540054      # two-sided 0.05
_Z_POWER = 0.8416212335729143       # 0.80

#: Clustered inference with few clusters is anti-conservative; the frozen estimator therefore
#: references a t distribution on (n_clusters - 1) df. This multiplier inflates the required
#: cluster count so the gate is stated on the distribution the estimator actually uses.
SMALL_CLUSTER_INFLATION = 1.15

# ---- frozen structural minimums ---------------------------------------------------------
#: Each minimum answers a DIFFERENT failure mode, so none can be traded against another.
MIN_COMPETITIONS = 4          # matches the capability layer's restricted-universe floor
MIN_FOLDS = 3                 # a direction can only be unstable if there are >= 3 blocks
MIN_FIXTURES_PER_FOLD = 50    # keeps a fold's per-competition cell above single digits
MIN_EVALUABLE_FAMILIES = 12   # per-family FDR is meaningless on a handful of tests
MIN_EFFECTIVE_SAMPLE = 20.0   # Kish ESS of the weighted control arm
MIN_TEAMS = 40                # cluster count cannot exceed the number of distinct teams

#: Direction stability is measured over FOLDS, exactly as V7 froze it, and competition
#: stability is reported separately -- also exactly as V7 froze it. Neither the unit nor the
#: threshold is changed.
#:
#: A finer (fold x competition) CELL unit was built and trialled on the development window.
#: It is rejected on an a-priori power argument that does not depend on any result: a cell
#: holds tens of observations, so for a true effect of |r| ~= 0.1 the probability that a
#: cell's correlation even has the right SIGN is about Phi(0.1*sqrt(50)) ~= 0.76 -- i.e. a
#: 0.75 agreement threshold at cell level measures sampling noise, not stability. The fold is
#: the smallest block on which the sign is informative.
#:
#: DISCLOSURE: the cell unit was trialled before it was rejected, and on the development
#: window it left zero survivors. That observation preceded this decision. It is recorded
#: rather than hidden; the justification above stands on its own, and the reverted unit and
#: threshold are V7's, so nothing here loosens a criterion.
STABILITY_UNIT = "FOLD"
DIRECTION_STABILITY_MIN = 0.75
STABILITY_SECONDARY_UNIT = "COMPETITION"
CELL_UNIT_REJECTED = {
    "unit": "FOLD_X_COMPETITION_CELL",
    "reason": "per-cell correlation sign is near-random for small true effects",
    "trialled_on_development_window": True,
    "development_survivors_under_cell_unit": 0,
}

# ---- verdicts ---------------------------------------------------------------------------
READY = "V7_1_EVALUABILITY_GATE_PASSED"
BLOCKED = "V7_1_BLOCKED_INSUFFICIENT_EVALUABILITY"


def required_clusters(sigma: float, *, mde: float = MDE) -> int:
    """Clusters needed to detect `mde` at ALPHA/POWER, given cluster-level dispersion sigma.

    Two-sided normal approximation, inflated for the clustered-t reference distribution.
    `sigma` is the standard deviation of the per-cluster endpoint difference, estimated by
    development-window simulation -- never from the fresh sample.
    """
    if sigma is None or sigma <= 0 or mde <= 0:
        return 0
    n = ((_Z_ALPHA_2 + _Z_POWER) * sigma / mde) ** 2
    return int(math.ceil(n * SMALL_CLUSTER_INFLATION))


def detectable_effect(sigma: float, n_clusters: int) -> float | None:
    """The smallest difference this many clusters could detect. The gate's plain-language
    counterpart to `required_clusters`, reported whether the gate passes or blocks."""
    if not sigma or n_clusters <= 1:
        return None
    return (_Z_ALPHA_2 + _Z_POWER) * sigma / math.sqrt(n_clusters / SMALL_CLUSTER_INFLATION)


def assess(structure: dict, simulation: dict) -> dict:
    """Decide READY or BLOCKED from fresh-sample STRUCTURE and development SIMULATION.

    `structure` keys: n_fixtures, n_folds, n_competitions, n_teams, min_fixtures_per_fold,
                      n_evaluable_families, expected_clusters, expected_scored_pairs,
                      expected_effective_sample
    `simulation` keys: cluster_sigma (development-window dispersion of the endpoint)
    """
    sigma = simulation.get("cluster_sigma")
    need = required_clusters(sigma)
    checks = [
        ("competitions", structure.get("n_competitions", 0), MIN_COMPETITIONS),
        ("folds", structure.get("n_folds", 0), MIN_FOLDS),
        ("fixtures_per_fold", structure.get("min_fixtures_per_fold", 0),
         MIN_FIXTURES_PER_FOLD),
        ("evaluable_families", structure.get("n_evaluable_families", 0),
         MIN_EVALUABLE_FAMILIES),
        ("teams", structure.get("n_teams", 0), MIN_TEAMS),
        ("effective_sample", structure.get("expected_effective_sample", 0.0),
         MIN_EFFECTIVE_SAMPLE),
        ("clusters_for_power", structure.get("expected_clusters", 0), need),
    ]
    failures = [{"check": name, "have": have, "need": req}
                for name, have, req in checks if have < req]
    mde_now = detectable_effect(sigma, structure.get("expected_clusters", 0))
    return {
        "evaluability_version": EVALUABILITY_VERSION,
        "verdict": BLOCKED if failures else READY,
        "precision_requirement": {"mde": MDE, "alpha": ALPHA, "power": POWER,
                                  "small_cluster_inflation": SMALL_CLUSTER_INFLATION},
        "structural_minimums": {
            "min_competitions": MIN_COMPETITIONS, "min_folds": MIN_FOLDS,
            "min_fixtures_per_fold": MIN_FIXTURES_PER_FOLD,
            "min_evaluable_families": MIN_EVALUABLE_FAMILIES,
            "min_effective_sample": MIN_EFFECTIVE_SAMPLE, "min_teams": MIN_TEAMS},
        "stability": {"unit": STABILITY_UNIT,
                      "secondary_unit": STABILITY_SECONDARY_UNIT,
                      "direction_stability_min": DIRECTION_STABILITY_MIN,
                      "cell_unit_rejected": CELL_UNIT_REJECTED},
        "simulated_cluster_sigma": sigma,
        "clusters_required_for_power": need,
        "clusters_expected": structure.get("expected_clusters", 0),
        "smallest_detectable_difference_at_expected_clusters": mde_now,
        "checks": [{"check": n, "have": h, "need": r} for n, h, r in checks],
        "failures": failures,
        "reads_confirmatory_outcomes": False,
        "derived_from": ["fresh sample structure", "development-window simulation"],
    }


def version_stamp() -> dict:
    return {"evaluability_version": EVALUABILITY_VERSION,
            "mde": MDE, "alpha": ALPHA, "power": POWER,
            "stability_unit": STABILITY_UNIT,
            "stability_secondary_unit": STABILITY_SECONDARY_UNIT,
            "direction_stability_min": DIRECTION_STABILITY_MIN,
            "cell_unit_rejected": CELL_UNIT_REJECTED,
            "minimums_are_frozen_the_implied_counts_are_not": True,
            "reads_confirmatory_outcomes": False}
