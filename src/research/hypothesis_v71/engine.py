"""V7.1 measurement engine (`v71_engine_v1`).

The single execution path. The diagnostic replay and the (not yet authorized) confirmatory run
call exactly this code, so a dry run genuinely exercises what a real run would do.

Differences from V7's executor that matter scientifically:

  * the COMPILER is the hardened one: every declared comparator is executed, and a
    structurally invalid query RAISES instead of producing a zero-valued feature;
  * the effect unit is the FOLD, exactly as V7 froze it, with per-competition effects
    reported alongside as a secondary stability dimension (also as V7 froze it);
  * the confounder design is SCREENED generically, with constant and collinear columns dropped
    under named reasons rather than producing a singular solve;
  * every rate and correlation passes an explicit range contract, so an impossible value
    aborts the evaluator instead of flowing into a result.

Nothing here decides WHICH fixtures to read. That is the frozen fold manifest's job.
"""
from __future__ import annotations

from . import compiler as CO
from . import confounders as CF
from . import estimator as ES
from . import evaluability as EV
from . import invariants as INV
from . import recency as REC
from . import similarity as SIM
from src.research.hypothesis_v7 import pit as V7PIT

ENGINE_VERSION = "v71_engine_v1"

#: Terminal taxonomy. The structural states come FIRST: a hypothesis that never had a
#: contrast is not an out-of-sample failure, and conflating the two is how V7's headline
#: attrition became unreadable.
STRUCTURALLY_INVALID = "STRUCTURALLY_INVALID"
SEMANTICALLY_AMBIGUOUS = "SEMANTICALLY_AMBIGUOUS"
UNMEASURABLE = "UNMEASURABLE"
INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
CONFOUNDED_UNRESOLVED = "CONFOUNDED_UNRESOLVED"
OOS_DIRECTION_UNSTABLE = "OOS_DIRECTION_UNSTABLE"
OOS_NO_EFFECT = "OOS_NO_EFFECT"
OOS_SURVIVES = "OOS_SURVIVES"
CANDIDATE_FEATURE_ELIGIBLE = "CANDIDATE_FEATURE_ELIGIBLE"

TERMINAL_STATES = (STRUCTURALLY_INVALID, SEMANTICALLY_AMBIGUOUS, UNMEASURABLE,
                   INSUFFICIENT_SUPPORT, CONFOUNDED_UNRESOLVED, OOS_DIRECTION_UNSTABLE,
                   OOS_NO_EFFECT, OOS_SURVIVES, CANDIDATE_FEATURE_ELIGIBLE)

NONTRIVIAL_ABS_EFFECT_MIN = 0.05
MIN_CELL_OBSERVATIONS = 20


class Context:
    """Everything a fold needs that is not the hypothesis: PIT terciles, profile means and
    the similarity engine. Built once per fold from the fold's own training frontier."""

    def __init__(self, index, terciles, axis_cache, similarity):
        self.index = index
        self.terciles = terciles
        self.axis_cache = axis_cache
        self.similarity = similarity


def recency_family_for(ir):
    """The weightings a selector pair needs.

    A TIME_DECAY cohort is evaluated at EVERY frozen half-life and the results are averaged.
    The frozen recency contract says both members of the decay family are always reported and
    neither is ever selected, so evaluating one of them would silently turn a preregistered
    family into a chosen window.
    """
    if ir.cohort is not None and ir.cohort.weighting == "TIME_DECAY":
        return tuple(REC.family())
    return (REC.UniformRecency(),)


