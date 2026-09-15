"""V7 confirmatory OOS measurement engine (`v7_measurement_v1`).

Executes the ALREADY-FROZEN V7 design. It adds no design freedom that the frozen artifacts
settle, and every parameter it must supply that the frozen artifacts do NOT settle is declared
in `engine_spec()` and hashed BEFORE the first effect is computed. The report marks each entry
PREREGISTERED or ENGINE_LEVEL.

COMPILATION (frozen `analysis_spec.VALID_COMPARATORS` semantics, taken literally)
--------------------------------------------------------------------------------
For hypothesis H, metric m, fold f, validation fixture F, with subject S = home or away per
H.SUBJECT and perspective per H.SIDE (FOR = S's own value, AGAINST = S's opponent's value):

    PIT history      = corpus records with kickoff_unix STRICTLY < F.kickoff_unix
    env              = competition-environment mean of m over PIT history  (shrinkage prior,
                       frozen `pit.SHRINKAGE_PRIOR = TEAM_COMPETITION_BASELINE`)
    B (baseline)     = shrink(S's baseline-set mean, n, env, k=pit.SHRINKAGE_STRENGTH_K)
    C (cohort)       = shrink(S's cohort-set  mean, n, env, k=pit.SHRINKAGE_STRENGTH_K)
    signal           = C - B
    outcome_residual = observed(F, m) - B

Both C and B are shrunk toward the SAME prior, so whenever the cohort set equals the baseline
set the compiler yields signal == 0 EXACTLY. That is not an assertion about any hypothesis: it
is what the frozen comparator definition produces, and a zero-variance signal is assigned
`TAUTOLOGICAL` by rule (`outcomes.TERMINAL_STATES`).

Baseline / cohort sets by frozen comparator:
  SUBJECT_OVERALL_BASELINE          B = all prior;         C = all prior under CONDITIONS,
                                                               windowed by TIME_SCOPE
  SUBJECT_VENUE_BASELINE            B = prior at F's venue; C = same, under CONDITIONS/window
  SUBJECT_RECENT_VS_LONG_BASELINE   B = all prior undecayed; C = time-DECAYED weighting of the
                                    same observations, at EACH frozen half-life
                                    (`pit.TIME_DECAY_HALFLIVES_DAYS`), both reported, never
                                    selected (frozen `REWEIGHTING_COMPARATORS` flag)

ZERO SPEND. No LLM. No Bedrock. No CHAMPION. No p_model.
"""
from __future__ import annotations

import hashlib
import json
import math

MEASUREMENT_VERSION = "v7_measurement_v1"

# ---------------------------------------------------------------------------------------
# ENGINE_LEVEL parameters: NOT settled by any frozen artifact. Declared and hashed BEFORE the
# first effect is computed. Chosen as conventional defaults, never tuned to a result.
# ---------------------------------------------------------------------------------------
#: fraction of evaluable folds that must share the effect's sign for "direction-stable"
DIRECTION_STABILITY_MIN = 0.75
#: |shrunk OOS quality score| below this counts as no effect ("non-trivial" in the frozen
#: promotion rule, which states the requirement but not the number)
NONTRIVIAL_ABS_EFFECT_MIN = 0.05
#: |development-window effect| at or above this is "a large in-sample effect", used ONLY to
#: separate OOS_FAIL (large in sample, gone OOS) from OOS_NO_EFFECT (never there)
DEV_EFFECT_LARGE = 0.15
#: multi-metric hypotheses: each metric is measured separately and the hypothesis score is the
#: equal-weight mean over its measurable metrics; per-metric results are preserved
MULTI_METRIC_AGGREGATION = "EQUAL_WEIGHT_MEAN_OVER_METRICS"
#: support is classified per (hypothesis, metric, fold) cohort, matching classify_support's
#: per-cohort signature
SUPPORT_LEVEL = "PER_HYPOTHESIS_METRIC_FOLD"
#: per-hypothesis p-value: two-sided t-test on the fold-level effects (df = n_folds - 1)
PVALUE_METHOD = "TWO_SIDED_T_ON_FOLD_EFFECTS"
#: opponent-profile banding: terciles of the competition's PIT distribution of team means
PROFILE_BANDING = "PIT_COMPETITION_TERCILES"
#: empirical-Bayes shrinkage of the per-hypothesis score toward its multiplicity-family mean
EB_SHRINKAGE = "EB_RELIABILITY_WEIGHTED_TOWARD_FAMILY_MEAN"

