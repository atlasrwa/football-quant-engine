"""V7 comparator semantics + confounder plan + multiplicity plan (`v7_analysis_v1`).
Phases 8, 11, 14. All FROZEN before any confirmatory effect is inspected.

- Comparator semantics reject degenerate comparisons that guarantee an apparent effect.
- The confounder plan is BY FAMILY and drawn from a frozen allowed set (the model's own
  `candidate_confounders` are metadata only; the engine trusts the frozen plan).
- The multiplicity plan pre-registers hypothesis families and a family-level FDR + hierarchical
  shrinkage rule, so nominal p<0.05 is never the sole promotion criterion.

ZERO SPEND. Deterministic. No effects computed here.
"""
from __future__ import annotations

ANALYSIS_VERSION = "v7_analysis_v1"

# ---- Phase 8: comparator semantics -----------------------------------------------------
# A comparator is REJECTED if the cohort's conditioning rule is essentially contained in the
# baseline (baseline absorption), if it compares a thing to itself, or if the difference is
# structurally implied. These checks are structural, not effect-based.
COMPARATOR_FLAGS = {
    "TAUTOLOGICAL_COMPARATOR": "cohort and baseline are defined by the same rule",
    "BASELINE_ABSORPTION": "baseline already contains the conditioning subset, guaranteeing "
                           "a near-zero or mechanically-signed difference",
    "SELF_COMPARISON": "subject compared to itself with no distinguishing condition",
    "STRUCTURALLY_IMPLIED_EFFECT": "arithmetic identity guarantees the sign",
}

# valid comparator -> (cohort definition, baseline definition) that are NOT nested.
VALID_COMPARATORS = {
    "SUBJECT_OVERALL_BASELINE": ("subject conditional cohort",
                                 "subject all-prior mean (venue-agnostic)"),
    "SUBJECT_VENUE_BASELINE": ("subject at target venue",
                               "subject venue-adjusted historical baseline"),
    "OPPONENT_OVERALL_BASELINE": ("opponent concession conditional cohort",
                                  "opponent all-prior concession baseline"),
    "OPPONENT_VENUE_BASELINE": ("opponent concession at venue",
                                "opponent venue concession baseline"),
    "SUBJECT_COMPETITION_BASELINE": ("subject in competition",
                                     "subject cross-competition baseline"),
    "LEAGUE_ENVIRONMENT_BASELINE": ("subject/opponent value",
                                    "league-season environment mean"),
    "SIMILAR_OPPONENT_COHORT": ("subject vs deterministic similar-opponent cohort",
                                "subject venue baseline over dissimilar opponents"),
    "SUBJECT_CONDITIONAL_VS_BASELINE": ("subject under condition",
                                        "subject baseline without the condition"),
    # Phase 10 recency family. The cohort is the time-DECAYED recent weighting of the
    # subject's own prior matches; the baseline is its long-run un-decayed mean over the same
    # PIT history. The two are NOT nested in the absorption sense -- they reweight the same
    # observations rather than one containing the other as a subset -- but they are strongly
    # correlated, so the contrast is only interpretable through the preregistered decay
    # half-lives in `pit.TIME_DECAY_HALFLIVES_DAYS` (180, 365). That family is frozen: the
    # engine reports BOTH half-lives and never selects the better-looking one.
    "SUBJECT_RECENT_VS_LONG_BASELINE": ("subject time-decayed recent weighting",
                                        "subject long-run un-decayed PIT baseline"),
}

#: comparators whose cohort and baseline are drawn from the SAME observation set and so must
#: be reported across the whole preregistered decay family, never at a single chosen window.
REWEIGHTING_COMPARATORS = {"SUBJECT_RECENT_VS_LONG_BASELINE"}


def flag_comparator(canonical_spec: dict) -> dict:
    """Structurally flag a comparator. A SIMILAR_OPPONENT_COHORT whose baseline is the SAME
    cohort would be absorption; an unconditioned SUBJECT_CONDITIONAL_VS_BASELINE is self-
    comparison. Returns {ok, flags}."""
    comp = canonical_spec.get("COMPARATOR")
    conds = canonical_spec.get("CONDITIONS") or []
    sim = canonical_spec.get("SIMILARITY_DIMENSIONS") or []
    flags = []
    if comp not in VALID_COMPARATORS:
        flags.append("STRUCTURALLY_IMPLIED_EFFECT")   # unknown comparator: refuse
    if comp == "SUBJECT_CONDITIONAL_VS_BASELINE" and not conds:
        flags.append("SELF_COMPARISON")
    if comp == "SIMILAR_OPPONENT_COHORT" and not sim and not conds:
        flags.append("TAUTOLOGICAL_COMPARATOR")
    # baseline absorption: a condition equal to the baseline partition (e.g. venue condition
    # against a venue baseline over the same venue) collapses the contrast.
    cond_blob = " ".join(conds).lower()
    if comp in ("SUBJECT_VENUE_BASELINE", "OPPONENT_VENUE_BASELINE") and "venue" in cond_blob:
        flags.append("BASELINE_ABSORPTION")
    return {"comparator": comp, "ok": not flags, "flags": flags,
            "requires_full_decay_family": comp in REWEIGHTING_COMPARATORS,
            "definition": VALID_COMPARATORS.get(comp)}


