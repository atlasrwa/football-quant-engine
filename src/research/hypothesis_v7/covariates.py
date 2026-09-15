"""V7 outcome-blind structural covariates for Control-B matching (`v7_covariates_v1`).

Task 3. Every covariate below is a deterministic function of a canonical hypothesis'
STRUCTURE plus the effect-blind provider/coverage contract. NOTHING here reads a historical
effect, an OOS result, a fold statistic, a significance value, or an outcome direction. The
schema is frozen BEFORE any confirmatory OOS is computed or viewed.

WHY RAW `PROVIDER_REQUIREMENTS` IS EXCLUDED
-------------------------------------------
`canonical_spec.PROVIDER_REQUIREMENTS` is the model's own declaration of what data it thinks
it needs. Measured against the V6.1 universe it is NOT a property of the statistical question:

  * `xg` capability vs an xg/np_xg target ....... 53 agree, 5 cap-only, 5 target-only
  * `target_fixture_venue_context` vs a venue comparator .. 0 agree, 30 cap-only, 17 comp-only
  * `match_level_observations` ................... present in only 65 of 132 families
  * `opponent_profile` vs an opponent_profile condition ... 33/33, ZERO discordant

Only the last is deterministic. Matching on the raw capability list would therefore match on
LLM self-description rather than on the question being asked, and would penalise a control
that cannot narrate its own requirements. So the raw list is excluded and the ONE genuine
question-property it encodes -- `USES_SIMILARITY` -- is carried explicitly.

`canonical.py` is NOT modified: `PROVIDER_REQUIREMENTS` stays inside the canonical spec and
therefore inside every `canonical_hypothesis_id`. The exclusion happens at the COVARIATE layer
only, so the frozen universe, dedup families and candidate lock are untouched.

ZERO SPEND. No LLM. No effects. No OOS.
"""
from __future__ import annotations

import hashlib
import json

COVARIATES_VERSION = "v7_covariates_v1"

#: Fields deliberately NOT available to the covariate builder. Asserted by test.
FORBIDDEN_COVARIATE_SOURCES = (
    "historical_effect", "oos_effect", "effect_size", "p_value", "significance",
    "fold_effect", "fold_performance", "outcome_direction", "survives", "oos_survives",
    "shrunk_effect", "confirmatory",
)

#: banding for target-set size, frozen (LLM spans 1..5, null spans 1..5)
TARGET_BANDS = ((1, 1, "T1"), (2, 2, "T2"), (3, 3, "T3"), (4, 5, "T4_5"))

#: METRIC -> structural metric group, computed IDENTICALLY for both origins from the TARGET
#: set itself. This replaces the model's own `research_family` label in the matching vector:
#: `research_family` is an LLM semantic judgement the deterministic null has no equivalent
#: process for (the null can only derive a family from content), so matching on it would again
#: match on self-labelling rather than on the question. Measured evidence that it is a label
#: and not a structural fact: `SUBJECT_RECENT_VS_LONG_BASELINE` carries FORM_VS_BASELINE 22
#: times but six other families 16 times, for identical structure. `research_family` is still
#: recorded as a DESCRIPTIVE covariate and still drives the confounder/multiplicity plan.
METRIC_GROUP = {
    "goals": "SCORING", "xg": "SCORING", "np_xg": "SCORING", "big_chances": "SCORING",
    "shots": "SHOT_VOLUME", "shots_on_target": "SHOT_VOLUME",
    "shots_off_target": "SHOT_VOLUME", "shots_inside_box": "SHOT_VOLUME",
    "shots_outside_box": "SHOT_VOLUME",
    "corner_kicks": "SET_PIECE", "accurate_crosses": "SET_PIECE",
    "possession": "TERRITORY", "final_third_entries": "TERRITORY",
    "touches_in_penalty_area": "TERRITORY", "offsides": "TERRITORY",
    "tackles": "DEFENSIVE_ACTION", "interceptions": "DEFENSIVE_ACTION",
    "clearances": "DEFENSIVE_ACTION", "blocked_shots": "DEFENSIVE_ACTION",
    "ball_recoveries": "DEFENSIVE_ACTION", "saves": "GOALKEEPING",
    "fouls": "DISCIPLINE", "yellow_cards": "DISCIPLINE", "red_cards": "DISCIPLINE",
    "cards_2h": "DISCIPLINE", "cards": "DISCIPLINE",
}