HIGH, MID, LOW = "HIGH", "MID", "LOW"


def engine_spec() -> dict:
    """Everything the engine pins that the frozen artifacts do not. Hashed before execution."""
    return {
        "measurement_version": MEASUREMENT_VERSION,
        "preregistered_inputs": {
            "comparator_semantics": "analysis_spec.VALID_COMPARATORS (frozen)",
            "support_rules": "pit.classify_support thresholds (frozen)",
            "shrinkage_k": "pit.SHRINKAGE_STRENGTH_K (frozen)",
            "shrinkage_prior": "pit.SHRINKAGE_PRIOR = TEAM_COMPETITION_BASELINE (frozen)",
            "decay_halflives": "pit.TIME_DECAY_HALFLIVES_DAYS (frozen, both reported)",
            "similarity": "similarity.* dimensions/scaling/k/tie-break (frozen)",
            "folds": "walkforward.build_folds (frozen)",
            "confounder_plan": "analysis_spec.CONFOUNDER_PLAN by family (frozen)",
            "multiplicity": "BH-FDR per family at q=0.10 + EB shrinkage (frozen)",
            "terminal_states": "outcomes.TERMINAL_STATES (frozen)",
            "endpoints": "endpoints.END_TO_END / CONDITIONAL_SIGNAL (frozen)",
            "matching_weights": "matching.match frozen weights (frozen, reused verbatim)",
        },
        "engine_level_parameters": {
            "signal_construction": "signal = C - B; outcome_residual = observed - B",
            "standardized_effect": ("Pearson correlation between confounder-residualized "
                                    "signal and confounder-residualized outcome_residual, "
                                    "per fold"),
            "oos_quality_score": ("mean over evaluable folds of the standardized effect, "
                                  "multiplied by the fold direction-agreement rate"),
            "direction_stability_min": DIRECTION_STABILITY_MIN,
            "nontrivial_abs_effect_min": NONTRIVIAL_ABS_EFFECT_MIN,
            "dev_effect_large": DEV_EFFECT_LARGE,
            "multi_metric_aggregation": MULTI_METRIC_AGGREGATION,
            "support_level": SUPPORT_LEVEL,
            "pvalue_method": PVALUE_METHOD,
            "profile_banding": PROFILE_BANDING,
            "eb_shrinkage": EB_SHRINKAGE,
            "confounder_residualization": ("OLS on the frozen per-family confounder design "
                                           "(venue indicator, competition one-hots, opponent "
                                           "PIT strength on the metric, subject baseline B, "
                                           "subject PIT card rate, season regime); both "
                                           "signal and outcome_residual residualized"),
            "confounder_identifiability": (
                "a planned column that is CONSTANT within a block is not identifiable "
                "against the intercept and is dropped, recorded as "
                "confounders_dropped_constant. The venue indicator is constant by "
                "construction whenever SUBJECT fixes the side (always home or always away), "
                "so it drops for most hypotheses; this is a property of the frozen canonical "
                "grammar, not a choice made here."),
            "confounder_unavailable_in_corpus": (
                "score_state and formation are in the frozen ALLOWED set but the corpus "
                "supplies no PIT-safe per-fixture column for them; they are recorded per "
                "fold as confounders_unavailable_in_corpus rather than silently ignored"),
            "profile_axis_parsing": (
                "a profile axis names a metric AND a perspective: goals_for -> "
                "(goals, FOR); shots_on_target_against -> (shots_on_target, AGAINST)"),
            "profile_banding_cutoff": (
                "competition terciles computed at the fold's confirmatory start, which uses "
                "only data strictly before every validation fixture in the block and is "
                "therefore PIT-safe for all of them"),
            "degenerate_fast_path": (
                "an unconditioned, unwindowed cohort IS the baseline set, so the compiler "
                "returns signal == 0 exactly without rescanning; identical value, less work"),
            "terminal_state_order": [
                "UNMEASURABLE", "TAUTOLOGICAL(comparator-flagged)",
                "TAUTOLOGICAL(zero-variance signal)", "INSUFFICIENT_SUPPORT",
                "CONFOUNDED_UNRESOLVED", "OOS_DIRECTION_UNSTABLE",
                "OOS_FAIL", "OOS_NO_EFFECT", "OOS_SURVIVES",
                "CANDIDATE_FEATURE_ELIGIBLE"],
            "development_window_use": ("DEVELOPMENT effect computed ONLY to separate OOS_FAIL "
                                       "from OOS_NO_EFFECT; never confirmatory evidence"),
            "thin_fold_behaviour": ("a fold failing frozen support records "
                                    "INSUFFICIENT_SUPPORT and is excluded from the score; "
                                    "never silently dropped"),
        },
        "degeneracy_rule": ("C and B are shrunk toward the SAME prior, so cohort == baseline "
                            "yields signal == 0 exactly; zero variance across all folds -> "
                            "TAUTOLOGICAL, produced by the compiler, not asserted"),
        "reads_champion": False, "writes_champion": False, "uses_llm": False,
        "uses_bedrock": False,
    }


