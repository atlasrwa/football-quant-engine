"""V8B.2 fixture-level deterministic scorer (`v8b2_scorer_v1`).

Narrowly-scoped SUCCESSOR to the frozen `hypothesis_v8b1.scorer` (which is NOT modified). The
ONLY behavioral change is the support gate:

  * V8B.1 called `V7PIT.classify_support(..., unique_teams=1, ...)`, and V7.1's gate required
    `unique_teams >= 6` -> `SCORE_OK` structurally unreachable at the fixture level.
  * V8B.2 computes `unique_opponents` (the fixture-level diversity analogue -- distinct
    canonical opponent identities the cohort entity actually faced, PIT-safe) and gates it with
    `support.classify_fixture_support(...)` (`v8b2_fixture_support_v1`).

EVERYTHING ELSE is byte-for-byte the same computation as the frozen V8B.1 scorer: the same
compiler (`compile_query`), the same shrinkage / recency family averaging, the same scale
(`_weighted_variance`), the same NULL/degeneracy/scale-floor handling, the same
higher-is-better standardized-improvement formula, the same sign convention. Reason reporting
is upgraded to list ONLY the actual failing predicates (via FixtureSupport.failures).

NO LLM NUMERIC INPUT. ZERO SPEND. No network. No CHAMPION. Reads a target outcome ONLY through
`compiler.compile_query` (the single seal-crossing call), exactly as V8B.1 did, and only for
the one target fixture's own observed value.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v71 import compiler as CO
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v7 import pit as V7PIT
from src.research.hypothesis_v8b2 import support as SUP

SCORER_VERSION = "v8b2_scorer_v1"

ZERO_VARIANCE_FLOOR = 1e-18

SCORE_OK = "SCORE_OK"
SCORE_REFUSED = "SCORE_REFUSED"
SCORE_INSUFFICIENT_SUPPORT = "SCORE_INSUFFICIENT_SUPPORT"
SCORE_UNDEFINED = "SCORE_UNDEFINED"
TERMINAL_STATUSES = (SCORE_OK, SCORE_REFUSED, SCORE_INSUFFICIENT_SUPPORT, SCORE_UNDEFINED)


@dataclass(frozen=True)
class FixtureScore:
    """One hypothesis, one target fixture. `score` is populated only when status==SCORE_OK;
    every other field is populated whenever its computation was reached."""
    status: str
    score: float | None = None
    baseline_estimate: float | None = None
    cohort_estimate: float | None = None
    observed: float | None = None
    scale_var: float | None = None
    raw_improvement: float | None = None
    cohort_n: int | None = None
    baseline_n: int | None = None
    unique_opponents: int | None = None
    support_status: str | None = None
    support_failures: tuple = ()
    reason: str = ""


def _weighted_mean(values, weights):
    tw = sum(weights)
    if tw <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights)) / tw


def _weighted_variance(values, weights):
    tw = sum(weights)
    if tw <= 0:
        return None
    mean = _weighted_mean(values, weights)
    return sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / tw


def unique_opponents_of_cohort(ir, index, rec_i, cohort_fixtures) -> int:
    """Count DISTINCT canonical opponent identities contributing to the fixture-level cohort.

    For the cohort entity (the entity whose PIT history forms the cohort -- the subject for a
    subject cohort, the fixture opponent for an opponent-baseline cohort), walk its PIT-safe
    prior entries (strictly before the target kickoff, guaranteed by `prior_entries`) and, for
    each entry that belongs to one of the cohort's own contributing fixtures, take the opponent
    relative to that entity. The opponent id is entry[4] = away_id if the entity was home else
    home_id (canonical string id), so both home and away historical rows are handled and the
    entity itself is never counted. Distinct ids only; unresolved/None never counted.
    """
    rec = index.recs[rec_i]
    subject_id = str(rec.home_id) if ir.subject == "HOME_TEAM" else str(rec.away_id)
    # cohort entity mirrors compiler._entity_id for the cohort selector's role.
    role = ir.cohort.entity_role
    if role == "SUBJECT":
        entity_id = subject_id
    elif role == "FIXTURE_OPPONENT":
        entity_id = str(rec.away_id) if str(rec.home_id) == subject_id else str(rec.home_id)
    else:
        # COMPETITION_ENVIRONMENT etc. -- no per-opponent cohort; diversity is not applicable.
        return 0
    want_fixtures = set(str(f) for f in (cohort_fixtures or ()))
    if not want_fixtures:
        return 0
    opponents = set()
    for e in index.prior_entries(entity_id, rec_i):     # PIT-safe: strictly before target
        rec_idx, _kick, _comp, _is_home, opponent_id = e
        if str(index.recs[rec_idx].fixture_id) not in want_fixtures:
            continue
        if opponent_id is None:
            continue
        oid = str(opponent_id)
        if oid == str(entity_id):        # never count the entity itself
            continue
        opponents.add(oid)
    return len(opponents)


def score_fixture(ir, index, rec_i, *, metric, terciles, axis_cache, similarity, recency,
                  capability=None) -> FixtureScore:
    """Score ONE hypothesis IR at ONE target fixture position for ONE metric. See module
    docstring: identical to the frozen V8B.1 scorer except the support gate uses the
    fixture-level `unique_opponents` diversity analogue."""
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
                return FixtureScore(status=SCORE_REFUSED,
                                    reason="observed value or environment mean unavailable")
            cw, bw = sum(q.cohort_weights), sum(q.baseline_weights)
            if cw <= 0 or bw <= 0:
                return FixtureScore(status=SCORE_REFUSED, reason="degenerate weights")
            c_mean = _weighted_mean(q.cohort_values, q.cohort_weights)
            b_mean = _weighted_mean(q.baseline_values, q.baseline_weights)
            c_hat = w.shrink(c_mean, q.cohort_n, q.environment_mean)
            b_hat = w.shrink(b_mean, q.baseline_n, q.environment_mean)
            scale_var = _weighted_variance(q.cohort_values, q.cohort_weights)
            cs.append(c_hat)
            bs.append(b_hat)
            scales.append(scale_var)
            observed = q.observed
            last_q = q
    except (CO.CompileRefused, SIM.SimilarityRefused) as e:
        return FixtureScore(status=SCORE_REFUSED, reason=str(e))
    except INV.InvariantViolation as e:
        return FixtureScore(status=SCORE_REFUSED, reason=str(e))

    # ---- fixture-level support gate: unique_opponents (NOT unique_teams) ------------------
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
                            unique_opponents=uniq_opp,
                            support_status=support.status,
                            support_failures=support.failures,
                            reason="; ".join(f"{f['field']}: have={f.get('have')} "
                                             f"need={f.get('need', f.get('limit'))}"
                                             for f in support.failures))

    # ---- average the recency family exactly as the frozen scorer does ---------------------
    c_hat = sum(cs) / len(cs)
    b_hat = sum(bs) / len(bs)
    scale_var = sum(scales) / len(scales)

    if scale_var is None or scale_var <= ZERO_VARIANCE_FLOOR:
        return FixtureScore(status=SCORE_UNDEFINED,
                            baseline_estimate=b_hat, cohort_estimate=c_hat, observed=observed,
                            scale_var=scale_var, cohort_n=last_q.cohort_n,
                            baseline_n=last_q.baseline_n, unique_opponents=uniq_opp,
                            support_status=support.status,
                            reason=f"cohort has no pre-T dispersion to standardize by "
                                   f"(scale_var={scale_var!r} <= {ZERO_VARIANCE_FLOOR})")

    baseline_sq_error = (observed - b_hat) ** 2
    cohort_sq_error = (observed - c_hat) ** 2
    raw_improvement = baseline_sq_error - cohort_sq_error
    score = raw_improvement / scale_var

    return FixtureScore(status=SCORE_OK, score=score, baseline_estimate=b_hat,
                        cohort_estimate=c_hat, observed=observed, scale_var=scale_var,
                        raw_improvement=raw_improvement, cohort_n=last_q.cohort_n,
                        baseline_n=last_q.baseline_n, unique_opponents=uniq_opp,
                        support_status=support.status, support_failures=())


def version_stamp() -> dict:
    return {"scorer_version": SCORER_VERSION,
            "successor_to": "v8b1_scorer_v1",
            "only_behavioral_change": "support gate uses fixture-level unique_opponents "
                                      "instead of V7.1 pooled-unit unique_teams",
            "support_classifier": SUP.version_stamp()["fixture_support_version"],
            "reuses_unchanged": ["compiler.compile_query", "recency.Recency.shrink",
                                 "pit.kish_effective_n", "pit.weight_concentration"],
            "new_formula": "score(T) = ((observed-b_hat)**2 - (observed-c_hat)**2) / "
                           "weighted_variance(cohort_values, cohort_weights)",
            "sign_convention": "higher is better",
            "zero_variance_floor": ZERO_VARIANCE_FLOOR,
            "terminal_statuses": list(TERMINAL_STATUSES),
            "llm_numeric_input": False,
            "reads_outcomes": "only the single target fixture's own observed value, via "
                              "compiler.compile_query, after selection freeze"}
