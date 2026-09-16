"""V8B.1 fixture-level scoring primitive (`v8b1_scorer_v1`). See research/hypothesis_engine/
V8B1_SCORER_SPEC.md for the full design rationale and reconciliation statement.

Lives in its own package (`src/research/hypothesis_v8b1/`), deliberately separate from
`src/research/hypothesis_v71/`, which is FROZEN scope belonging to V7.1's own sealed
confirmatory-run provenance chain (`V7_1_BLAST_RADIUS.json` et al.). This module calls into
`hypothesis_v71`'s existing primitives but is not itself part of that package, so V7.1's own
frozen blast-radius/provenance artifacts never need to change to accommodate it.

Answers a question V7.1's own machinery structurally cannot: did ONE hypothesis's conditional
(cohort) estimate beat its baseline estimate at ONE target fixture, in pre-T-standardized
units? V7.1's `engine.py::evaluate_cell`/`score_family` require >=20 fixtures (a fold) to
compute a Pearson correlation; this module exists because that primitive cannot be evaluated
at n=1, not because it is wrong at its own designed granularity.

Every point estimate below is constructed EXACTLY as `engine.py::_estimates` already
constructs it (same shrinkage via `recency.Recency.shrink`, same recency family, same PIT
discipline via `compiler.compile_query`). The only new arithmetic is the standardized
improvement formula in `score_fixture()`.

NO LLM NUMERIC INPUT ENTERS THIS MODULE ANYWHERE. Callers pass a canonical `IR` (resolved from
a hypothesis ID, however that ID was chosen) and a target fixture position; nothing about how
the ID was selected, nor any LLM-authored prose, is visible to this code.

ZERO SPEND. No network. No CHAMPION. Not tuned against any real target outcome: see the
synthetic proof battery in tests/research/hypothesis_v8b1/test_scorer.py, which this module's
behavior must satisfy using constructed data before it is ever pointed at a real fixture.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v71 import compiler as CO
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v7 import pit as V7PIT

SCORER_VERSION = "v8b1_scorer_v1"

#: Reused, unchanged, from the frozen V7 support gate. A cohort that would fail this at
#: fold-level fails it identically here, at fixture-level, for the same reason.
MIN_RAW_N = V7PIT.MIN_RAW_N
MIN_UNIQUE_FIXTURES = V7PIT.MIN_UNIQUE_FIXTURES
MIN_UNIQUE_TEAMS = V7PIT.MIN_UNIQUE_TEAMS
MIN_EFFECTIVE_N = V7PIT.MIN_EFFECTIVE_N
MAX_WEIGHT_CONCENTRATION = V7PIT.MAX_WEIGHT_CONCENTRATION

#: Same floor `engine.py::evaluate_cell` uses to declare a fold-cell "contrastless". Reused
#: for the identical reason: below this, dispersion is numerically indistinguishable from zero
#: and standardizing by it would be a division by (numerical) zero, not a real computation.
ZERO_VARIANCE_FLOOR = 1e-18

# ---- named, non-fabricating terminal statuses -------------------------------------------
SCORE_OK = "SCORE_OK"
SCORE_REFUSED = "SCORE_REFUSED"
SCORE_INSUFFICIENT_SUPPORT = "SCORE_INSUFFICIENT_SUPPORT"
SCORE_UNDEFINED = "SCORE_UNDEFINED"

TERMINAL_STATUSES = (SCORE_OK, SCORE_REFUSED, SCORE_INSUFFICIENT_SUPPORT, SCORE_UNDEFINED)


@dataclass(frozen=True)
class FixtureScore:
    """One hypothesis, one target fixture. `score` is populated only when `status == SCORE_OK`;
    every other field is populated whenever the corresponding computation was reached, so a
    caller can always see WHY a status was reached, never just THAT it was."""
    status: str
    score: float | None = None
    baseline_estimate: float | None = None
    cohort_estimate: float | None = None
    observed: float | None = None
    scale_var: float | None = None
    raw_improvement: float | None = None
    cohort_n: int | None = None
    baseline_n: int | None = None
    support_status: str | None = None
    reason: str = ""


def _weighted_mean(values, weights):
    tw = sum(weights)
    if tw <= 0:
        return None
    return sum(v * w for v, w in zip(values, weights)) / tw


def _weighted_variance(values, weights):
    """Weighted population variance around the WEIGHTED (unshrunk) mean. >= 0 by construction
    (a sum of squares), never negative, never requires a second pass over any other fixture."""
    tw = sum(weights)
    if tw <= 0:
        return None
    mean = _weighted_mean(values, weights)
    return sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / tw


def score_fixture(ir, index, rec_i, *, metric, terciles, axis_cache, similarity, recency,
                  capability=None) -> FixtureScore:
    """Score ONE hypothesis IR at ONE target fixture position for ONE metric.

    `recency` is the weighting FAMILY exactly as `engine.recency_family_for(ir)` would build
    it (a tuple of one or two `Recency` instances) -- callers must pass the same family the
    point estimate is meant to average over, never a single hand-picked member.
    """
    try:
        cs, bs, scales, observed = [], [], [], None
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
        # A degenerate/structurally-invalid query (e.g. IDENTICAL_COHORT_BASELINE) is caught
        # by compile_query's own pre-fold-loop assert_valid call before it ever builds a
        # CompiledQuery. This is the SAME structural fact CompiledQuery.is_degenerate() would
        # have reported had construction reached that far -- reused, not reinterpreted.
        return FixtureScore(status=SCORE_REFUSED, reason=str(e))

    # ---- support gate: reused thresholds, unchanged, evaluated at fixture level -----------
    support = V7PIT.classify_support(
        raw_n=last_q.cohort_n, unique_fixtures=len(last_q.cohort_fixtures),
        unique_teams=1, effective_n=V7PIT.kish_effective_n(last_q.cohort_weights),
        concentration=V7PIT.weight_concentration(last_q.cohort_weights), n_competitions=1)
    if support["status"] != V7PIT.SUPPORT_ADEQUATE:
        return FixtureScore(status=SCORE_INSUFFICIENT_SUPPORT,
                            cohort_n=last_q.cohort_n, baseline_n=last_q.baseline_n,
                            support_status=support["status"],
                            reason="; ".join(support["reasons"]))

    # ---- average the weighting family exactly as _estimates() does for the point estimate --
    c_hat = sum(cs) / len(cs)
    b_hat = sum(bs) / len(bs)
    scale_var = sum(scales) / len(scales)

    if scale_var is None or scale_var <= ZERO_VARIANCE_FLOOR:
        return FixtureScore(status=SCORE_UNDEFINED,
                            baseline_estimate=b_hat, cohort_estimate=c_hat, observed=observed,
                            scale_var=scale_var, cohort_n=last_q.cohort_n,
                            baseline_n=last_q.baseline_n, support_status=support["status"],
                            reason="cohort has no pre-T dispersion to standardize by "
                                  f"(scale_var={scale_var!r} <= {ZERO_VARIANCE_FLOOR})")

    baseline_sq_error = (observed - b_hat) ** 2
    cohort_sq_error = (observed - c_hat) ** 2
    raw_improvement = baseline_sq_error - cohort_sq_error
    score = raw_improvement / scale_var

    return FixtureScore(status=SCORE_OK, score=score, baseline_estimate=b_hat,
                        cohort_estimate=c_hat, observed=observed, scale_var=scale_var,
                        raw_improvement=raw_improvement, cohort_n=last_q.cohort_n,
                        baseline_n=last_q.baseline_n, support_status=support["status"])


def version_stamp() -> dict:
    return {"scorer_version": SCORER_VERSION,
            "reuses": ["compiler.compile_query", "recency.Recency.shrink",
                      "pit.classify_support", "pit.shrink_estimate"],
            "new_formula": "score(T) = ((observed-b_hat)**2 - (observed-c_hat)**2) / "
                           "weighted_variance(cohort_values, cohort_weights)",
            "sign_convention": "higher is better; positive means the cohort (conditional) "
                               "estimate was closer to the observation than the baseline, "
                               "in units of the cohort's own pre-T variance",
            "zero_variance_floor": ZERO_VARIANCE_FLOOR,
            "support_thresholds_source": V7PIT.PIT_VERSION,
            "terminal_statuses": list(TERMINAL_STATUSES),
            "llm_numeric_input": False,
            "tuned_against_real_outcomes": False,
            "reads_outcomes": "only the single target fixture's own observed value, "
                              "after selection freeze -- never used to fit any parameter"}
