"""V7 Control-B matching, weighting and balance (`v7_matching_v1`). Tasks 4-7.

Replaces reliance on two aggregate tolerance gates with a formal, outcome-blind comparability
design. The objective function may ONLY reduce imbalance in the frozen structural covariates;
no step of this module can read a historical effect, an OOS result or any confirmatory
statistic. Thresholds below are frozen BEFORE the cross-tabulation is computed.

INFERENTIAL UNIT (Task 5)
-------------------------
One LLM canonical family <-> its weighted matched control SET, with total control weight
exactly 1. A larger control pool therefore buys MATCHING FLEXIBILITY and never nominal sample
size: 399 generic hypotheses can never become 399 independent votes against ~53 LLM ones.
Effective N is computed over the resulting control weights, and a concentration cap prevents
a handful of generic controls from carrying the comparison.

MATCHING HIERARCHY (Task 4)
---------------------------
  TIER_1_EXACT      exact agreement on the full frozen coarsened key
  TIER_2_CEM        coarsened exact matching (time_scope and side relaxed)
  TIER_3_COARSE     (uses_similarity, comparator, measurability_status) only
  NO_COMPARABLE_CONTROL   no null support at any tier -- reported, never forced

ZERO SPEND. No LLM. No effects. No OOS.
"""
from __future__ import annotations

import hashlib
import json

MATCHING_VERSION = "v7_matching_v1"

# ---- frozen thresholds, set BEFORE any cross-tabulation was inspected -----------------
MIN_NULL_PER_STRATUM = 3          # a stratum needs >=3 controls to be a credible comparator
MAX_NO_COMPARABLE_FRACTION = 0.25  # >25% unmatched LLM families blocks the comparison
MAX_STANDARDIZED_DIFF = 0.25      # max |SMD| per covariate level after weighting
MAX_CONTROL_WEIGHT_SHARE = 0.25   # no single control may hold >25% of total control weight
MIN_EFFECTIVE_N = 20.0            # Kish ESS over control weights

TIER_1 = "TIER_1_EXACT"
TIER_2 = "TIER_2_CEM"
TIER_3 = "TIER_3_COARSE"
NO_MATCH = "NO_COMPARABLE_CONTROL"

#: The CORE key every tier shares. It pins the covariates from which the derived ones follow:
#: `support_risk_class` is a deterministic function of (n_conditions, uses_similarity,
#: comparator), so pinning those three at every tier balances it automatically instead of
#: leaving it to drift in the coarse tier.
CORE_KEY = ("uses_similarity", "comparator", "n_conditions", "measurability_status",
            "requires_half_resolution", "support_risk_class", "coverage_class")

#: the coarsened key at each tier, in frozen order. Each tier relaxes CONTENT granularity
#: (time_scope, then target_band) but never relaxes the core or the perspective slots.
TIER_KEYS = {
    TIER_1: CORE_KEY + ("metric_group", "target_band", "time_scope", "subject", "side"),
    TIER_2: CORE_KEY + ("metric_group", "target_band", "subject", "side"),
    TIER_3: CORE_KEY + ("metric_group", "subject", "side"),
}

#: How this hierarchy was selected. The THRESHOLDS above were frozen FIRST; the tier keys and
#: the control-pool size were then chosen as the smallest configuration meeting them, using
#: ONLY structural balance diagnostics. No outcome, effect, fold or OOS quantity was consulted
#: at any point in that selection -- the objective function is imbalance in frozen structural
#: covariates and nothing else, exactly as Task 4 permits.
SELECTION_PROVENANCE = (
    "thresholds frozen before any cross-tabulation; tier keys and control-pool size then "
    "selected to satisfy them against structural balance only; no outcome consulted")


def _key(cov: dict, fields) -> str:
    return "|".join(f"{f}={cov.get(f)}" for f in fields)


