"""DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1  (`item6_baseline_coverage_v1`)

Frozen, machine-readable declaration of the hypothesis-family space the deterministic
engine ALREADY covers. This is the single source of truth the baseline-equivalence
detector consults, and the abstract description the LLM is shown ("these are already
covered; do not spend hypothesis budget rediscovering them").

Grounded directly in the frozen V8C grammar
(`research/hypothesis_engine/V8C_HYPOTHESIS_GRAMMAR_SPEC.md`), which defines the
admissible deterministic universe as the tuple

    (target_metric, subject, perspective, comparator, window, conditions)

with:
  - 24 contract-covered target metrics
  - subject in {HOME_TEAM, AWAY_TEAM}
  - perspective in {FOR, AGAINST}
  - 10 comparators (COMPARATOR_BINDINGS)
  - 3 windows {ALL_PRIOR, W5, W10}
  - 76 condition shapes: arity 0/1/2, where arity-2 is CLOSED to exactly
    venue x opponent_profile and competition x opponent_profile.

IMPORTANT SCIENTIFIC DISCIPLINE
-------------------------------
This module deliberately encodes ONLY the *structural shape* of what is covered.
It does NOT record, and must never record, the historical OOS success/failure of any
baseline family. Revealing "which baseline families worked" would (a) leak outcome
information into the Stage-1 evaluator and (b) let the LLM optimize against our prior
audit. The LLM treatment input describes coverage abstractly; researcher knowledge of
prior OOS results is kept strictly out of this file.

The abstract descriptions here are phrased WITHOUT any concrete worked football
hypothesis (no metric pair, no direction, no venue, no profile instantiated as an
example). See ANTI-imitation tests.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple

BASELINE_COVERAGE_VERSION = "item6_baseline_coverage_v1"

# --- The frozen deterministic grammar dimensions (from V8C grammar spec) ----------------

# 24 contract-covered target metrics (np_xg excluded upstream, stays excluded).
BASELINE_TARGET_METRICS: Tuple[str, ...] = (
    "goals",
    "goals_conceded",
    "shots",
    "shots_on_target",
    "shots_against",
    "shots_on_target_against",
    "big_chances",
    "big_chances_against",
    "corner_kicks",
    "accurate_crosses",
    "possession",
    "touches_in_penalty_area",
    "ball_recoveries",
    "tackles",
    "interceptions",
    "blocks",
    "clearances",
    "fouls",
    "yellow_cards",
    "red_cards",
    "cards_2h",
    "offsides",
    "passes",
    "pass_accuracy",
)

BASELINE_SUBJECTS: Tuple[str, ...] = ("HOME_TEAM", "AWAY_TEAM")
BASELINE_PERSPECTIVES: Tuple[str, ...] = ("FOR", "AGAINST")

BASELINE_COMPARATORS: Tuple[str, ...] = (
    "LEAGUE_ENVIRONMENT_BASELINE",
    "OPPONENT_OVERALL_BASELINE",
    "OPPONENT_VENUE_BASELINE",
    "SIMILAR_OPPONENT_COHORT",
    "SUBJECT_COMPETITION_BASELINE",
    "SUBJECT_CONDITIONAL_VS_BASELINE",
    "SUBJECT_OVERALL_BASELINE",
    "SUBJECT_RECENT_VS_LONG_BASELINE",
    "SUBJECT_VENUE_BASELINE",
    "SUBJECT_VS_FIXTURE_OPPONENT",
)

BASELINE_WINDOWS: Tuple[str, ...] = ("ALL_PRIOR", "W5", "W10")

# 6 frozen opponent-profile axes (execution.PROFILE_AXES).
BASELINE_PROFILE_AXES: Tuple[str, ...] = (
    "goals_for",
    "goals_against",
    "shots_on_target_for",
    "shots_on_target_against",
    "possession_for",
    "shots_against",
)

# Condition dimensions the ontology declares.
BASELINE_CONDITION_DIMENSIONS: Tuple[str, ...] = (
    "historical_venue_conditioning",  # HOME | AWAY
    "opponent_profile",               # HIGH | MID | LOW x 6 axes
    "competition",                    # SAME
)

# Arity-2 interaction families that are CLOSED and covered (the only two).
BASELINE_INTERACTION_FAMILIES: Tuple[FrozenSet[str], ...] = (
    frozenset({"historical_venue_conditioning", "opponent_profile"}),
    frozenset({"competition", "opponent_profile"}),
)

# --- Baseline-covered structural family catalogue -----------------------------------------
# Each entry is a coarse structural family the deterministic engine covers. These are the
# categories the LLM is told are ALREADY covered. Descriptions are abstract (no worked
# football hypothesis).

BaselineFamily = Dict[str, object]

BASELINE_COVERED_FAMILIES: Tuple[BaselineFamily, ...] = (
    {
        "family_id": "BC_SAME_METRIC_MIRROR",
        "abstract_description": (
            "A single provider metric compared as a team's own production against the "
            "corresponding same-metric concession of the opponent (an attack-vs-concession "
            "'mirror' on one metric)."
        ),
        "structural_signature": {
            "comparator_in": ["SUBJECT_VS_FIXTURE_OPPONENT", "OPPONENT_OVERALL_BASELINE",
                               "OPPONENT_VENUE_BASELINE"],
            "single_metric": True,
            "mirror_for_against": True,
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_UNIVARIATE_PROFILE_SPLIT",
        "abstract_description": (
            "A single metric conditioned on ONE opponent-profile band (HIGH/MID/LOW) along "
            "ONE of the frozen profile axes, versus a subject baseline."
        ),
        "structural_signature": {
            "comparator_in": ["SUBJECT_CONDITIONAL_VS_BASELINE", "SUBJECT_OVERALL_BASELINE"],
            "single_metric": True,
            "condition_dims_subset_of": ["opponent_profile"],
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_SIMPLE_VENUE_CONTRAST",
        "abstract_description": (
            "A single metric contrasted by the subject's home/away venue, versus a subject "
            "or venue baseline (a pure venue split)."
        ),
        "structural_signature": {
            "comparator_in": ["SUBJECT_VENUE_BASELINE", "SUBJECT_OVERALL_BASELINE",
                               "OPPONENT_VENUE_BASELINE"],
            "single_metric": True,
            "condition_dims_subset_of": ["historical_venue_conditioning"],
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_RECENT_VS_LONGRUN",
        "abstract_description": (
            "A single metric's recent-window level contrasted with its long-run level "
            "(recent-vs-long-run deviation / form)."
        ),
        "structural_signature": {
            "comparator_in": ["SUBJECT_RECENT_VS_LONG_BASELINE"],
            "window_in": ["W5", "W10"],
            "single_metric": True,
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_TEAM_METRIC_X_OPP_CONCESSION",
        "abstract_description": (
            "A team's production on one metric read directly against the corresponding "
            "opponent concession of that same metric (direct cross-entity same-metric)."
        ),
        "structural_signature": {
            "comparator_in": ["SUBJECT_VS_FIXTURE_OPPONENT"],
            "single_metric": True,
            "mirror_for_against": True,
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_ENVIRONMENT_BASELINE",
        "abstract_description": (
            "A single metric read against its competition/league environment baseline."
        ),
        "structural_signature": {
            "comparator_in": ["LEAGUE_ENVIRONMENT_BASELINE", "SUBJECT_COMPETITION_BASELINE"],
            "single_metric": True,
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_SINGLE_DIM_PROFILE_ALREADY_EXPRESSIBLE",
        "abstract_description": (
            "Any single-dimensional profile/venue/competition split already expressible by "
            "the existing conditioning grammar (arity 0 or 1)."
        ),
        "structural_signature": {
            "single_metric": True,
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_SIMILAR_OPPONENT_COHORT",
        "abstract_description": (
            "A single metric read over a deterministically-computed cohort of opponents "
            "similar to the fixture opponent (existing similarity comparator)."
        ),
        "structural_signature": {
            "comparator_in": ["SIMILAR_OPPONENT_COHORT"],
            "single_metric": True,
            "max_condition_arity": 1,
        },
    },
    {
        "family_id": "BC_COVERED_TWO_DIM_INTERACTION",
        "abstract_description": (
            "The two closed arity-2 interactions the grammar already supports: venue crossed "
            "with a single opponent-profile band, and same-competition crossed with a single "
            "opponent-profile band."
        ),
        "structural_signature": {
            "max_condition_arity": 2,
            "interaction_families_covered": True,
        },
    },
    {
        "family_id": "BC_SALIENCE_RANKING",
        "abstract_description": (
            "Simple deterministic salience ranking / selection over existing enumerated "
            "candidates (no new representational construct)."
        ),
        "structural_signature": {
            "is_selection_only": True,
        },
    },
)

# The 9 deterministic research-family labels (structural map, V8C section 7). Used by the
# equivalence detector's family-collision heuristics and reported for transparency.
BASELINE_RESEARCH_FAMILY_LABELS: Tuple[str, ...] = (
    "ATTACK_VOLUME",
    "DEFENSIVE_CONCESSION",
    "SET_PIECE_GENERATION",
    "DISCIPLINE",
    "POSSESSION_CONTROL",
    "FORM_VS_BASELINE",
    "CROSS_ENTITY",
    "ENVIRONMENT",
    "MATCHUP_SIMILARITY",
)


# --- Structural axes the baseline grammar CANNOT express -----------------------------------
# These are the "escape hatches" a genuinely novel mechanism must use. They are declared here
# so the formalizer can detect when a mechanism requires a construct outside the grammar
# (an F4 additive-extension candidate). This is a structural declaration, NOT a hint list
# handed to the LLM.
BASELINE_UNSUPPORTED_STRUCTURES: Tuple[Dict[str, str], ...] = (
    {
        "structure_id": "US_MULTI_METRIC_INTERACTION",
        "description": (
            "A joint relationship between two or more DISTINCT provider metrics (not a "
            "single metric's for/against mirror) that cannot be reduced to one metric with "
            "one conditioning band."
        ),
    },
    {
        "structure_id": "US_TWO_DIM_OPP_PROFILE_INTERSECTION",
        "description": (
            "A conditioning intersection over TWO DISTINCT opponent-profile axes "
            "simultaneously (profile x profile), which the grammar excludes by design."
        ),
    },
    {
        "structure_id": "US_THRESHOLD_NONLINEARITY",
        "description": (
            "A threshold / piecewise / nonlinear relationship on a continuous observable "
            "(not the fixed HIGH/MID/LOW tercile banding)."
        ),
    },
    {
        "structure_id": "US_HALF_STATE_OR_GAME_STATE",
        "description": (
            "A within-match state construction (e.g. half-level split, or conditioning on a "
            "prior scoreline/game-state) where the provider resolution actually supports it."
        ),
    },
    {
        "structure_id": "US_CROSS_METRIC_ASYMMETRY",
        "description": (
            "An asymmetric attack-vs-defence relationship across DIFFERENT metrics (subject's "
            "metric A vs opponent's metric B, A != B)."
        ),
    },
    {
        "structure_id": "US_SEQUENCING_REGIME",
        "description": (
            "A sequencing / regime / trajectory construction over ordered prior matches beyond "
            "a simple recent-window mean."
        ),
    },
)


def version_stamp() -> Dict[str, object]:
    """Machine-readable version + capability envelope. Reads no outcome, no LLM output."""
    return {
        "baseline_coverage_version": BASELINE_COVERAGE_VERSION,
        "n_target_metrics": len(BASELINE_TARGET_METRICS),
        "n_comparators": len(BASELINE_COMPARATORS),
        "n_windows": len(BASELINE_WINDOWS),
        "n_profile_axes": len(BASELINE_PROFILE_AXES),
        "n_covered_families": len(BASELINE_COVERED_FAMILIES),
        "n_unsupported_structures": len(BASELINE_UNSUPPORTED_STRUCTURES),
        "reads_outcomes": False,
        "reads_oos_history": False,
        "reads_llm_output": False,
        "contains_worked_football_example": False,
    }


def covered_family_ids() -> List[str]:
    return [f["family_id"] for f in BASELINE_COVERED_FAMILIES]


def unsupported_structure_ids() -> List[str]:
    return [s["structure_id"] for s in BASELINE_UNSUPPORTED_STRUCTURES]


def abstract_coverage_prose() -> List[str]:
    """The abstract, example-free coverage statements shown to the LLM as treatment input."""
    return [f["abstract_description"] for f in BASELINE_COVERED_FAMILIES]