def _estimates(ir, index, rec_i, metric, ctx, capability, weightings):
    """(cohort estimate, baseline estimate, observed, fixtures read), averaged over the
    frozen decay family when the cohort is a reweighting one. Raises/refuses like the
    compiler it wraps."""
    cs, bs, observed, read = [], [], None, frozenset()
    for w in weightings:
        q = CO.compile_query(ir, index, rec_i, metric=metric, terciles=ctx.terciles,
                             axis_cache=ctx.axis_cache, similarity=ctx.similarity,
                             recency=w, capability=capability, collect_fixtures=False)
        if q.observed is None or q.environment_mean is None:
            raise CO.CompileRefused("observed value or environment mean unavailable")
        cw, bw = sum(q.cohort_weights), sum(q.baseline_weights)
        if cw <= 0 or bw <= 0:
            raise CO.CompileRefused("degenerate weights")
        c_mean = sum(x * v for x, v in zip(q.cohort_weights, q.cohort_values)) / cw
        b_mean = sum(x * v for x, v in zip(q.baseline_weights, q.baseline_values)) / bw
        cs.append(w.shrink(c_mean, q.cohort_n, q.environment_mean))
        bs.append(w.shrink(b_mean, q.baseline_n, q.environment_mean))
        observed, read = q.observed, read | q.fixtures_read
    return (sum(cs) / len(cs), sum(bs) / len(bs), observed, read)


def evaluate_cell(ir, metric, index, positions, ctx, plan, capability, recency):
    """One block of target fixtures: compile each, then adjust and correlate.

    `recency` is the weighting FAMILY (a tuple) or a single weighting; a reweighting cohort is
    always evaluated across the whole frozen family.
    """
    weightings = tuple(recency) if isinstance(recency, (tuple, list)) else (recency,)
    sig, res, rows, teams, fixtures = [], [], [], set(), set()
    refused = 0
    for rec_i in positions:
        try:
            c, b, observed, _read = _estimates(ir, index, rec_i, metric, ctx, capability,
                                               weightings)
        except (CO.CompileRefused, SIM.SimilarityRefused):
            refused += 1
            continue
        rec = index.recs[rec_i]
        subject = str(rec.home_id) if ir.subject == "HOME_TEAM" else str(rec.away_id)
        opp = str(rec.away_id) if str(rec.home_id) == subject else str(rec.home_id)
        sig.append(c - b)
        res.append(observed - b)
        rows.append({
            "venue": 1.0 if str(rec.home_id) == subject else 0.0,
            "competition": rec.competition,
            "opponent_strength": index.pit_mean(opp, metric, "FOR", rec_i)[0] or 0.0,
            "team_baseline_quality": b,
            "cards": index.pit_mean(subject, "yellow_cards", "FOR", rec_i)[0] or 0.0,
            "season_regime": float(abs(hash_free_season(rec.season_id))),
        })
        teams.add(subject)
        fixtures.add(str(rec.fixture_id))

    n = len(sig)
    out = {"n": n, "n_refused": refused, "unique_teams": len(teams),
           "unique_fixtures": len(fixtures), "effect": None, "adjusted": False,
           "signal_variance": None, "support": V7PIT.SUPPORT_NOT_EVALUABLE}
    if n == 0:
        return out
    weights = [1.0] * n
    support = V7PIT.classify_support(
        raw_n=n, unique_fixtures=len(fixtures), unique_teams=len(teams),
        effective_n=V7PIT.kish_effective_n(weights),
        concentration=V7PIT.weight_concentration(weights), n_competitions=1)
    out["support"] = support["status"]
    mean_s = sum(sig) / n
    out["signal_variance"] = sum((x - mean_s) ** 2 for x in sig) / n
    if n < MIN_CELL_OBSERVATIONS or support["status"] != V7PIT.SUPPORT_ADEQUATE:
        return out
    if out["signal_variance"] <= 1e-18:
        # A contrastless signal is a STRUCTURAL fact, not an out-of-sample failure. The
        # invariants should already have refused it; reaching here is recorded, not silently
        # turned into a zero effect.
        out["contrastless"] = True
        return out

    columns = {}
    for name in plan["confounders"]:
        if name == "competition":
            levels = sorted({r["competition"] for r in rows})[1:]
            for lv in levels:
                columns[f"competition={lv}"] = [
                    1.0 if r["competition"] == lv else 0.0 for r in rows]
        elif name in ("opponent_strength", "opponent_profile"):
            columns["opponent_strength"] = [r["opponent_strength"] for r in rows]
        elif name in rows[0]:
            columns[name] = [r[name] for r in rows]
    screened = CF.screen_design(columns)
    out["confounders_applied"] = sorted(screened["kept"])
    out["confounders_dropped"] = screened["dropped"]
    out["confounders_removed_from_plan"] = plan["removed"]

    X = [[screened["kept"][k][i] for k in sorted(screened["kept"])] for i in range(n)]
    rs = ES.ols_residualize(sig, X) if X and X[0] else sig
    rr = ES.ols_residualize(res, X) if X and X[0] else res
    if rs is None or rr is None:
        out["confounded_unresolved"] = True
        return out
    out["adjusted"] = bool(X and X[0])
    effect = ES.pearson(rs, rr)
    ES.assert_in_range("correlation", effect, where="cell effect")
    out["effect"] = effect
    return out