def metric_group(targets) -> str:
    """The structural metric group of a target set: the alphabetically-first group present.

    Deterministic, symmetric across origins, and a pure function of TARGET -- never of a label
    the generator chose for itself.
    """
    groups = sorted({METRIC_GROUP.get(m, "OTHER") for m in (targets or [])})
    return groups[0] if groups else "NONE"


#: comparator -> the baseline construction it compiles to (Phase 8 semantics)
BASELINE_TYPE = {
    "SUBJECT_OVERALL_BASELINE": "SUBJECT_ALL_PRIOR_MEAN",
    "SUBJECT_VENUE_BASELINE": "SUBJECT_VENUE_MEAN",
    "SUBJECT_COMPETITION_BASELINE": "SUBJECT_CROSS_COMPETITION_MEAN",
    "OPPONENT_OVERALL_BASELINE": "OPPONENT_ALL_PRIOR_CONCESSION",
    "OPPONENT_VENUE_BASELINE": "OPPONENT_VENUE_CONCESSION",
    "LEAGUE_ENVIRONMENT_BASELINE": "LEAGUE_SEASON_MEAN",
    "SIMILAR_OPPONENT_COHORT": "DISSIMILAR_OPPONENT_VENUE_MEAN",
    "SUBJECT_CONDITIONAL_VS_BASELINE": "SUBJECT_UNCONDITIONED_MEAN",
    "SUBJECT_RECENT_VS_LONG_BASELINE": "SUBJECT_LONG_RUN_UNDECAYED_MEAN",
}


def _band(n):
    for lo, hi, label in TARGET_BANDS:
        if lo <= n <= hi:
            return label
    return "T4_5"


def _cond_kinds(conditions):
    """The condition DIMENSIONS present, read structurally from the canonical tokens."""
    venue = profile = other = 0
    for c in conditions:
        blob = c if isinstance(c, str) else json.dumps(c, sort_keys=True)
        if "historical_venue_conditioning" in blob:
            venue += 1
        elif "opponent_profile" in blob:
            profile += 1
        else:
            other += 1
    return venue, profile, other