def engine_spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(engine_spec(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---------------------------------------------------------------------------------------
# statistics helpers (deterministic, no RNG)
# ---------------------------------------------------------------------------------------
def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 1e-15 or syy <= 1e-15:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def ols_residualize(y, X):
    """Residualize y on design matrix X (list of rows, intercept added). Normal equations."""
    n = len(y)
    if n == 0:
        return y
    cols = (len(X[0]) if X and X[0] else 0)
    A = [[1.0] + list(r) for r in X] if cols else [[1.0] for _ in range(n)]
    p = len(A[0])
    if n <= p:
        return None
    XtX = [[sum(A[i][a] * A[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    Xty = [sum(A[i][a] * y[i] for i in range(n)) for a in range(p)]
    # Gaussian elimination with partial pivoting
    M = [row[:] + [Xty[i]] for i, row in enumerate(XtX)]
    for c in range(p):
        piv = max(range(c, p), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-10:
            return None
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        for r in range(p):
            if r == c:
                continue
            f = M[r][c] / pv
            for k in range(c, p + 1):
                M[r][k] -= f * M[c][k]
    beta = [M[i][p] / M[i][i] for i in range(p)]
    return [y[i] - sum(beta[a] * A[i][a] for a in range(p)) for i in range(n)]


def t_two_sided_p(values):
    """Two-sided t-test that the mean of `values` is 0 (df = n-1). Deterministic."""
    n = len(values)
    if n < 2:
        return None
    m = sum(values) / n
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    if var <= 1e-18:
        return 0.0 if abs(m) > 1e-12 else 1.0
    t = m / math.sqrt(var / n)
    df = n - 1
    # regularized incomplete beta for the t distribution tail
    x = df / (df + t * t)
    return _betainc(df / 2.0, 0.5, x)


def _betainc(a, b, x):
    """Regularized incomplete beta I_x(a,b) via continued fraction (Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _betainc(b, a, 1 - x)
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= c * d
        if abs(1.0 - c * d) < 1e-12:
            break
    return front * (f - 1.0)


def benjamini_hochberg(pvals, q):
    """BH-FDR. Returns the list of booleans (rejected) aligned with `pvals`."""
    idx = sorted(range(len(pvals)), key=lambda i: pvals[i])
    n = len(pvals)
    rejected = [False] * n
    kmax = -1
    for rank, i in enumerate(idx, start=1):
        if pvals[i] <= q * rank / n:
            kmax = rank
    for rank, i in enumerate(idx, start=1):
        if rank <= kmax:
            rejected[i] = True
    return rejected


def empirical_bayes(scores, ses):
    """Shrink each score toward the family mean by its own reliability.

    tau2 = max(0, var(scores) - mean(se^2)) is the between-hypothesis variance; each score is
    pulled toward the family mean with weight tau2 / (tau2 + se_i^2), so a noisily-estimated
    hypothesis is pulled hard and a precisely-estimated one is barely moved. Deterministic.
    """
    n = len(scores)
    if n < 2:
        return list(scores)
    m = sum(scores) / n
    var = sum((x - m) ** 2 for x in scores) / (n - 1)
    mse = sum((e or 0.0) ** 2 for e in ses) / n
    tau2 = max(0.0, var - mse)
    out = []
    for x, e in zip(scores, ses):
        s2 = (e or 0.0) ** 2
        w = 1.0 if (tau2 + s2) <= 1e-18 else tau2 / (tau2 + s2)
        out.append(m + w * (x - m))
    return out
