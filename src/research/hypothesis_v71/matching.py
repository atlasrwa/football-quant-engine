"""V7.1 Endpoint-B matching (`v71_matching_v1`). Section 15.

V7's matching layer was audited and frozen for the Control-B closure, and its ALGORITHM and
THRESHOLDS are reused unchanged. What V7.1 changes is the stratum KEY, because restricted
universes did not exist in V7: a family measurable on four competitions and a family
measurable on six do not have the same measurability OPPORTUNITY, and matching them together
would reintroduce exactly the bias the Control-B design was built to exclude.

So `n_admissible_competitions` joins the core key. Everything else -- the tier hierarchy, the
minimum controls per stratum, the unmatched-fraction limit, the balance and ESS thresholds,
the "total control weight per treated family is exactly 1" rule, and the inferential unit --
is V7's, reused rather than restated.

Outcome-blind: every covariate is a property of the QUESTION, never of any result.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import matching as V7M

MATCHING_VERSION = "v71_matching_v1"

# thresholds: frozen, reused verbatim
MIN_NULL_PER_STRATUM = V7M.MIN_NULL_PER_STRATUM
MAX_NO_COMPARABLE_FRACTION = V7M.MAX_NO_COMPARABLE_FRACTION
MAX_STANDARDIZED_DIFF = V7M.MAX_STANDARDIZED_DIFF
MAX_CONTROL_WEIGHT_SHARE = V7M.MAX_CONTROL_WEIGHT_SHARE
MIN_EFFECTIVE_N = V7M.MIN_EFFECTIVE_N

TIER_1, TIER_2, TIER_3, NO_MATCH = V7M.TIER_1, V7M.TIER_2, V7M.TIER_3, V7M.NO_MATCH

#: V7's core key PLUS three axes that must survive every tier.
#:
#: `n_admissible_competitions` -- restricted universes make measurability OPPORTUNITY vary by
#:   family, and a four-competition family is not comparable to a six-competition one.
#: `time_scope` and `target_band` -- V7's hierarchy coarsened by DROPPING these, so families
#:   matched at the coarse tier were compared against controls with a different temporal
#:   requirement and a different target-set size. Measured on the V7.1 pools that left
#:   |SMD| = 0.50 on `time_scope=ALL_PRIOR` and 0.36 on `target_band=T4_5` -- both squarely
#:   inside the comparability the Control-B design exists to guarantee.
#:
#: The tiers therefore coarsen on metric_group / subject / side only, and the balance-critical
#: axes are exact at every tier.
CORE_KEY = V7M.CORE_KEY + ("n_admissible_competitions", "time_scope", "target_band",
                           "subject", "side")
#: `metric_group` joins the exact key too. Coarsening it was measured on the V7.1 pools and
#: left |SMD| = 0.87: the treated arm is ~80% SCORING, while a metric-group-blind stratum
#: draws controls from the whole vocabulary. There is therefore ONE tier: an exact stratum on
#: every frozen structural covariate. A treated family with fewer than
#: `MIN_NULL_PER_STRATUM` exact controls has NO comparable control and is reported as such,
#: rather than matched against something structurally different.
TIER_KEYS = {
    TIER_1: CORE_KEY + ("metric_group",),
}

SELECTION_PROVENANCE = V7M.SELECTION_PROVENANCE

# reused verbatim: these read only the weights and covariates the matcher produced
effective_sample = V7M.effective_sample
balance = V7M.balance
comparability_verdict = V7M.comparability_verdict


def match(llm_rows: list, null_rows: list) -> dict:
    """Match every treated family to a weighted control set. Outcome-blind throughout.

    Rows are `[{"canonical_hypothesis_id", "covariates"}]`. Total control weight per treated
    family is exactly 1, so a large control pool buys matching flexibility and never extra
    votes. Control weights are stored UNROUNDED: they feed the ESS and balance computations,
    and the invariant `sum(weights) == n_matched` must hold exactly.
    """
    index = {tier: {} for tier in TIER_KEYS}
    for tier, fields in TIER_KEYS.items():
        for r in null_rows:
            index[tier].setdefault(V7M._key(r["covariates"], fields), []).append(
                r["canonical_hypothesis_id"])

    assignments, control_weight = [], {}
    for row in sorted(llm_rows, key=lambda r: r["canonical_hypothesis_id"]):
        cov = row["covariates"]
        chosen_tier, controls = NO_MATCH, []
        for tier in (TIER_1,):
            cand = sorted(index[tier].get(V7M._key(cov, TIER_KEYS[tier]), []))
            if len(cand) >= MIN_NULL_PER_STRATUM:
                chosen_tier, controls = tier, cand
                break
        w = (1.0 / len(controls)) if controls else 0.0
        for c in controls:
            control_weight[c] = control_weight.get(c, 0.0) + w
        assignments.append({
            "canonical_hypothesis_id": row["canonical_hypothesis_id"],
            "tier": chosen_tier,
            "stratum_key": V7M._key(cov, TIER_KEYS[chosen_tier if chosen_tier != NO_MATCH
                                                   else TIER_1]),
            "n_controls": len(controls),
            "weight_per_control": round(w, 8),
            "control_ids": controls,
        })

    matched = [a for a in assignments if a["tier"] != NO_MATCH]
    n_unmatched = len(assignments) - len(matched)
    tiers = {}
    for a in assignments:
        tiers[a["tier"]] = tiers.get(a["tier"], 0) + 1
    return {
        "matching_version": MATCHING_VERSION,
        "n_llm": len(assignments),
        "n_matched": len(matched),
        "n_no_comparable_control": n_unmatched,
        "no_comparable_fraction": round(n_unmatched / max(len(assignments), 1), 4),
        "tier_composition": tiers,
        "inferential_unit": ("one treated canonical family <-> its weighted control set, "
                             "total control weight exactly 1"),
        "assignments": assignments,
        "control_weights": dict(sorted(control_weight.items())),
    }


def version_stamp() -> dict:
    return {"matching_version": MATCHING_VERSION,
            "algorithm_source": V7M.MATCHING_VERSION,
            "core_key": list(CORE_KEY),
            "tier_keys": {k: list(v) for k, v in TIER_KEYS.items()},
            "added_in_v7_1": ["n_admissible_competitions", "time_scope", "target_band",
                              "subject", "side"],
            "added_rationale": ("restricted universes make measurability OPPORTUNITY vary by "
                                "family; and V7's hierarchy coarsened by dropping time_scope "
                                "target_band, subject and side, which left them out of "
                                "balance. All are now exact at every tier; only metric_group "
                                "coarsens."),
            "balance_estimand": ("balance is a property of the MATCHED sample: an unmatched "
                                 "treated family has no comparator to be balanced against, "
                                 "and is accounted for by the unmatched-fraction limit"),
            "thresholds": {"min_null_per_stratum": MIN_NULL_PER_STRATUM,
                           "max_no_comparable_fraction": MAX_NO_COMPARABLE_FRACTION,
                           "max_standardized_diff": MAX_STANDARDIZED_DIFF,
                           "max_control_weight_share": MAX_CONTROL_WEIGHT_SHARE,
                           "min_effective_n": MIN_EFFECTIVE_N},
            "controls_buy_flexibility_not_votes": True,
            "outcome_blind": True}