def hash_free_season(season_id):
    """A stable numeric season code. Never Python's salted `hash()`."""
    digits = "".join(ch for ch in str(season_id) if ch.isdigit())
    return int(digits) % 100000 if digits else 0


def evaluate_family(ir, folds, index, ctx, capability, recency=None, *,
                    restrict_to=None):
    """Every metric x every FOLD for one canonical family, plus per-competition blocks.

    The fold rows carry the confirmatory effects. The competition rows are a SECONDARY
    stability view and never enter the score, so a family cannot be rescued or condemned by
    slicing it more finely.
    """
    plan = CF.plan_for(ir.research_family)
    weightings = recency if recency is not None else recency_family_for(ir)
    metrics = [m for m in ir.target_metrics if m in index.metrics]
    per_metric = {}
    for m in metrics:
        cells, comp_cells = [], []
        for f in folds:
            positions = [p for p in f["positions"]
                         if restrict_to is None
                         or index.recs[p].competition in restrict_to]
            if not positions:
                continue
            cell = evaluate_cell(ir, m, index, positions, ctx, plan, capability, weightings)
            cell.update({"fold_index": f["fold_index"], "competitions": sorted(
                {index.recs[p].competition for p in positions})})
            cells.append(cell)
            by_comp = {}
            for p in positions:
                by_comp.setdefault(index.recs[p].competition, []).append(p)
            for comp, pos in sorted(by_comp.items()):
                c = evaluate_cell(ir, m, index, pos, ctx, plan, capability, weightings)
                c.update({"fold_index": f["fold_index"], "competition": comp})
                comp_cells.append(c)
        per_metric[m] = {"cells": cells, "competition_cells": comp_cells}
    return {"metrics": metrics, "per_metric": per_metric, "confounder_plan": plan}


def score_family(evidence):
    """OOS quality score, with direction agreement over FOLDS (V7's frozen unit)."""
    per_metric, all_effects = [], []
    for m, blk in sorted(evidence["per_metric"].items()):
        eff = [c["effect"] for c in blk["cells"] if c["effect"] is not None]
        if not eff:
            continue
        pos = sum(1 for e in eff if e > 0)
        neg = sum(1 for e in eff if e < 0)
        agree = max(pos, neg) / len(eff)
        ES.assert_in_range("direction_agreement", agree, where=m)
        mean_e = sum(eff) / len(eff)
        per_metric.append({"metric": m, "n_cells": len(eff), "mean_effect": mean_e,
                           "direction_agreement": agree, "score": mean_e * agree})
        all_effects += eff
    if not per_metric:
        return None
    score = sum(x["score"] for x in per_metric) / len(per_metric)
    agree = sum(x["direction_agreement"] for x in per_metric) / len(per_metric)
    n = len(all_effects)
    mean_all = sum(all_effects) / n
    se = None
    if n >= 2:
        var = sum((e - mean_all) ** 2 for e in all_effects) / (n - 1)
        se = (var / n) ** 0.5
    p = ES.t_two_sided_p(all_effects)
    ES.assert_in_range("p_value", p, where="family p")
    comp_agree = _competition_agreement(evidence)
    return {"oos_quality_score": score, "direction_agreement": agree,
            "competition_direction_agreement": comp_agree,
            "mean_fold_effect": mean_all, "se": se, "n_folds": n,
            "per_metric": per_metric, "p_value": p}


