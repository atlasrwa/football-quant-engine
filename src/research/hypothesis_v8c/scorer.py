"""V8C fixture scorer (`v8c_scorer_v1`) -- successor to the frozen `hypothesis_v8b2.scorer`.

The ONLY behavioural change is which compiler it calls:

    v8b2.scorer -> hypothesis_v71.compiler   (cross-competition profile mean vs a different
                                              competition's terciles -- P1 PROFILE-COMP)
    v8c.scorer  -> hypothesis_v8c.compiler   (competition-coherent profile, same semantic the
                                              V8C pre-T classifier uses)

This is not an optional tidy-up: if the pre-T classifier used the corrected compiler and the
post-T scorer used the frozen one, they would disagree about which prior matches are in the
cohort, and the PRE_T_EVALUABLE => SCORE_OK consistency invariant would break for every
opponent-profile hypothesis. ONE profile semantic must run end to end.

Thresholds, formula, sign convention, scale floor, support gate and terminal statuses are
IMPORTED UNCHANGED from the frozen V8B.2 scorer. No threshold is touched -- and none may be,
having seen any score direction or magnitude.

ZERO SPEND. Reads a target outcome ONLY through `compile_query`, after the selection freeze.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import pit as V7PIT
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v8b2 import scorer as V8B2SC
from src.research.hypothesis_v8b2 import support as SUP
from src.research.hypothesis_v8c import compiler as CO

SCORER_VERSION = "v8c_scorer_v1"

# Frozen, imported -- never restated, so they cannot drift.
FixtureScore = V8B2SC.FixtureScore
ZERO_VARIANCE_FLOOR = V8B2SC.ZERO_VARIANCE_FLOOR
SCORE_OK = V8B2SC.SCORE_OK
SCORE_REFUSED = V8B2SC.SCORE_REFUSED
SCORE_INSUFFICIENT_SUPPORT = V8B2SC.SCORE_INSUFFICIENT_SUPPORT
SCORE_UNDEFINED = V8B2SC.SCORE_UNDEFINED
TERMINAL_STATUSES = V8B2SC.TERMINAL_STATUSES
_weighted_mean = V8B2SC._weighted_mean
_weighted_variance = V8B2SC._weighted_variance

#: The exact refusal string the target-outcome branch emits. The pre-T consistency invariant
#: references THIS constant rather than a copied literal.
OBSERVED_UNAVAILABLE_REASON = "observed value or environment mean unavailable"


def unique_opponents_of_cohort(ir, index, rec_i, cohort_fixtures) -> int:
    """Unchanged from V8B.2 -- distinct canonical opponent identities in the cohort."""
    return V8B2SC.unique_opponents_of_cohort(ir, index, rec_i, cohort_fixtures)


def score_fixture(ir, index, rec_i, *, metric, terciles, axis_cache, similarity, recency,
                  capability=None) -> FixtureScore:
    """Score ONE hypothesis IR at ONE target fixture. Identical to the frozen V8B.2 scorer
    except that the compiler is the competition-coherent V8C successor."""
    try:
        cs, bs, scales, observed = [], [], [], None
        last_q = None
        for w in recency:
            q = CO.compile_query(ir, index, rec_i, metric=metric, terciles=terciles,
                                 axis_cache=axis_cache, similarity=similarity, recency=w,
                                 capability=capability, collect_fixtures=True)
            if q.is_degenerate():
                return FixtureScore(status=SCORE_REFUSED,
                                    reason="cohort and baseline read the same observations "
                                           "with the same weighting at this fixture")
            if q.observed is None or q.environment_mean is None:
                return FixtureScore(status=SCORE_REFUSED, reason=OBSERVED_UNAVAILABLE_REASON)
            cw, bw = sum(q.cohort_weights), sum(q.baseline_weights)
            if cw <= 0 or bw <= 0:
                return FixtureScore(status=SCORE_REFUSED, reason="degenerate weights")
            c_mean = _weighted_mean(q.cohort_values, q.cohort_weights)
            b_mean = _weighted_mean(q.baseline_values, q.baseline_weights)
            c_hat = w.shrink(c_mean, q.cohort_n, q.environment_mean)
            b_hat = w.shrink(b_mean, q.baseline_n, q.environment_mean)
            scales.append(_weighted_variance(q.cohort_values, q.cohort_weights))
            cs.append(c_hat)
            bs.append(b_hat)
            observed = q.observed
            last_q = q
    except (CO.CompileRefused, SIM.SimilarityRefused) as e:
        return FixtureScore(status=SCORE_REFUSED, reason=str(e))
    except INV.InvariantViolation as e:
        return FixtureScore(status=SCORE_REFUSED, reason=str(e))

    uniq_opp = unique_opponents_of_cohort(ir, index, rec_i, last_q.cohort_fixtures)
    support = SUP.classify_fixture_support(
        raw_n=last_q.cohort_n,
        unique_fixtures=len(last_q.cohort_fixtures),
        unique_opponents=uniq_opp,
        effective_n=V7PIT.kish_effective_n(last_q.cohort_weights),
        max_weight_share=V7PIT.weight_concentration(last_q.cohort_weights))
    if support.status != SUP.SUPPORT_ADEQUATE:
        return FixtureScore(status=SCORE_INSUFFICIENT_SUPPORT,
                            cohort_n=last_q.cohort_n, baseline_n=last_q.baseline_n,
                            unique_opponents=uniq_opp, support_status=support.status,
                            support_failures=support.failures,
                            reason="; ".join(f"{f['field']}: have={f.get('have')} "
                                             f"need={f.get('need', f.get('limit'))}"
                                             for f in support.failures))

    c_hat = sum(cs) / len(cs)
    b_hat = sum(bs) / len(bs)
    scale_var = sum(scales) / len(scales)

    if scale_var is None or scale_var <= ZERO_VARIANCE_FLOOR:
        return FixtureScore(status=SCORE_UNDEFINED, baseline_estimate=b_hat,
                            cohort_estimate=c_hat, observed=observed, scale_var=scale_var,
                            cohort_n=last_q.cohort_n, baseline_n=last_q.baseline_n,
                            unique_opponents=uniq_opp, support_status=support.status,
                            reason=f"cohort has no pre-T dispersion to standardize by "
                                   f"(scale_var={scale_var!r} <= {ZERO_VARIANCE_FLOOR})")

    raw_improvement = (observed - b_hat) ** 2 - (observed - c_hat) ** 2
    return FixtureScore(status=SCORE_OK, score=raw_improvement / scale_var,
                        baseline_estimate=b_hat, cohort_estimate=c_hat, observed=observed,
                        scale_var=scale_var, raw_improvement=raw_improvement,
                        cohort_n=last_q.cohort_n, baseline_n=last_q.baseline_n,
                        unique_opponents=uniq_opp, support_status=support.status,
                        support_failures=())


def version_stamp() -> dict:
    return {"scorer_version": SCORER_VERSION,
            "successor_to": V8B2SC.SCORER_VERSION,
            "only_behavioral_change": "calls the competition-coherent v8c compiler",
            "compiler": CO.COMPILER_VERSION,
            "thresholds_changed": False,
            "formula_changed": False,
            "support_classifier": SUP.version_stamp()["fixture_support_version"],
            "zero_variance_floor": ZERO_VARIANCE_FLOOR,
            "terminal_statuses": list(TERMINAL_STATUSES),
            "observed_unavailable_reason": OBSERVED_UNAVAILABLE_REASON,
            "one_profile_semantic_end_to_end": True}
