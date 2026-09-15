"""V7 frozen endpoint definitions (`v7_endpoints_v1`). Tasks 1, 2, 8, 9.

V7 asks TWO questions that must never be collapsed into one number.

A. END_TO_END_RESEARCH_YIELD (Task 1A / Task 8)
   Denominator = ALL frozen canonical families, including the ones the corpus cannot measure.
   "Does the LLM generate research ideas that are actually usable by the current quant data
   stack?" Data-compatibility failure COUNTS here. The control is not rewarded merely for
   producing easy generic ideas, and the LLM is not rewarded for sophisticated but
   unmeasurable ones -- both are scored from the same full canonical starting point.

B. CONDITIONAL_SIGNAL_QUALITY (Task 1B / Task 9)
   Denominator = families passing the SAME frozen eligibility gates on both sides
   (MEASURABLE and ADEQUATE_SUPPORT), then matched/weighted on frozen structural covariates.
   "Conditional on being measurable and adequately supported, are the LLM's research ideas
   better than a structurally comparable generic null?"

DATA_COMPATIBILITY_RATE (Task 2) is a THIRD, purely descriptive quantity. It is a property of
the research system, not football evidence, and is reported separately from every OOS number.
It exists so that conditioning on measurability in endpoint B cannot hide the fact that the
LLM named low-coverage metrics more often than the null.

The primary statistic for B is chosen HERE, before any OOS is computed or viewed.

ZERO SPEND. No effects. No OOS.
"""
from __future__ import annotations

import hashlib
import json

ENDPOINTS_VERSION = "v7_endpoints_v1"

# ---- A: end-to-end research yield ------------------------------------------------------
END_TO_END = {
    "endpoint_id": "END_TO_END_RESEARCH_YIELD",
    "question": ("Does the LLM generate research ideas that are actually usable by the "
                 "current quant data stack, end to end?"),
    "denominator": "ALL frozen canonical families (measurable and unmeasurable alike)",
    "progression": ["canonical", "measurable", "adequate_support", "oos_survives"],
    "statistic": ("proportion of canonical families reaching OOS_SURVIVES, per origin, with "
                  "the full attrition ladder reported at every stage and reasons preserved"),
    "comparison": ("LLM origin vs DETERMINISTIC_NULL origin from the identical canonical "
                   "starting point; NOT matched, because matching on measurability would "
                   "condition away the very failure this endpoint measures"),
    "uncertainty": ("cluster bootstrap over (metric_family, primary_metric) blocks; the "
                    "control contributes at its matched weight, never at raw pool size"),
    "includes_unmeasurable": True,
    "note": ("a control is not credited for producing easy generic ideas, and the LLM is not "
             "credited for sophisticated but unmeasurable ones -- both are scored from the "
             "same denominator"),
}

# ---- B: conditional signal quality -----------------------------------------------------
CONDITIONAL_SIGNAL = {
    "endpoint_id": "CONDITIONAL_SIGNAL_QUALITY",
    "question": ("Conditional on being measurable and adequately supported, do the LLM's "
                 "hypotheses carry better OOS football information than a structurally "
                 "comparable generic null?"),
    "eligibility": ["MEASURABLE", "ADEQUATE_SUPPORT"],
    "eligibility_applied_symmetrically": True,
    "denominator": "families passing BOTH gates, on both sides, by the same frozen rules",
    "design": ("frozen outcome-blind covariate matching/weighting (see matching.py); one LLM "
               "family <-> weighted control set with total control weight 1"),
    "primary_statistic": "OOS_QUALITY_SCORE_DIFFERENCE",
    "primary_statistic_definition": (
        "mean difference in the continuous, pre-specified OOS_QUALITY_SCORE between each LLM "
        "family and its weighted control set, averaged over matched LLM families with equal "
        "weight per family. Continuous is preferred to a binary survival indicator so no "
        "information is discarded at an arbitrary threshold."),
    "secondary_statistics": ["OOS_SURVIVES_RATE_DIFFERENCE", "FOLD_DIRECTION_STABILITY",
                             "SHRINKAGE_ADJUSTED_EFFECT_QUALITY"],
    "uncertainty": ("cluster bootstrap over matched sets, clustered additionally by "
                    "(metric_family, primary_metric); never naive binomial SEs over the "
                    "pooled control count"),
    "excludes_unmeasurable": True,
    "no_comparable_control_handling": ("families with no credible control analogue are "
                                       "reported as NO_COMPARABLE_CONTROL and excluded from "
                                       "the matched statistic, never force-matched"),
}