def match(llm_rows: list, null_rows: list) -> dict:
    """Match every LLM family to a weighted control set. Outcome-blind throughout.

    `llm_rows` / `null_rows` are [{"canonical_hypothesis_id", "covariates"}]. Returns the
    per-family assignment, the aggregated control weights, and the tier composition.
    """
    # index controls by every tier key once
    index = {tier: {} for tier in TIER_KEYS}
    for tier, fields in TIER_KEYS.items():
        for r in null_rows:
            index[tier].setdefault(_key(r["covariates"], fields), []).append(
                r["canonical_hypothesis_id"])

    assignments, control_weight = [], {}
    for row in sorted(llm_rows, key=lambda r: r["canonical_hypothesis_id"]):
        cov = row["covariates"]
        chosen_tier, controls = NO_MATCH, []
        for tier in (TIER_1, TIER_2, TIER_3):
            cand = sorted(index[tier].get(_key(cov, TIER_KEYS[tier]), []))
            if len(cand) >= MIN_NULL_PER_STRATUM:
                chosen_tier, controls = tier, cand
                break
        # total control weight per LLM family is EXACTLY 1 (Task 5)
        w = (1.0 / len(controls)) if controls else 0.0
        for c in controls:
            control_weight[c] = control_weight.get(c, 0.0) + w
        assignments.append({
            "canonical_hypothesis_id": row["canonical_hypothesis_id"],
            "tier": chosen_tier,
            "stratum_key": _key(cov, TIER_KEYS[chosen_tier]) if chosen_tier != NO_MATCH
            else _key(cov, TIER_KEYS[TIER_3]),
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
        "inferential_unit": ("one LLM canonical family <-> its weighted control set, "
                             "total control weight exactly 1"),
        "assignments": assignments,
        # NOT rounded: these feed the ESS and balance computations, and the invariant
        # "total control weight == n_matched" must hold exactly.
        "control_weights": dict(sorted(control_weight.items())),
    }


def effective_sample(control_weights: dict, n_null_raw: int) -> dict:
    """Kish ESS and concentration over the control weights (Task 7)."""
    w = [v for v in control_weights.values() if v > 0]
    s1, s2 = sum(w), sum(x * x for x in w)
    ess = (s1 * s1 / s2) if s2 > 0 else 0.0
    max_share = (max(w) / s1) if w else 1.0
    return {
        "raw_null_n": n_null_raw,
        "nominal_weighted_null_n": len(w),
        "total_control_weight": s1,
        "effective_n": ess,
        "max_single_control_weight": round(max(w), 6) if w else 0.0,
        "max_single_control_share": max_share,
        "concentration_ok": max_share <= MAX_CONTROL_WEIGHT_SHARE,
        "effective_n_ok": ess >= MIN_EFFECTIVE_N,
        "thresholds": {"max_control_weight_share": MAX_CONTROL_WEIGHT_SHARE,
                       "min_effective_n": MIN_EFFECTIVE_N},
        "note": ("total_control_weight equals the number of matched LLM families by "
                 "construction, so the control pool never inflates nominal N"),
    }


def _levels(rows, field):
    return sorted({str(r["covariates"].get(field)) for r in rows})


def _prop(rows, field, level, weights=None):
    """(Weighted) proportion of `rows` at `field == level`."""
    if weights is None:
        n = len(rows)
        if not n:
            return 0.0
        return sum(1 for r in rows if str(r["covariates"].get(field)) == level) / n
    tot = sum(weights.get(r["canonical_hypothesis_id"], 0.0) for r in rows)
    if tot <= 0:
        return 0.0
    hit = sum(weights.get(r["canonical_hypothesis_id"], 0.0) for r in rows
              if str(r["covariates"].get(field)) == level)
    return hit / tot


def balance(llm_rows, null_rows, control_weights, covariate_fields) -> dict:
    """Balance diagnostics per covariate LEVEL, raw and weighted (Task 6).

    For a categorical level the standardized difference uses the binomial pooled SD, which is
    the standard categorical analogue of the standardized mean difference.
    """
    import math
    out, worst = [], 0.0
    for field in covariate_fields:
        for level in sorted(set(_levels(llm_rows, field)) | set(_levels(null_rows, field))):
            p_llm = _prop(llm_rows, field, level)
            p_raw = _prop(null_rows, field, level)
            p_w = _prop(null_rows, field, level, control_weights)
            pooled = math.sqrt(((p_llm * (1 - p_llm)) + (p_w * (1 - p_w))) / 2) or 1e-9
            smd_w = abs(p_llm - p_w) / pooled
            pooled_raw = math.sqrt(((p_llm * (1 - p_llm)) + (p_raw * (1 - p_raw))) / 2) or 1e-9
            smd_raw = abs(p_llm - p_raw) / pooled_raw
            worst = max(worst, smd_w)
            out.append({"covariate": field, "level": level,
                        "llm_prop": round(p_llm, 4),
                        "null_raw_prop": round(p_raw, 4),
                        "null_weighted_prop": round(p_w, 4),
                        "smd_raw": round(smd_raw, 4),
                        "smd_weighted": round(smd_w, 4),
                        "within_threshold": smd_w <= MAX_STANDARDIZED_DIFF})
    n_bad = sum(1 for r in out if not r["within_threshold"])
    return {"max_standardized_diff": MAX_STANDARDIZED_DIFF,
            "worst_smd_weighted": round(worst, 4),
            "n_levels": len(out), "n_levels_out_of_balance": n_bad,
            "balance_ok": n_bad == 0,
            "rows": out}


def comparability_verdict(match_result, ess, bal) -> dict:
    """The frozen GO/NO-GO on Control B. Every input is outcome-blind."""
    reasons = []
    if match_result["no_comparable_fraction"] > MAX_NO_COMPARABLE_FRACTION:
        reasons.append(f"no_comparable_fraction="
                       f"{match_result['no_comparable_fraction']} > "
                       f"{MAX_NO_COMPARABLE_FRACTION}")
    if not ess["concentration_ok"]:
        reasons.append(f"max_single_control_share={ess['max_single_control_share']} > "
                       f"{MAX_CONTROL_WEIGHT_SHARE}")
    if not ess["effective_n_ok"]:
        reasons.append(f"effective_n={ess['effective_n']} < {MIN_EFFECTIVE_N}")
    if not bal["balance_ok"]:
        reasons.append(f"{bal['n_levels_out_of_balance']} covariate levels exceed "
                       f"|SMD|={MAX_STANDARDIZED_DIFF} "
                       f"(worst {bal['worst_smd_weighted']})")
    return {"control_b_comparable": not reasons,
            "reasons": reasons or ["structural comparability defensible"],
            "thresholds_frozen_before_crosstab": True,
            "depends_on_effect": False,
            "evaluated_before_oos": True}


def version_stamp() -> dict:
    return {"matching_version": MATCHING_VERSION,
            "tier_keys": {k: list(v) for k, v in TIER_KEYS.items()},
            "core_key": list(CORE_KEY),
            "selection_provenance": SELECTION_PROVENANCE,
            "min_null_per_stratum": MIN_NULL_PER_STRATUM,
            "max_no_comparable_fraction": MAX_NO_COMPARABLE_FRACTION,
            "max_standardized_diff": MAX_STANDARDIZED_DIFF,
            "max_control_weight_share": MAX_CONTROL_WEIGHT_SHARE,
            "min_effective_n": MIN_EFFECTIVE_N,
            "inferential_unit": "one LLM family <-> weighted control set, total weight 1",
            "control_pool_buys_flexibility_not_n": True,
            "objective_reads_outcomes": False,
            "frozen_before_oos": True}


def spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(version_stamp(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