# ---- Phase 11: confounder plan by family ----------------------------------------------
ALLOWED_CONFOUNDERS = (
    "venue", "competition", "season_regime", "opponent_strength", "opponent_profile",
    "score_state", "cards", "formation", "team_baseline_quality")

# per research-family adjustment strategy + relevant confounders. Frozen.
CONFOUNDER_PLAN = {
    "ATTACK_VOLUME": {"confounders": ["venue", "competition", "opponent_strength",
                                      "team_baseline_quality"],
                      "strategy": "regression_adjustment + partial_pooling(team)"},
    "ATTACK_QUALITY": {"confounders": ["venue", "competition", "opponent_strength",
                                       "team_baseline_quality"],
                       "strategy": "regression_adjustment + partial_pooling(team)"},
    "DEFENSIVE_CONCESSION": {"confounders": ["venue", "competition", "opponent_strength",
                                             "team_baseline_quality"],
                             "strategy": "regression_adjustment + partial_pooling(team)"},
    "DEFENSIVE_SUPPRESSION": {"confounders": ["venue", "competition", "opponent_strength",
                                              "team_baseline_quality"],
                              "strategy": "regression_adjustment + partial_pooling(team)"},
    "SET_PIECE_GENERATION": {"confounders": ["venue", "competition", "opponent_profile",
                                             "team_baseline_quality"],
                             "strategy": "stratification(venue) + partial_pooling(team)"},
    "TEMPO_AND_TERRITORY": {"confounders": ["venue", "competition", "opponent_strength"],
                            "strategy": "regression_adjustment"},
    "DISCIPLINE": {"confounders": ["venue", "competition", "cards", "opponent_profile"],
                   "strategy": "stratification(venue,competition) + partial_pooling(team)"},
    "OPPONENT_PROFILE_INTERACTION": {"confounders": ["venue", "competition",
                                                     "opponent_profile", "opponent_strength",
                                                     "team_baseline_quality"],
                                     "strategy": "matched_similar_cohort + residualization"},
    "FORM_VS_BASELINE": {"confounders": ["venue", "competition", "opponent_strength",
                                         "season_regime"],
                         "strategy": "shrinkage_to_baseline + regression_adjustment"},
    "VENUE_EFFECT": {"confounders": ["competition", "opponent_strength"],
                     "strategy": "stratification(venue)"},
}
DEFAULT_PLAN = {"confounders": ["venue", "competition", "opponent_strength"],
                "strategy": "regression_adjustment"}


def confounder_plan_for(family: str) -> dict:
    return CONFOUNDER_PLAN.get(family, DEFAULT_PLAN)


# ---- Phase 14: multiplicity plan -------------------------------------------------------
# hypothesis families for multiplicity control (grouping of research_family tokens).
MULTIPLICITY_FAMILIES = {
    "attacking_volume": ["ATTACK_VOLUME", "TEMPO_AND_TERRITORY"],
    "attack_quality": ["ATTACK_QUALITY"],
    "defensive": ["DEFENSIVE_CONCESSION", "DEFENSIVE_SUPPRESSION"],
    "set_piece": ["SET_PIECE_GENERATION"],
    "discipline": ["DISCIPLINE"],
    "opponent_interaction": ["OPPONENT_PROFILE_INTERACTION"],
    "form_baseline": ["FORM_VS_BASELINE", "VENUE_EFFECT"],
}
MULTIPLICITY_METHOD = "BENJAMINI_HOCHBERG_FDR_per_family + EMPIRICAL_BAYES_SHRINKAGE"
FDR_Q = 0.10                    # family-wise false-discovery rate, frozen
PROMOTION_RULE = ("promotion requires: OOS survival (direction-stable across folds) AND "
                  "FDR-adjusted family significance at q=0.10 AND a shrinkage-adjusted "
                  "effect that remains non-trivial. Nominal p<0.05 is NEVER sufficient alone.")


def multiplicity_family_of(research_family: str) -> str:
    for fam, members in MULTIPLICITY_FAMILIES.items():
        if research_family in members:
            return fam
    return "other"


def version_stamp() -> dict:
    return {"analysis_version": ANALYSIS_VERSION,
            "valid_comparators": sorted(VALID_COMPARATORS),
            "reweighting_comparators": sorted(REWEIGHTING_COMPARATORS),
            "comparator_reject_flags": sorted(COMPARATOR_FLAGS),
            "allowed_confounders": list(ALLOWED_CONFOUNDERS),
            "confounder_plan_families": sorted(CONFOUNDER_PLAN),
            "multiplicity_families": {k: v for k, v in MULTIPLICITY_FAMILIES.items()},
            "multiplicity_method": MULTIPLICITY_METHOD, "fdr_q": FDR_Q,
            "promotion_rule": PROMOTION_RULE,
            "model_confounders_are_metadata_only": True,
            "frozen_before_confirmatory": True}