#: The continuous primary score for endpoint B. DEFINED here, COMPUTED only after
#: authorization. Every term is produced by the deterministic/statistical engine.
OOS_QUALITY_SCORE = {
    "name": "OOS_QUALITY_SCORE",
    "range": "[-1, 1]",
    "definition": ("mean over confirmatory folds of the sign-consistent, shrinkage-adjusted "
                   "standardized effect, multiplied by the fold direction-agreement rate; a "
                   "family whose sign reverses across folds is pulled toward 0 by "
                   "construction rather than by a post-hoc rule"),
    "components": ["shrinkage_adjusted_standardized_effect_per_fold",
                   "fold_direction_agreement_rate"],
    "computed_by": "deterministic statistical engine",
    "llm_involvement": "none",
    "frozen_before_oos": True,
}

# ---- Task 2: descriptive data-compatibility --------------------------------------------
DATA_COMPATIBILITY = {
    "endpoint_id": "DATA_COMPATIBILITY_RATE",
    "kind": "DESCRIPTIVE_RESEARCH_SYSTEM_PROPERTY",
    "question": ("What fraction of an origin's canonical families can the current corpus "
                 "actually measure?"),
    "definition": ("n_measurable / n_canonical per origin, reported alongside the fraction "
                   "naming at least one coverage-failing metric and the per-metric drivers"),
    "is_football_evidence": False,
    "is_predictive_evidence": False,
    "reported_separately_from_oos": True,
    "rationale": ("the LLM may generate more contextually interesting but less "
                  "corpus-compatible questions; that is a real property of the research "
                  "system and must not be hidden by restricting all conclusions to the "
                  "measurable subset, nor promoted to football evidence"),
}


def data_compatibility(n_canonical: int, n_measurable: int,
                       n_naming_failing_metric: int, drivers: dict) -> dict:
    """The descriptive DATA_COMPATIBILITY_RATE for one origin. Effect-blind."""
    return {
        "n_canonical": n_canonical,
        "n_measurable": n_measurable,
        "data_compatibility_rate": round(n_measurable / max(n_canonical, 1), 4),
        "n_naming_coverage_failing_metric": n_naming_failing_metric,
        "coverage_failing_share": round(n_naming_failing_metric / max(n_canonical, 1), 4),
        "per_metric_drivers": dict(sorted(drivers.items())),
        "is_football_evidence": False,
    }


def attrition_ladder(n_canonical: int, n_measurable: int, n_supported=None) -> dict:
    """The end-to-end progression up to the pre-OOS frontier.

    `oos_survives` is deliberately absent: it is not computed at this stage. The ladder is
    frozen with a null placeholder so the shape cannot be changed after results are seen.
    """
    return {
        "canonical": n_canonical,
        "measurable": n_measurable,
        "adequate_support": n_supported,
        "oos_survives": None,
        "oos_stage_computed": False,
        "attrition_reasons_preserved": True,
    }


def version_stamp() -> dict:
    return {"endpoints_version": ENDPOINTS_VERSION,
            "end_to_end": END_TO_END,
            "conditional_signal": CONDITIONAL_SIGNAL,
            "oos_quality_score": OOS_QUALITY_SCORE,
            "data_compatibility": DATA_COMPATIBILITY,
            "endpoints_are_distinct": True,
            "collapsed_into_one_number": False,
            "primary_statistic_chosen_before_oos": True,
            "arm_contrast_is_descriptive_only": True}


def spec_hash() -> str:
    return hashlib.sha256(
        json.dumps(version_stamp(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