def build(canonical_spec: dict, measurability: dict, confounder_plan: dict) -> dict:
    """The frozen outcome-blind structural covariate vector for one canonical hypothesis.

    `measurability` is the effect-blind gate result (schema + measured coverage only);
    `confounder_plan` is the frozen per-family adjustment plan. Neither carries an effect.
    """
    targets = canonical_spec.get("TARGET") or []
    conds = canonical_spec.get("CONDITIONS") or []
    sim = canonical_spec.get("SIMILARITY_DIMENSIONS") or []
    comparator = canonical_spec.get("COMPARATOR")
    venue_c, profile_c, other_c = _cond_kinds(conds)

    per_metric = measurability.get("per_metric") or []
    admissible = measurability.get("admissible_competitions") or []
    requires_half = any(r.get("resolution") == "half" for r in per_metric)
    n_fields = sum(1 for r in per_metric if r.get("field"))

    # deterministic query complexity: how much machinery the compiled query needs.
    complexity = (len(targets) + 2 * len(conds) + 3 * (1 if sim else 0)
                  + (1 if comparator in ("SIMILAR_OPPONENT_COHORT",
                                         "SUBJECT_RECENT_VS_LONG_BASELINE") else 0))

    # expected support risk, from STRUCTURE only: narrower conditioning and similarity
    # cohorts cut the usable N before any data is touched.
    narrowing = len(conds) + (1 if sim else 0) + (1 if comparator ==
                                                  "SUBJECT_VENUE_BASELINE" else 0)
    support_risk = "LOW" if narrowing == 0 else ("MEDIUM" if narrowing == 1 else "HIGH")

    return {
        # --- question shape -------------------------------------------------------
        "n_target_metrics": len(targets),
        "target_band": _band(len(targets)),
        "primary_metric": sorted(targets)[0] if targets else None,
        "metric_group": metric_group(targets),
        "n_metric_groups": len({METRIC_GROUP.get(m, "OTHER") for m in targets}),
        # DESCRIPTIVE ONLY -- the model's own label, never a matching covariate
        "research_family_label": canonical_spec.get("FAMILY"),
        "subject": canonical_spec.get("SUBJECT"),
        "side": canonical_spec.get("SIDE"),
        "comparator": comparator,
        "baseline_type": BASELINE_TYPE.get(comparator),
        "time_scope": canonical_spec.get("TIME_SCOPE"),
        "comparator_is_reweighting":
            comparator == "SUBJECT_RECENT_VS_LONG_BASELINE",
        # --- conditioning depth ---------------------------------------------------
        "n_conditions": len(conds),
        "n_venue_conditions": venue_c,
        "n_profile_conditions": profile_c,
        "n_other_conditions": other_c,
        "uses_venue_conditioning": venue_c > 0,
        "uses_competition_conditioning": other_c > 0,
        # --- similarity -----------------------------------------------------------
        "uses_similarity": bool(sim),
        "n_similarity_dimensions": len(sim),
        # --- data requirements (effect-blind contract) ----------------------------
        "measurability_status": measurability.get("status"),
        "is_measurable": measurability.get("status") == "MEASURABLE",
        "n_required_fields": n_fields,
        "requires_half_resolution": requires_half,
        "providers": sorted(measurability.get("providers") or []),
        "n_admissible_competitions": len(admissible),
        "coverage_class": ("FULL" if len(admissible) == 6
                           else ("PARTIAL" if admissible else "NONE")),
        # --- analysis burden ------------------------------------------------------
        "confounder_family": confounder_plan.get("strategy"),
        "n_confounders": len(confounder_plan.get("confounders") or []),
        # --- derived complexity / risk --------------------------------------------
        "query_complexity": complexity,
        "support_risk_class": support_risk,
    }


#: the covariates the matching layer is allowed to use, in frozen order.
MATCHING_COVARIATES = (
    "uses_similarity", "comparator", "target_band", "time_scope", "metric_group",
    "measurability_status", "subject", "side", "n_conditions", "support_risk_class",
    "coverage_class", "requires_half_resolution",
)

#: recorded for transparency but NEVER used to match, with the reason.
DESCRIPTIVE_ONLY_COVARIATES = {
    "research_family_label": ("the model's own semantic family label; the deterministic null "
                              "has no equivalent labelling process, and identical structure "
                              "carries FORM_VS_BASELINE 22x vs six other families 16x in the "
                              "V6.1 universe. Matched on `metric_group` instead."),
    "primary_metric": "high-cardinality; matched via metric_group + target_band",
}


def schema() -> dict:
    return {
        "covariates_version": COVARIATES_VERSION,
        "matching_covariates": list(MATCHING_COVARIATES),
        "descriptive_only_covariates": dict(DESCRIPTIVE_ONLY_COVARIATES),
        "metric_groups": dict(METRIC_GROUP),
        "target_bands": [list(b) for b in TARGET_BANDS],
        "baseline_types": dict(BASELINE_TYPE),
        "outcome_blind": True,
        "forbidden_sources": list(FORBIDDEN_COVARIATE_SOURCES),
        "excluded_raw_provider_requirements": True,
        "exclusion_rationale": (
            "canonical_spec.PROVIDER_REQUIREMENTS is the model's self-description, not a "
            "property of the statistical question: measured against the V6.1 universe, xg "
            "capability vs xg target is 53 agree / 5 / 5, target_fixture_venue_context vs a "
            "venue comparator is 0 agree / 30 / 17, and match_level_observations appears in "
            "only 65 of 132 families. Only opponent_profile <-> opponent_profile condition is "
            "deterministic (33/33), and that is carried explicitly as USES_SIMILARITY. "
            "canonical.py is unchanged, so canonical ids and the candidate lock are untouched."),
        "frozen_before_oos": True,
    }


def schema_hash() -> str:
    return hashlib.sha256(
        json.dumps(schema(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