def _competition_agreement(evidence):
    """Secondary stability view: sign agreement across competitions. Reported, never scored."""
    vals = []
    for blk in evidence["per_metric"].values():
        eff = [c["effect"] for c in blk.get("competition_cells", [])
               if c["effect"] is not None]
        if not eff:
            continue
        pos = sum(1 for e in eff if e > 0)
        vals.append(max(pos, len(eff) - pos) / len(eff))
    return (sum(vals) / len(vals)) if vals else None


def terminal_state(*, ir_ok, invariant_ok, capability_status, evidence, score,
                   fdr_rejected):
    if not ir_ok:
        return SEMANTICALLY_AMBIGUOUS
    if not invariant_ok:
        return STRUCTURALLY_INVALID
    if capability_status in ("UNKNOWN", "UNSUPPORTED", "INSUFFICIENT_COVERAGE"):
        return UNMEASURABLE
    if evidence is None or score is None:
        if evidence is not None and any(
                c.get("confounded_unresolved")
                for blk in evidence["per_metric"].values() for c in blk["cells"]):
            return CONFOUNDED_UNRESOLVED
        return INSUFFICIENT_SUPPORT
    if score["direction_agreement"] < EV.DIRECTION_STABILITY_MIN:
        return OOS_DIRECTION_UNSTABLE
    if abs(score["oos_quality_score"]) < NONTRIVIAL_ABS_EFFECT_MIN:
        return OOS_NO_EFFECT
    return CANDIDATE_FEATURE_ELIGIBLE if fdr_rejected else OOS_SURVIVES


def spec() -> dict:
    """The engine's own frozen parameters, hashed before any confirmatory effect."""
    return {"engine_version": ENGINE_VERSION,
            "effect_unit": "FOLD",
            "secondary_stability_unit": "COMPETITION",
            "min_cell_observations": MIN_CELL_OBSERVATIONS,
            "nontrivial_abs_effect_min": NONTRIVIAL_ABS_EFFECT_MIN,
            "direction_stability_min": EV.DIRECTION_STABILITY_MIN,
            "stability_unit": EV.STABILITY_UNIT,
            "multi_metric_aggregation": "EQUAL_WEIGHT_MEAN_OVER_METRICS",
            "pvalue_method": "TWO_SIDED_T_ON_FOLD_EFFECTS",
            "adjustment": "OLS_RESIDUALIZATION_ON_SCREENED_FROZEN_PLAN",
            "shrinkage": {"prior": REC.SHRINKAGE_PRIOR, "k": REC.SHRINKAGE_STRENGTH_K},
            "decay_family_days": list(REC.HALFLIVES_DAYS),
            "decay_family_aggregation": "EQUAL_WEIGHT_MEAN_OVER_HALFLIVES (never selected)",
            "terminal_states": list(TERMINAL_STATES),
            "invariants_version": INV.INVARIANTS_VERSION,
            "compiler_version": CO.COMPILER_VERSION,
            "estimator_version": ES.ESTIMATOR_VERSION,
            "confounders_version": CF.CONFOUNDERS_VERSION,
            "emits_zero_feature_for_invalid_query": False}


def spec_hash() -> str:
    import hashlib
    import json
    return hashlib.sha256(
        json.dumps(spec(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def version_stamp() -> dict:
    return {"engine_version": ENGINE_VERSION, "spec_hash": spec_hash()}
